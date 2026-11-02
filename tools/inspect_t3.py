"""Read-only T3 schema diagnostics. Does not read prompts, credentials or settings."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import os

parser = argparse.ArgumentParser()
parser.add_argument("path", nargs="?", default=str(Path.home()/".t3/userdata/statev2.sqlite"))
parser.add_argument("--mappings", action="store_true", help="Show mapping JSON structure, never message contents")
parser.add_argument("--summary", action="store_true", help="Only membership counts, including exact matches in the saved catalog")
args = parser.parse_args()
if args.summary:
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    import t3_sessions
    import black_launcher
    os.environ['AGENT_MANAGER_T3_DB']=args.path
    result=t3_sessions.scan(Path.home())
    catalog=black_launcher.data_directory()/'chat_catalog.sqlite3'
    matches=0
    if catalog.is_file():
        db=sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True)
        try:
            matches=sum((source,sid) in result['sessions'] for source,sid in db.execute('SELECT source,id FROM sessions'))
        finally:
            db.close()
    print(json.dumps({'status':result['status'],'native_sessions':len(result['sessions']),'saved_chat_matches':matches}))
    raise SystemExit
with sqlite3.connect(Path(args.path).resolve().as_uri()+"?mode=ro", uri=True, timeout=1) as db:
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print(json.dumps(tables))
    if args.mappings:
        def shape(value, depth=0):
            if depth > 5:
                return "..."
            if isinstance(value, dict):
                return {key: shape(item, depth+1) for key,item in list(value.items())[:35]}
            if isinstance(value, list):
                return [shape(value[0], depth+1)] if value else []
            return type(value).__name__
        for table, columns in [
            ("orchestration_v2_projection_provider_sessions", "provider,driver,payload_json"),
            ("orchestration_v2_projection_provider_threads", "provider,driver,payload_json"),
            ("provider_session_runtime", "provider_name,resume_cursor_json,runtime_payload_json"),
            ("projection_thread_sessions", "provider_name,provider_session_id,provider_thread_id"),
        ]:
            print(table, "count", db.execute('SELECT count(*) FROM '+table).fetchone()[0])
            for row in db.execute('SELECT '+columns+' FROM '+table+' LIMIT 3'):
                print(json.dumps([shape(json.loads(v)) if isinstance(v,str) and v.startswith(('{','[')) else v for v in row]))
        raise SystemExit
    for table in tables:
        if not any(term in table.lower() for term in ("session", "thread", "provider")):
            continue
        columns = [(row[1], row[2]) for row in db.execute('PRAGMA table_info("'+table.replace('"','""')+'")')]
        print(json.dumps({"table": table, "columns": columns}))
