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
code = """import fcntl,json,runpy,signal
from pathlib import Path
from contextlib import contextmanager
@contextmanager
def queued_lock(root):
 with (Path(root)/'worker.lock').open('a') as handle:
  def timeout(*_): raise TimeoutError('operator_worker_slot_timeout')
  signal.signal(signal.SIGALRM,timeout);signal.alarm(3600)
  try: fcntl.flock(handle,fcntl.LOCK_EX)
  finally: signal.alarm(0)
  try: yield
  finally: fcntl.flock(handle,fcntl.LOCK_UN)
ns=runpy.run_path('/operator/import.py')
ns['run'].__globals__['heavy_lock']=queued_lock
result=ns['run'](Path('/data'),Path('/data/operator-imports/us-off-snapshot-20261020-r2'),apply=True,off=Path('/data/downloads/open_food_facts/57fa7d1994038dcf3c9ec9c9700d4d476b699e533c85a0d2fbdba2ffbf94dccd.jsonl.gz'),sha256='1e8cbd8e00d78d42ed2cf419dd4020964cb37621076a67ee31667913be99ae37')
print(json.dumps(result))
"""
cmd = [
    "docker",
    "run",
    "-d",
    "--name",
    "bord-food-off-us-snapshot-20261020-r2",
    "--network",
    "none",
    "--entrypoint",
    "python",
    "--env",
    "PYTHONPATH=/app",
    "--no-healthcheck",
    "--memory",
    "2g",
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
for name in [
    "control.py",
    "platform.py",
    "refresh.py",
    "store_enrichment.py",
    "store_hours.py",
    "operator_products.py",
]:
    cmd += ["--mount", f"type=bind,src={release}/{name},dst=/app/bord_food_api/{name},readonly"]
cmd += [
    "--mount",
    f"type=bind,src={release}/import-retained-products.py,dst=/operator/import.py,readonly",
    r["image_id"],
    "-c",
    code,
]
p = subprocess.run(SSH + [shlex.join(cmd)], capture_output=True, text=True, check=True)
result = {
    "container_id": p.stdout.strip(),
    "release": release,
    "network": "none",
    "paid_calls": 0,
    "scope": ["en:united-states"],
    "worker_lock": "same exclusive flock, explicit bounded operator wait rather than fail-fast",
}
(here / "off-launch-initial.json").write_bytes((here / "off-launch.json").read_bytes())
(here / "off-launch.json").write_text(json.dumps(result, indent=2) + "\n")
print(result)
