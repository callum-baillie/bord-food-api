"""Scoped serving update after actual-image offline preflight. No image publication."""

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
r = json.loads((HERE.parent / "iowa-fields-20261020/current-release.json").read_text())
assert (
    json.loads((HERE / "revised-offline-plan.json").read_text())["actual_image_preflight"]
    == "passed"
)


def cmd(args, body=None):
    return subprocess.run(
        SSH + [shlex.join(args)], input=body, capture_output=True, check=True, timeout=180
    ).stdout


before = {
    n: json.loads(cmd(["docker", "inspect", "--format", "{{json .State}}", n]))
    for n in ["bord-food-api", "Bord", "bord-food-crawl-history"]
}
assert (
    cmd(["docker", "inspect", "--format", "{{.Image}}", "bord-food-api"]).decode().strip()
    == r["image_id"]
)
path = "/mnt/cache/git/compose/productivity/compose.yaml"
original = cmd(["cat", path]).decode()
local = TOWER / "stacks/productivity/compose.yaml"
source = local.read_text()
modules = [
    "platform",
    "store_enrichment",
    "chain_profiles",
    "store_quality",
    "store_hours",
    "store_sources",
]


def patch(text):
    match = re.search(
        r"^  bord-food-api:\n.*?(?=^  [a-zA-Z0-9_-]+:|\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert match
    block = match[0]
    for module in modules:
        target = f"/app/bord_food_api/{module}.py:ro"
        new = f"      - ./config/crawl-field-releases/{r['release'].rsplit('/', 1)[1]}/bord_food_api/{module}.py:{target}\n"
        lines = re.findall(r"^      - .+:" + re.escape(target) + r"\n", block, re.MULTILINE)
        assert len(lines) <= 1
        if lines:
            block = block.replace(lines[0], new)
        else:
            anchor = re.search(
                r"^      - .+:/app/bord_food_api/store_enrichment.py:ro\n", block, re.MULTILINE
            )[0]
            block = block.replace(anchor, anchor + new)
    return text[: match.start()] + block + text[match.end() :]


updated = patch(original)
source_updated = patch(source)
cmd(["tee", "/tmp/bord-quality-compose.yaml"], updated.encode())
script = f"""set -eu
cd /mnt/cache/git/compose/productivity
test "$(sha256sum compose.yaml | cut -d' ' -f1)" = {hashlib.sha256(original.encode()).hexdigest()}
cp compose.yaml /mnt/cache/appdata/bord-food-api/backups/20261020-before-contact-improvements/compose-before-quality.yaml
install -m 644 /tmp/bord-quality-compose.yaml compose.yaml.next-quality
docker compose --env-file .env -p tower-productivity -f compose.yaml.next-quality config --quiet
mv compose.yaml.next-quality compose.yaml
docker compose --env-file .env -p tower-productivity -f compose.yaml up -d --no-deps --wait --wait-timeout 120 bord-food-api
"""
cmd(["bash", "-s"], script.encode())
local.write_text(source_updated)
after = {
    n: json.loads(cmd(["docker", "inspect", "--format", "{{json .State}}", n])) for n in before
}
assert all(
    before[n]["StartedAt"] == after[n]["StartedAt"] for n in ["Bord", "bord-food-crawl-history"]
)
receipt = {
    "release": r["release"],
    "image_id": r["image_id"],
    "modules": modules,
    "only_api_recreated": True,
    "before": before,
    "after": after,
}
(HERE / "api-activation.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(
    json.dumps({"healthy": after["bord-food-api"]["Health"]["Status"], "only_api_recreated": True})
)
