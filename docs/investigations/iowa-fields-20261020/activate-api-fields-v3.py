"""Replace only the serving field-retention module on the existing pinned image."""

import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/bord-iowa-expand")
from remote import SSH

HERE = Path(__file__).parent
TOWER = Path("/home/callum/Documents/Projects/Tower/tower/Tower-build")
r = json.loads((HERE / "current-release.json").read_text())
assert (
    json.loads((HERE / "actual-image-preflight.json").read_text())["actual_image_preflight"]
    == "passed"
)


def cmd(args, body=None):
    p = subprocess.run(
        SSH + [shlex.join(args)], input=body, capture_output=True, check=True, timeout=180
    )
    return p.stdout


before = {
    name: json.loads(cmd(["docker", "inspect", "--format", "{{json .State}}", name]))
    for name in ["bord-food-api", "Bord", "bord-food-crawl-history"]
}
assert (
    cmd(["docker", "inspect", "--format", "{{.Image}}", "bord-food-api"]).decode().strip()
    == r["image_id"]
)
path = "/mnt/cache/git/compose/productivity/compose.yaml"
original = cmd(["cat", path]).decode()
lines = re.findall(
    r"^      - .+:/app/bord_food_api/store_enrichment.py:ro\n", original, re.MULTILINE
)
assert len(lines) == 1
new = (
    "      - ./config/crawl-field-releases/"
    + r["release"].rsplit("/", 1)[1]
    + "/bord_food_api/store_enrichment.py:/app/bord_food_api/store_enrichment.py:ro\n"
)
updated = original.replace(lines[0], new)
source = TOWER / "stacks/productivity/compose.yaml"
local = source.read_text()
assert local.count(lines[0]) == 1
backup = "/mnt/cache/appdata/bord-food-api/backups/20261020-before-iowa-fields"
cmd(["tee", "/tmp/bord-iowa-fields-compose.yaml"], updated.encode())
script = f"""set -eu
cd /mnt/cache/git/compose/productivity
test "$(sha256sum compose.yaml | cut -d' ' -f1)" = {hashlib.sha256(original.encode()).hexdigest()}
cp compose.yaml {backup}/compose-before-v2-fields.yaml
cp /mnt/cache/appdata/bord-food-api/current.json {backup}/manifest-before-v2-fields.json
install -m 644 /tmp/bord-iowa-fields-compose.yaml compose.yaml.next-iowa-fields
docker compose --env-file .env -p tower-productivity -f compose.yaml.next-iowa-fields config --quiet
mv compose.yaml.next-iowa-fields compose.yaml
docker compose --env-file .env -p tower-productivity -f compose.yaml up -d --no-deps --wait --wait-timeout 120 bord-food-api
"""
cmd(["bash", "-s"], script.encode())
source.write_text(local.replace(lines[0], new))
after = {
    name: json.loads(cmd(["docker", "inspect", "--format", "{{json .State}}", name]))
    for name in before
}
assert all(
    before[n]["StartedAt"] == after[n]["StartedAt"] for n in ["Bord", "bord-food-crawl-history"]
)
receipt = {
    "image_id": r["image_id"],
    "module_release": r["release"],
    "before": before,
    "after": after,
    "compose_before_sha256": hashlib.sha256(original.encode()).hexdigest(),
    "compose_after_sha256": hashlib.sha256(updated.encode()).hexdigest(),
    "only_api_recreated": True,
}
(HERE / "api-activation-v3.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(
    json.dumps(
        {
            "only_api_recreated": True,
            "healthy": after["bord-food-api"]["Health"]["Status"],
            "started": after["bord-food-api"]["StartedAt"],
        }
    )
)
