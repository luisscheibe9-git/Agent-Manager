"""Append realistic lifecycle events to this checkout's synthetic QA sessions only."""
import argparse
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent.parent / "notes/qa-data"
parser = argparse.ArgumentParser()
parser.add_argument("event", choices=["working", "needs", "done", "usage"])
parser.add_argument("--chat", default="working")
args = parser.parse_args()
ids = json.loads((ROOT / "ids.json").read_text())
sid = ids[args.chat]
path = ROOT / "home/.codex/sessions" / (sid + ".jsonl")
def event(kind, payload): return {"type":kind,"timestamp":time.time(),"payload":payload}
if args.event == "working":
    rows = [event("event_msg", {"type":"task_started","turn_id":"qa-live"}),
            event("response_item", {"type":"message","role":"user","content":[{"type":"input_text","text":"Continue the synthetic task"}]})]
elif args.event == "needs":
    rows = [event("response_item", {"type":"function_call","name":"request_user_input_async","call_id":"qa-live-question","arguments":"{}"}),
            event("response_item", {"type":"function_call_output","call_id":"qa-live-question","output":"Question accepted; awaiting reply"})]
elif args.event == "done":
    rows = [event("response_item", {"type":"message","role":"user","content":[{"type":"input_text","text":"Approved (synthetic fixture answer)"}]}),
            event("response_item", {"type":"message","role":"assistant","phase":"final_answer","content":[{"type":"output_text","text":"Live QA update: the task is complete. This is synthetic test data."}]}),
            event("event_msg", {"type":"task_complete","turn_id":"qa-live"})]
else:
    rows = [event("event_msg", {"type":"token_count","info":{"total_token_usage":{"input_tokens":32000,"cached_input_tokens":20000,"output_tokens":8000,"reasoning_output_tokens":1500,"total_tokens":40000},"last_token_usage":{"total_tokens":17000},"model_context_window":200000}})]
with path.open("a", encoding="utf8") as stream:
    for row in rows: stream.write(json.dumps(row)+"\n")
print(f"Appended {args.event} to synthetic {args.chat} chat")
