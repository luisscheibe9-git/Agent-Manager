"""Provider transcript details. Never execute commands found in transcripts."""
import json
import re


def empty():
    return {"branch": "", "pull_requests": [], "changed_files": [], "tokens": {},
            "model": "", "context_window": None, "context_tokens": None,
            "running": None, "needs": False, "rate_limits": None, "pending": {},
            "active_turn": None, "usage_messages": {}, "attention_sequence": 0}


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
            if block.get("type") == "tool_use":
                details["running"] = True
                details["needs"] = block.get("name") in ("AskUserQuestion", "ExitPlanMode")
                if details["needs"]:
                    details["attention_sequence"] += 1
                text_details(json.dumps(block.get("input", {})), details)
        usage = message.get("usage") or {}
        if usage and message.get("id"):
            previous = details["usage_messages"].setdefault(message["id"], {})
            for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                previous[key] = max(previous.get(key, 0), usage.get(key, 0) or 0)
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
    details["changed_files"] = details["changed_files"][-100:]
    details["pull_requests"] = details["pull_requests"][-20:]
    return details
