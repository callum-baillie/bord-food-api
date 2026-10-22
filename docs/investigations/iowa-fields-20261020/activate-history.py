"""Update only the network-disabled failure observer's outcome parser."""

import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/bord-iowa-expand")
from remote import SSH

HERE = Path(__file__).parent
TOWER = Path("/home/callum/Documents/Projects/Tower/tower/Tower-build")
r = json.loads((HERE / "current-release.json").read_text())


def cmd(args, body=None):
    return subprocess.run(
        SSH + [shlex.join(args)], input=body, capture_output=True, check=True, timeout=180
    ).stdout


states = {
    n: json.loads(cmd(["docker", "inspect", "--format", "{{json .State}}", n]))
    for n in ["bord-food-api", "Bord", "bord-food-crawl-history"]
}
path = "/mnt/cache/git/compose/productivity/compose.crawl-history.yaml"
original = cmd(["cat", path]).decode()
local = TOWER / "stacks/productivity/compose.crawl-history.yaml"
source = local.read_text()
assert original.count(":/observer:ro") == source.count(":/observer:ro") == 1
new = (
    "      - ./config/crawl-field-releases/"
    + r["release"].rsplit("/", 1)[1]
    + "/bord_food_api/crawl_history.py:/observer/bord_food_api/crawl_history.py:ro\n"
)


def replace_overlay(text):
    lines = text.splitlines(keepends=True)
    matches = [line for line in lines if ":/observer/bord_food_api/crawl_history.py:" in line]
    assert len(matches) <= 1
    if matches:
        return text.replace(matches[0], new)
    return text.replace("    read_only: true\n", new + "    read_only: true\n")


updated = replace_overlay(original)
source_updated = replace_overlay(source)
assert "network_mode: none" in updated
cmd(["tee", "/tmp/bord-iowa-fields-history.yaml"], updated.encode())
script = f"""set -eu
cd /mnt/cache/git/compose/productivity
test "$(sha256sum compose.crawl-history.yaml | cut -d' ' -f1)" = {hashlib.sha256(original.encode()).hexdigest()}
cp compose.crawl-history.yaml /mnt/cache/appdata/bord-food-api/backups/20261020-before-iowa-fields/history-compose-before-final.yaml
install -m 644 /tmp/bord-iowa-fields-history.yaml compose.crawl-history.yaml.next
docker compose --env-file .env -p tower-productivity -f compose.yaml -f compose.crawl-history.yaml.next --profile crawl-history config --quiet
mv compose.crawl-history.yaml.next compose.crawl-history.yaml
docker compose --env-file .env -p tower-productivity -f compose.yaml -f compose.crawl-history.yaml --profile crawl-history up -d --no-deps --wait --wait-timeout 120 bord-food-crawl-history
"""
cmd(["bash", "-s"], script.encode())
local.write_text(source_updated)
after = {
    n: json.loads(cmd(["docker", "inspect", "--format", "{{json .State}}", n])) for n in states
}
assert all(states[n]["StartedAt"] == after[n]["StartedAt"] for n in ["Bord", "bord-food-api"])
receipt = {
    "release": r["release"],
    "network": "none",
    "before": states,
    "after": after,
    "only_history_recreated": True,
}
(HERE / "history-activation-final.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(
    json.dumps(
        {
            "only_history_recreated": True,
            "healthy": after["bord-food-crawl-history"]["Health"]["Status"],
        }
    )
)
