"""Owner-authorized isolated Unraid import launcher; fixed files, no secrets in output."""

import argparse
import hashlib
import io
import json
import shlex
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILES = {
    "control.py": "bord_food_api/control.py",
    "platform.py": "bord_food_api/platform.py",
    "refresh.py": "bord_food_api/refresh.py",
    "store_enrichment.py": "bord_food_api/store_enrichment.py",
    "store_hours.py": "bord_food_api/store_hours.py",
    "store_sources.py": "bord_food_api/store_sources.py",
    "store_microdata.py": "bord_food_api/store_microdata.py",
    "store_discovery.py": "bord_food_api/store_discovery.py",
    "crawl_evidence.py": "bord_food_api/crawl_evidence.py",
    "operator_products.py": "bord_food_api/operator_products.py",
    "import-retained-products.py": "scripts/import-retained-products.py",
    "enrich-retained-stores.py": "scripts/enrich-retained-stores.py",
    "official-chart.json": "docs/investigations/store-enrichment-20261020/official-cold-storage-chart.json",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--identity", required=True)
    args = parser.parse_args()
    ssh = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=10",
        "-i",
        args.identity,
        args.host,
    ]

    def run(argv, *, input=None):
        result = subprocess.run(
            ssh + [shlex.join(argv)], input=input, capture_output=True, check=True, timeout=300
        )
        return result.stdout.decode().strip()

    digest = hashlib.sha256()
    for name, relative in sorted(FILES.items()):
        digest.update(name.encode() + b"\0" + (ROOT / relative).read_bytes())
    release = "/mnt/cache/git/compose/productivity/config/operator-releases/" + digest.hexdigest()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name, relative in FILES.items():
            tar.add(ROOT / relative, arcname=name, recursive=False)
    run(["mkdir", "-p", release])
    run(["tar", "-xf", "-", "-C", release], input=archive.getvalue())
    image = run(["docker", "inspect", "--format", "{{.Image}}", "bord-food-api"])
    backup = "/data/backups/20261020-before-products-enrichment"
    code = (
        "from bord_food_api.platform import Platform; import json; from pathlib import Path; p=Platform('/data'); b=Path("
        + repr(backup)
        + "); assert not b.exists() or json.loads((b/'current.json').read_text())['generation']==p.current()['generation']; print(json.dumps({'status':'existing_verified','generation':p.current()['generation']} if b.exists() else p.backup(b)))"
    )
    backup_result = run(["docker", "exec", "bord-food-api", "python", "-c", code])
    print("backup", backup_result, flush=True)
    worker = [
        "docker",
        "run",
        "--name",
        "bord-food-retained-import-20261020-r3",
        "--network",
        "none",
        "--entrypoint",
        "python",
        "--env",
        "PYTHONPATH=/app",
        "--no-healthcheck",
        "--memory",
        "2g",
        "--cpus",
        "1.5",
        "--user",
        "99:100",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=32m",
        "--mount",
        "type=bind,src=/mnt/cache/appdata/bord-food-api,dst=/data",
    ]
    for name in FILES:
        destination = (
            "/app/bord_food_api/" + name
            if name.endswith(".py")
            and name not in {"import-retained-products.py", "enrich-retained-stores.py"}
            else "/operator/" + name
        )
        worker.extend(["--mount", f"type=bind,src={release}/{name},dst={destination},readonly"])
    command = [
        "/operator/import-retained-products.py",
        "--data-dir",
        "/data",
        "--run-dir",
        "/data/operator-imports/us-products-20261020-r3",
        "--usda-products",
        "--off",
        "/data/downloads/open_food_facts/57fa7d1994038dcf3c9ec9c9700d4d476b699e533c85a0d2fbdba2ffbf94dccd.jsonl.gz",
        "--off-sha256",
        "1e8cbd8e00d78d42ed2cf419dd4020964cb37621076a67ee31667913be99ae37",
        "--storage-chart",
        "/operator/official-chart.json",
    ]
    probe = [v for v in worker]
    probe[probe.index("bord-food-retained-import-20261020-r3")] = (
        "bord-food-retained-import-plan-20261020"
    )
    probe.insert(2, "--rm")
    plan = run(probe + [image, *command])
    print("plan", plan, flush=True)
    launched = run(worker[:2] + ["-d"] + worker[2:] + [image, *command, "--apply"])
    receipt = {
        "release": release,
        "image_id": image,
        "container_id": launched,
        "backup": backup,
        "plan": json.loads(plan),
        "source_network": False,
        "paid_calls": 0,
    }
    (Path(__file__).parent / "import-launch-r3.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
