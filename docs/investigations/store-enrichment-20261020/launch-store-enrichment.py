import json
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/bord-iowa-expand")
from remote import SSH

here = Path(
    "/home/callum/Documents/GitHub/bord-food-api/docs/investigations/store-enrichment-20261020"
)
r = json.loads((here / "import-launch-r3.json").read_text())
release = r["release"]
modules = [
    "control.py",
    "platform.py",
    "refresh.py",
    "store_enrichment.py",
    "store_hours.py",
    "store_sources.py",
    "store_microdata.py",
    "store_discovery.py",
    "crawl_evidence.py",
]
cmd = [
    "docker",
    "run",
    "-d",
    "--name",
    "bord-food-store-enrichment-20261020-r2",
    "--network",
    "none",
    "--entrypoint",
    "python",
    "--env",
    "PYTHONPATH=/app",
    "--no-healthcheck",
    "--memory",
    "1536m",
    "--cpus",
    "1.5",
    "--user",
    "99:100",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges:true",
    "--read-only",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,size=32m",
    "--mount",
    "type=bind,src=/mnt/cache/appdata/bord-food-api,dst=/data",
]
for name in modules:
    cmd += ["--mount", f"type=bind,src={release}/{name},dst=/app/bord_food_api/{name},readonly"]
cmd += [
    "--mount",
    f"type=bind,src={release}/enrich-retained-stores.py,dst=/operator/enrich.py,readonly",
    r["image_id"],
    "-c",
    "import runpy,sys,time,json;from pathlib import Path;sys.argv=['/operator/enrich.py','--data-dir','/data','--run-dir','/data/operator-imports/store-enrichment-20261020','--publish'];status=Path('/data/operator-imports/store-enrichment-20261020/status.json');status.parent.mkdir(parents=True,exist_ok=True);status.write_text(json.dumps({'state':'waiting_for_worker_slot','source_network':False,'paid_calls':0}));\nfor attempt in range(120):\n try:\n  runpy.run_path('/operator/enrich.py',run_name='__main__');status.write_text((status.parent/'publication.json').read_text());break\n except BlockingIOError:\n  time.sleep(30)\nelse:\n status.write_text(json.dumps({'state':'failed','reason':'worker_slot_timeout'}));raise SystemExit(1)",
]
p = subprocess.run(SSH + [shlex.join(cmd)], capture_output=True, text=True, check=True)
result = {
    "container_id": p.stdout.strip(),
    "release": release,
    "network": "none",
    "paid_calls": 0,
    "queued_behind_existing_import": True,
}
(here / "enrichment-launch.json").write_text(json.dumps(result, indent=2) + "\n")
print(result)
