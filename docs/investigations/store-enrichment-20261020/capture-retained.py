"""Read-only public-business evidence snapshot; stdout is a gzip tar archive."""

import io
import json
import pathlib
import sys
import tarfile

root = pathlib.Path("/data")
raw = (root / "current.json").read_bytes()
manifest = json.loads(raw)
pack = pathlib.Path(manifest["packs"]["stores"])
if pack.parts[:2] != ("objects", "catalogs") or pack.suffix != ".sqlite":
    raise ValueError("invalid_pack")
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as out:
    entry = tarfile.TarInfo("current.json")
    entry.size = len(raw)
    out.addfile(entry, io.BytesIO(raw))
    out.add(root / pack, arcname=str(pack), recursive=False)
    for pattern in (
        "discovery/*/bundle.json",
        "discovery/*/candidates.jsonl",
        "discovery/*/crosswalk.jsonl",
        "crawl-campaigns/*/evidence/*.json",
    ):
        for path in sorted(root.glob(pattern)):
            if path.is_file() and not path.is_symlink():
                out.add(path, arcname=str(path.relative_to(root)), recursive=False)
