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

root = Path("/home/callum/Documents/GitHub/bord-food-api")
here = root / "docs/investigations/store-enrichment-20261020"
old = json.loads((here / "import-launch-r3.json").read_text())
files = {
    name: root / "bord_food_api" / name
    for name in ["control.py", "platform.py", "refresh.py", "store_enrichment.py", "store_hours.py"]
}
files["enrich-retained-stores.py"] = root / "scripts/enrich-retained-stores.py"
digest = hashlib.sha256()
for name, path in sorted(files.items()):
    digest.update(name.encode() + b"\0" + path.read_bytes())
release = "/mnt/cache/git/compose/productivity/config/operator-releases/" + digest.hexdigest()
archive = io.BytesIO()
with tarfile.open(fileobj=archive, mode="w") as tar:
    for name, path in files.items():
        tar.add(path, arcname=name, recursive=False)
for cmd, data in [
    (["mkdir", "-p", release], None),
    (["tar", "-xf", "-", "-C", release], archive.getvalue()),
]:
    subprocess.run(SSH + [shlex.join(cmd)], input=data, capture_output=True, check=True)
new = {
    "release": release,
    "previous_release": old["release"],
    "image_id": old["image_id"],
    "files": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()},
}
(here / "field-support-release.json").write_text(json.dumps(new, indent=2) + "\n")
print(new)
