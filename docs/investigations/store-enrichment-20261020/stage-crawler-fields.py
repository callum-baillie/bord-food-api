"""Stage current crawler field support and verify imports offline; never start a crawl."""

import hashlib
import io
import json
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, "/tmp/bord-iowa-expand")
from remote import SSH

root = Path(__file__).resolve().parents[3]
here = Path(__file__).parent
files = {str(path.relative_to(root)): path for path in (root / "bord_food_api").glob("*.py")}
for name in [
    "run-iowa-crawl.py",
    "run-iowa-statewide.py",
    "run-reviewed-crawl.py",
    "run-us-crawl.py",
    "enrich-retained-stores.py",
]:
    files["scripts/" + name] = root / "scripts" / name
digest = hashlib.sha256()
for name, path in sorted(files.items()):
    digest.update(name.encode() + b"\0" + path.read_bytes())
release = "/mnt/cache/git/compose/productivity/config/crawl-field-releases/" + digest.hexdigest()
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w") as tar:
    for name, path in files.items():
        tar.add(path, arcname=name, recursive=False)


def run(cmd, data=None):
    return subprocess.run(
        SSH + [shlex.join(cmd)], input=data, capture_output=True, check=True, timeout=90
    ).stdout


run(["mkdir", "-p", release])
run(["tar", "-xf", "-", "-C", release], buffer.getvalue())
image = json.loads((here / "import-launch-r3.json").read_text())["image_id"]
code = """import importlib.util,json,tempfile
from pathlib import Path
from bord_food_api.platform import Platform
from bord_food_api.crawl_evidence import collect_evidence
for name in ['run-iowa-crawl','run-iowa-statewide','run-us-crawl']:
 spec=importlib.util.spec_from_file_location(name,Path('scripts')/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 if name!='run-us-crawl': assert callable(module.publish_crawl_evidence)
with tempfile.TemporaryDirectory() as directory:
 p=Platform(directory);p.sync('fixture','IA','r1',[{'kind':'store','source_key':'one','payload':{'name':'Fixture','country':'US','address':{'street':'1 Fixture St','city':'Ames','region':'IA','postal_code':'50010'}}}]);row=p.records('store')[0]
 target={'store_id':row['id'],'url':'https://example.org/one','source_address':row['address'],'expected_branch':'Fixture'}
 result=collect_evidence('<div itemscope itemtype="https://schema.org/GroceryStore"><span itemprop="name">Fixture</span><div itemprop="address" itemscope itemtype="https://schema.org/PostalAddress"><span itemprop="streetAddress">1 Fixture Street</span><meta itemprop="postalCode" content="50010"></div><a itemprop="telephone" href="tel:+15155551234">Call</a></div>',target,retrieved_at=1792514300)
 assert result['branch_match']=='exact_address' and result['field_assertions']
print(json.dumps({'preflight':'passed','network':'none','source_requests':0,'paid_calls':0,'jobs_started':0}))
"""
cmd = [
    "docker",
    "run",
    "--rm",
    "--network",
    "none",
    "--entrypoint",
    "python",
    "--workdir",
    "/operator-release",
    "--env",
    "PYTHONPATH=/operator-release:/app",
    "--user",
    "99:100",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges:true",
    "--read-only",
    "--tmpfs",
    "/tmp:rw,nosuid,size=128m",
    "--mount",
    f"type=bind,src={release},dst=/operator-release,readonly",
    image,
    "-c",
    code,
]
result = json.loads(run(cmd))
receipt = {
    "release": release,
    "files": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()},
    "bytes": len(buffer.getvalue()),
    **result,
}
tower = (
    Path(
        "/home/callum/Documents/Projects/Tower/tower/Tower-build/stacks/productivity/config/crawl-field-releases"
    )
    / release.rsplit("/", 1)[1]
)
for name, path in files.items():
    destination = tower / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(path.read_bytes())
(here / "crawler-staging.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps({k: v for k, v in receipt.items() if k != "files"}))
