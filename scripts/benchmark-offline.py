"""Small synthetic benchmark; reports this host/corpus only, no source network."""

import json
import os
import platform
import resource
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from bord_food_api.api import create_app
from bord_food_api.platform import Platform
from bord_food_api.settings import Settings


def main():
    with tempfile.TemporaryDirectory(prefix="bord-offline-benchmark-") as directory:
        data = Path(directory)

        def rss():
            return int(
                next(
                    line.split()[1]
                    for line in Path("/proc/self/status").read_text().splitlines()
                    if line.startswith("VmRSS:")
                )
            )

        rss_phases = {"initial": rss()}
        catalog = Platform(data)
        stop = threading.Event()
        peak_staging = [0]

        def monitor():
            while not stop.wait(0.01):
                try:
                    peak_staging[0] = max(
                        peak_staging[0],
                        sum(p.stat().st_size for p in (data / "staging").rglob("*") if p.is_file()),
                    )
                except FileNotFoundError:
                    pass

        count = 1000

        def records():
            for number in range(count):
                yield {
                    "kind": "store",
                    "source_key": str(number),
                    "payload": {
                        "name": f"Synthetic benchmark market {number}",
                        "chain_key": "synthetic",
                        "address": {"street": f"{number} Fixture Lane", "region": "IA"},
                        "latitude": 42 + number / 100000,
                        "longitude": -91,
                    },
                }

        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()
        started = time.monotonic()
        imported = catalog.sync("synthetic_benchmark", "stores", "r1", records())
        build_seconds = time.monotonic() - started
        rss_phases["after_build"] = rss()
        replay = catalog.sync("synthetic_benchmark", "stores", "r2", records())
        rss_phases["after_replay"] = rss()
        stop.set()
        watcher.join()
        store_id = next(catalog.iter_records("store"))["id"]
        timings = {"lookup_ms": [], "store_search_ms": []}
        with TestClient(
            create_app(Settings(data_dir=data, api_key="", auto_download=False))
        ) as client:
            for _ in range(50):
                for name, path in [
                    ("lookup_ms", f"/v1/stores/{store_id}"),
                    (
                        "store_search_ms",
                        "/v1/stores?query=benchmark&lat=42&lon=-91&radius_km=10&limit=20",
                    ),
                ]:
                    before = time.perf_counter()
                    response = client.get(path)
                    assert response.status_code == 200
                    timings[name].append((time.perf_counter() - before) * 1000)
        rss_phases["after_queries"] = rss()
        print(
            json.dumps(
                {
                    "corpus": "1000 synthetic stores; one synthetic chain; concurrency=1; 50 requests/query",
                    "python": platform.python_version(),
                    "platform": platform.system(),
                    "logical_cpus_visible": os.cpu_count(),
                    "build_seconds": round(build_seconds, 3),
                    "changed": imported["changed"],
                    "replay_unchanged": replay["unchanged"],
                    "source_bytes_transferred": 0,
                    "retailer_detail_requests": 0,
                    "rss_phases_kib": rss_phases,
                    "peak_rss_kib": int(
                        next(
                            line.split()[1]
                            for line in Path("/proc/self/status").read_text().splitlines()
                            if line.startswith("VmHWM:")
                        )
                    )
                    if Path("/proc/self/status").exists()
                    else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "sampled_peak_staging_bytes": peak_staging[0],
                    "disk_bytes": sum(p.stat().st_size for p in data.rglob("*") if p.is_file()),
                    "p95_ms": {
                        name: round(statistics.quantiles(values, n=100)[94], 3)
                        for name, values in timings.items()
                    },
                    "limitation": "In-process TestClient on this host, not the proposed 2-vCPU/4-GiB or national dataset benchmark.",
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
