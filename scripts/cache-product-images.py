"""Explicit barcode-matched bulk image acquisition; never modifies food catalog packs."""

import argparse
import gzip
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bord_food_api.platform import Platform
from bord_food_api.product_images import ImageCache, ImageUnavailable, image_policy
from bord_food_api.settings import Settings, load_policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, help="Retained OFF JSONL/.gz or {products: [...]} JSON"
    )
    parser.add_argument("--gtin", action="append", default=[])
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument(
        "--api-fallback", action="store_true", help="Also use the paced API for bulk misses"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000 or not 1 <= args.max_seconds <= 86400:
        parser.error("Use bounded limit and duration")
    settings = Settings()
    platform = Platform(settings.data_dir)
    cache = ImageCache(
        settings.data_dir,
        image_policy(load_policy(settings)),
        denied=platform.control.hidden_sources,
    )
    cache.policy["api_fallback"] = cache.policy["api_fallback"] and args.api_fallback
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "plan",
                    "manifest": str(args.manifest) if args.manifest else None,
                    "max_images": args.limit,
                    "max_seconds": args.max_seconds,
                    "api_fallback": cache.policy["api_fallback"],
                    "catalog_writes": 0,
                }
            )
        )
        return
    if args.manifest:
        import hashlib

        import ijson

        def records():
            opening = gzip.open if args.manifest.suffix == ".gz" else open
            with opening(args.manifest, "rb") as source:
                if args.manifest.suffix == ".json":
                    first = source.read(4096).lstrip()[:1]
                    source.seek(0)
                    if first not in (b"[", b"{"):
                        raise ValueError("Expected a JSON product array/object")
                    yield from ijson.items(
                        source, "item" if first == b"[" else "products.item", use_float=True
                    )
                else:
                    for line in source:
                        if line.strip():
                            yield json.loads(line)

        with args.manifest.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        imported = cache.import_references(
            records(), provenance={"file": args.manifest.name, "sha256": digest}
        )
        print(json.dumps({"phase": "references_published", **imported}), flush=True)
    targets = args.gtin
    if not targets:
        from bord_food_api.platform import _sqlite

        path = cache.root / "references.sqlite"
        if not path.exists():
            raise ValueError("Provide a manifest or barcode targets")
        with _sqlite(path.as_uri() + "?mode=ro", uri=True) as db:
            targets = [
                row[0]
                for row in db.execute(
                    "SELECT gtin FROM references_index ORDER BY gtin LIMIT ?", (args.limit,)
                )
            ]
    started = time.monotonic()
    counts = {"cached": 0, "missing": 0, "deferred": 0}
    for gtin in targets[: args.limit]:
        if time.monotonic() - started >= args.max_seconds:
            break
        try:
            _, meta = cache.get(gtin)
            counts["cached"] += 1
            print(
                json.dumps({"gtin": meta["gtin"], "state": "cached", "bytes": meta["bytes"]}),
                flush=True,
            )
        except ImageUnavailable as error:
            counts["missing" if error.missing else "deferred"] += 1
            print(
                json.dumps(
                    {
                        "gtin": gtin,
                        "state": "missing" if error.missing else "deferred",
                        "reason": error.reason,
                        "retry_after": error.retry_after,
                    }
                ),
                flush=True,
            )
        # CDN image requests are serial and paced; API misses have their own durable gate.
        time.sleep(1)
    print(
        json.dumps(
            {
                "state": "complete",
                "counts": counts,
                "cache": cache.status(),
                "elapsed_seconds": time.monotonic() - started,
                "catalog_writes": 0,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
