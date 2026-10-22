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
args = [
    "/operator/import.py",
    "--data-dir",
    "/data",
    "--run-dir",
    "/data/operator-imports/us-off-snapshot-20261020",
    "--off",
    "/data/downloads/open_food_facts/57fa7d1994038dcf3c9ec9c9700d4d476b699e533c85a0d2fbdba2ffbf94dccd.jsonl.gz",
    "--off-sha256",
    "1e8cbd8e00d78d42ed2cf419dd4020964cb37621076a67ee31667913be99ae37",
    "--apply",
]
code = (
    "import json,runpy,sys,time;from pathlib import Path;status=Path('/data/operator-imports/us-off-snapshot-20261020/status.json');status.parent.mkdir(parents=True,exist_ok=True);status.write_text(json.dumps({'state':'waiting_for_store_publication','source_network':False,'paid_calls':0,'off_scope':['en:united-states']}));\nfor attempt in range(240):\n p=Path('/data/operator-imports/store-enrichment-20261020/publication.json');\n if p.exists() and json.loads(p.read_text()).get('state')=='published':\n  status.unlink();sys.argv="
    + repr(args)
    + ";runpy.run_path('/operator/import.py',run_name='__main__');break\n time.sleep(30)\nelse:\n status.write_text(json.dumps({'state':'failed','reason':'store_publication_wait_timeout'}));raise SystemExit(1)"
)
cmd = [
    "docker",
    "run",
    "-d",
    "--name",
    "bord-food-off-us-snapshot-20261020",
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
    "waiting_for_store_publication": True,
}
(here / "off-launch.json").write_text(json.dumps(result, indent=2) + "\n")
print(result)
