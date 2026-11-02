"""Change only the synthetic T3 membership fixture under notes/qa-data/home."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from test_t3_sessions import make_db

parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['add','remove','unavailable','restore'])
parser.add_argument('--chat',default='unread')
args=parser.parse_args()
home=ROOT/'notes/qa-data/home'
path=home/'.t3/userdata/statev2.sqlite'
backup=path.with_suffix('.sqlite.bak')
if args.action=='unavailable':
    if path.exists():
        if backup.exists():
            raise SystemExit('Restore the existing fixture backup first')
        path.rename(backup)
    path.write_bytes(b'Synthetic unavailable T3 database')
elif args.action=='restore':
    if backup.exists():
        path.unlink(missing_ok=True)
        backup.rename(path)
else:
    sid=json.loads((ROOT/'notes/qa-data/ids.json').read_text())[args.chat]
    if not path.exists():
        _,created=make_db(home);created.close()
    with sqlite3.connect(path) as db:
        owner='t3-fixture-'+args.chat
        db.execute('DELETE FROM orchestration_v2_projection_provider_threads WHERE thread_id=?',(owner,))
        db.execute('INSERT OR REPLACE INTO orchestration_v2_projection_threads VALUES (?,?,NULL)',(owner,'now' if args.action=='remove' else None))
        db.execute('INSERT INTO orchestration_v2_projection_provider_threads VALUES (?,?,?)',(owner,'codex',json.dumps({'nativeThreadRef':{'driver':'codex','nativeId':sid}})))
    db.close()
print('Synthetic T3 fixture:',args.action,args.chat)
