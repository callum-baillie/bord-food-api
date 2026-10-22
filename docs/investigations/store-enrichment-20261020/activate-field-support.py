"""Narrow, owner-authorized runtime module activation on the existing pinned image.

No image push, credential export, policy activation or other-service recreation.
"""

import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/bord-iowa-expand")
from remote import SSH

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
TOWER = Path("/home/callum/Documents/Projects/Tower/tower/Tower-build")
receipt = json.loads((HERE / "field-support-release.json").read_text())
release = receipt["release"]
modules = ["control.py", "platform.py", "refresh.py", "store_enrichment.py", "store_hours.py"]


def command(argv, *, data=None, timeout=120):
    result = subprocess.run(
        SSH + [shlex.join(argv)], input=data, capture_output=True, check=True, timeout=timeout
    )
    return result.stdout


# Compile/import and exercise actual Python 3.12 serving-image code without a network.
worker = [
    "docker",
    "run",
    "--rm",
    "-i",
    "--network",
    "none",
    "--entrypoint",
    "python",
    "--env",
    "PYTHONPATH=/app",
    "--user",
    "99:100",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges:true",
    "--read-only",
    "--tmpfs",
    "/tmp:rw,nosuid,size=128m",
]
for module in modules:
    worker += [
        "--mount",
        f"type=bind,src={release}/{module},dst=/app/bord_food_api/{module},readonly",
    ]
preflight = b"""import json,tempfile,hashlib,pathlib
from bord_food_api.platform import Platform
from bord_food_api.store_enrichment import reconcile_fields,publish_enrichment
with tempfile.TemporaryDirectory() as root:
 p=Platform(root)
 p.sync('fixture','IA','r1',[{'kind':'store','source_key':'1','payload':{'name':'Fixture','country':'US','address':{'region':'IA','country':'US'}}}])
 store=p.records('store')[0];result=reconcile_fields(store,[],now=1792513000)
 assert result['timezone']=='America/Chicago'
 publish_enrichment(p,[result],base_generation=p.current()['generation'],release='test',now=1792513000)
 assert p.get('store',store['id'])['field_provenance']['timezone']['status']=='derived'
 print(json.dumps({'python_image_preflight':'passed','network':'none','files':{name:hashlib.sha256(pathlib.Path('/app/bord_food_api/'+name).read_bytes()).hexdigest() for name in ['control.py','platform.py','refresh.py','store_enrichment.py','store_hours.py']}}))
"""
verified = json.loads(command(worker + [receipt["image_id"], "-"], data=preflight))
for name, digest in verified["files"].items():
    assert hashlib.sha256((ROOT / "bord_food_api" / name).read_bytes()).hexdigest() == digest
before = json.loads(command(["docker", "inspect", "--format", "{{json .}}", "bord-food-api"]))
assert before["Image"] == receipt["image_id"]
# Only inspect start/health metadata for companion services, never their environment.
related = {
    name: json.loads(command(["docker", "inspect", "--format", "{{json .State}}", name]))
    for name in ["Bord", "bord-food-crawl-history"]
}
path = "/mnt/cache/git/compose/productivity/compose.yaml"
original = command(["cat", path])
digest = hashlib.sha256(original).hexdigest()
mounts = "".join(
    f"      - ./config/operator-releases/{release.rsplit('/', 1)[1]}/{name}:/app/bord_food_api/{name}:ro\n"
    for name in modules
)
marker = "      - ./config/discovery-guards/37f542fbe0075c862636c2ce20b83c51ad726cefa3ab885e64af2f921173aee0/sources.py:/app/bord_food_api/sources.py:ro\n"
assert original.decode().count(marker) == 1
old_mounts = "".join(
    f"      - ./config/operator-releases/{receipt['previous_release'].rsplit('/', 1)[1]}/{name}:/app/bord_food_api/{name}:ro\n"
    for name in modules
)
assert original.decode().count(old_mounts) == 1
updated = original.decode().replace(old_mounts, mounts)
source = TOWER / "stacks/productivity/compose.yaml"
source_text = source.read_text()
assert source_text.count(marker) == 1
assert source_text.count(old_mounts) == 1
source_updated = source_text.replace(old_mounts, mounts)
# Mirror only the versioned files used for this serving override.
for name in modules:
    destination = (
        TOWER / "stacks/productivity/config/operator-releases" / release.rsplit("/", 1)[1] / name
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes((ROOT / "bord_food_api" / name).read_bytes())
command(["tee", "/tmp/bord-field-compose.yaml"], data=updated.encode())
script = f"""set -eu
cd /mnt/cache/git/compose/productivity
test "$(sha256sum compose.yaml | cut -d' ' -f1)" = {digest}
cp compose.yaml /mnt/cache/appdata/bord-food-api/backups/20261020-before-products-enrichment/compose-before-fields-r4.yaml
install -m 644 /tmp/bord-field-compose.yaml compose.yaml.next-fields
docker compose --env-file .env -p tower-productivity -f compose.yaml.next-fields config --quiet
mv compose.yaml.next-fields compose.yaml
docker compose --env-file .env -p tower-productivity -f compose.yaml up -d --no-deps bord-food-api
"""
command(["bash", "-s"], data=script.encode())
source.write_text(source_updated)
after = json.loads(command(["docker", "inspect", "--format", "{{json .State}}", "bord-food-api"]))
for name, state in related.items():
    assert (
        json.loads(command(["docker", "inspect", "--format", "{{json .State}}", name]))["StartedAt"]
        == state["StartedAt"]
    )
output = {
    "preflight": verified,
    "release": release,
    "base_image": before["Image"],
    "api_started_at": after["StartedAt"],
    "related_services_not_recreated": list(related),
    "compose_before_sha256": digest,
    "compose_after_sha256": hashlib.sha256(updated.encode()).hexdigest(),
    "source_policy_unchanged": True,
}
(HERE / "field-activation-initial.json").write_bytes((HERE / "field-activation.json").read_bytes())
(HERE / "field-activation.json").write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps(output))
