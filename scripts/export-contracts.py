"""Generate authoritative OpenAPI offline, or verify the checked-in contract."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bord_food_api.api import create_app
from bord_food_api.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="bord-contract-") as directory:
        app = create_app(Settings(data_dir=Path(directory), auto_download=False))
        schema = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path = ROOT / "contracts" / "openapi.json"
    if args.check:
        if not path.exists() or path.read_text() != schema:
            raise SystemExit("OpenAPI contract differs; run scripts/export-contracts.py")
        print("OpenAPI contract matches FastAPI")
    else:
        path.parent.mkdir(exist_ok=True)
        path.write_text(schema)
        print("Wrote contracts/openapi.json")


if __name__ == "__main__":
    main()
