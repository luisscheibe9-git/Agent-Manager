"""Provider transcript details. Never execute commands found in transcripts."""
import json
import re
import time
from datetime import datetime


def empty():
    return {"branch": "", "pull_requests": [], "changed_files": [], "tokens": {},
            "model": "", "context_window": None, "context_tokens": None,
            "running": None, "needs": False, "rate_limits": None, "pending": {},
            "active_turn": None, "usage_messages": {}, "attention_sequence": 0,
            "usage_buckets": {}, "limit_hits": []}


LIMIT_HIT = re.compile(r"hit your (?:session|usage|5-hour) limit\s*[·\-]\s*resets (\d{1,2})(?::(\d{2}))?\s*([ap]m)", re.I)


def note_limit_hit(details, record, text):
    """Remember 'You've hit your session limit · resets 2am' so spend before it can calibrate the 5-hour limit."""
    match = LIMIT_HIT.search(text or "")
    if not match:
        return
    try:
        hit = datetime.fromisoformat(str(record.get("timestamp")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return
    hour, minute = int(match.group(1)) % 12, int(match.group(2) or 0)
    if match.group(3).lower() == "pm":
        hour += 12
    local = time.localtime(hit)
    reset = time.mktime((local.tm_year, local.tm_mon, local.tm_mday, hour, minute, 0, 0, 0, -1))
    if reset <= hit:
        reset += 86400
    if all(abs(known["reset"] - reset) > 600 for known in details["limit_hits"]):
        details["limit_hits"].append({"at": hit, "reset": reset})


def claude_weight(usage):
    """Cost-weighted token units (output costs more than input; cache reads are cheap): a closer proxy for plan limits."""
    return (usage.get("input_tokens", 0) + 5 * usage.get("output_tokens", 0)
            + 1.25 * usage.get("cache_creation_input_tokens", 0) + 0.1 * usage.get("cache_read_input_tokens", 0))


def add_usage(details, stamp, tokens):
    """Count tokens that spend plan limits (not cache reads) in 5-minute buckets for the 5-hour share."""
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return
    key = str(int(when // 300 * 300))
    details["usage_buckets"][key] = details["usage_buckets"].get(key, 0) + tokens


def text_details(text, details):
    if not isinstance(text, str):
        return
    for url in re.findall(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+", text):
        if url not in details["pull_requests"]:
            details["pull_requests"].append(url)
    for filename in re.findall(r"\*\*\* (?:Update|Add|Delete) File: ([^\r\n]+)", text):
        filename = filename.split('\\n')[0].rstrip('"')
        if filename not in details["changed_files"]:
            details["changed_files"].append(filename)


def codex(record, details):
    payload = record.get("payload") or {}
    if not isinstance(payload, dict):
        return
    kind = record.get("type")
    event = payload.get("type")
    if kind == "session_meta":
        details["branch"] = (payload.get("git") or {}).get("branch", "")
        details["context_window"] = payload.get("context_window")
    elif kind == "turn_context":
        details["model"] = payload.get("model") or details["model"]
    elif kind == "event_msg":
        if event == "task_started":
            details["attention_sequence"] += 1
            details.update(running=True, needs=False, pending={}, active_turn=payload.get("root_turn_id") or payload.get("turn_id"))
            details["context_window"] = payload.get("model_context_window") or details["context_window"]
        elif event in ("task_complete", "task_completed", "turn_aborted", "task_failed"):
            turn = payload.get("root_turn_id") or payload.get("turn_id")
            if not turn or not details["active_turn"] or turn == details["active_turn"]:
                details["running"] = False
                details["attention_sequence"] += 1
        elif event == "token_count":
            info = payload.get("info") or {}
            details["tokens"] = info.get("total_token_usage") or details["tokens"]
            total = info.get("total_token_usage") or {}
            cached = total.get("cached_input_tokens", 0) or 0
            spent = ((total.get("input_tokens", 0) or 0) - cached) + 0.1 * cached + 8 * (total.get("output_tokens", 0) or 0)
            if spent > details.get("_spent", 0):
                add_usage(details, record.get("timestamp"), spent - details.get("_spent", 0))
                details["_spent"] = spent
            details["context_tokens"] = (info.get("last_token_usage") or {}).get("total_tokens")
            details["context_window"] = info.get("model_context_window") or details["context_window"]
            details["rate_limits"] = payload.get("rate_limits") or details["rate_limits"]
    elif kind == "response_item":
        call_id = payload.get("call_id")
        if event in ("function_call", "custom_tool_call"):
            name = payload.get("name", "")
            arguments = payload.get("arguments") or payload.get("input") or ""
            text_details(arguments, details)
            if "request_user_input" in name:
                details["attention_sequence"] += 1
                details["pending"][call_id or name] = "async" if "async" in name else "sync"
        elif event in ("function_call_output", "custom_tool_call_output"):
            output = payload.get("output", "")
            if details["pending"].get(call_id) == "sync":
                details["pending"].pop(call_id, None)
            text_details(output, details)
        elif event == "message":
            if payload.get("role") == "user":
                details["pending"].clear()
                details["attention_sequence"] += 1
            elif payload.get("role") == "assistant" and payload.get("phase") != "commentary":
                details["attention_sequence"] += 1
            for block in payload.get("content", []):
                if isinstance(block, dict):
                    text_details(block.get("text", ""), details)
        details["needs"] = bool(details["pending"])


def claude(record, details):
    details["branch"] = record.get("gitBranch") or details["branch"]
    message = record.get("message") or {}
    if record.get("isSidechain"):
        return
    if record.get("type") == "user":
        content = message.get("content")
        if isinstance(content, str) or any(isinstance(b, dict) and b.get("type") == "text" for b in content or []):
            details.update(running=True, needs=False)
            details["attention_sequence"] += 1
    if record.get("type") == "assistant":
        details["model"] = message.get("model") or details["model"]
        stop = message.get("stop_reason")
        if stop in ("end_turn", "stop_sequence", "max_tokens"):
            details.update(running=False, needs=False)
            details["attention_sequence"] += 1
        elif stop == "tool_use":
            details["running"] = True
        for block in message.get("content", []) if isinstance(message.get("content"), list) else []:
            if not isinstance(block, dict):
                continue
            text_details(block.get("text", ""), details)
            note_limit_hit(details, record, block.get("text", ""))
            if block.get("type") == "tool_use":
                details["running"] = True
                details["needs"] = block.get("name") in ("AskUserQuestion", "ExitPlanMode")
                if details["needs"]:
                    details["attention_sequence"] += 1
                text_details(json.dumps(block.get("input", {})), details)
        usage = message.get("usage") or {}
        if usage and message.get("id"):
            previous = details["usage_messages"].setdefault(message["id"], {})
            spent_before = claude_weight(previous)
            for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                previous[key] = max(previous.get(key, 0), usage.get(key, 0) or 0)
            spent_after = claude_weight(previous)
            if spent_after > spent_before:
                add_usage(details, record.get("timestamp"), spent_after - spent_before)
            totals = {key: sum(m.get(key, 0) for m in details["usage_messages"].values())
                      for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
            totals["cached_input_tokens"] = totals["cache_read_input_tokens"]
            totals["total_tokens"] = sum(totals[k] for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            details["tokens"] = totals
            details["context_tokens"] = sum(previous.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    if record.get("type") == "system" and record.get("subtype") in ("turn_duration", "stop_hook_summary"):
        details["attention_sequence"] += 1
        details["running"] = False


def finish(details):
    details.pop("usage_messages", None)
    details.pop("pending", None)
    details.pop("active_turn", None)
    details.pop("_spent", None)
    details["limit_hits"] = details["limit_hits"][-20:]
    cutoff = time.time() - 60 * 86400
    details["usage_buckets"] = {k: v for k, v in details["usage_buckets"].items() if int(k) >= cutoff}
    details["changed_files"] = details["changed_files"][-100:]
    details["pull_requests"] = details["pull_requests"][-20:]
    return details
