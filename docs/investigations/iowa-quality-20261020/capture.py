import json
import pathlib
import subprocess
import sys


def run(code):
    # Explicit read-only operator invocation: capture.py SSH_IDENTITY OUTPUT_JSON.
    command = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=10",
        "-i",
        sys.argv[1],
        "root@192.168.0.10",
        "docker exec -i bord-food-api python -",
    ]
    return subprocess.run(
        command, input=code, text=True, capture_output=True, timeout=120, check=True
    ).stdout


code = """import json,sqlite3,time
from pathlib import Path
root=Path('/data');raw=(root/'current.json').read_text();manifest=json.loads(raw)
db=sqlite3.connect((root/manifest['packs']['stores']).resolve().as_uri()+'?mode=ro',uri=True)
rows=[json.loads(p) for p, in db.execute("SELECT payload FROM entities WHERE kind='store'")];chains=[json.loads(p) for p, in db.execute("SELECT payload FROM entities WHERE kind='chain'")];db.close()
counts={}
for pack in ['usda','products','guidance','maps']:
 db=sqlite3.connect((root/manifest['packs'][pack]).resolve().as_uri()+'?mode=ro',uri=True)
 try:counts[pack]=db.execute('SELECT kind,count(*) FROM entities GROUP BY kind').fetchall()
 except sqlite3.OperationalError:counts[pack]={'tables':[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]}
 db.close()
status={}
for name in ['iowa-fields-statewide-20261020','iowa-fields-statewide-20261020-primary','iowa-fields-statewide-20261020-canonical']:
 path=root/'crawl-campaigns'/name/'status.json'
 if path.exists():status[name]=json.loads(path.read_text())
off=root/'operator-imports/us-off-snapshot-20261020-r2/status.json'
print(json.dumps({'captured_at':time.time(),'generation':manifest['generation'],'manifest_unchanged_during_read':raw==(root/'current.json').read_text(),'packs':manifest['packs'],'all_store_count':len(rows),'stores':[r for r in rows if r.get('address',{}).get('region')=='IA'],'chains':chains,'pack_counts':counts,'campaigns':status,'off':json.loads(off.read_text()) if off.exists() else None}))
"""
result = run(code)
pathlib.Path(sys.argv[2]).write_text(result)
s = json.loads(result)
print(
    {
        k: s[k]
        for k in ["generation", "manifest_unchanged_during_read", "all_store_count", "pack_counts"]
    }
)
print("Iowa", len(s["stores"]))
print(
    "campaigns",
    {
        k: {f: v.get(f) for f in ["state", "phase", "counts", "active", "error_type"]}
        for k, v in s["campaigns"].items()
    },
)
