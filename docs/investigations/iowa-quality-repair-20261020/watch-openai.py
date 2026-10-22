"""One authorized Iowa batch collector/importer; no resubmission or additional inference."""

import io
import json
import shlex
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from bord_food_api.platform import atomic_json
from bord_food_api.state_batch import Client

HERE = Path(__file__).parent
DIRECTORY = Path("/tmp/iowa-quality-openai/IA-quality-pilot-20261020")
SSH = [
    "ssh",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "ConnectTimeout=10",
    "-i",
    "/home/callum/Documents/Projects/Tower/tower/Tower-build/secrets/keys/ssh/tower-agent",
    "root@192.168.0.10",
]


def remote(args, body=None, timeout=600):
    result = subprocess.run(
        SSH + [shlex.join(args)], input=body, capture_output=True, timeout=timeout, check=False
    )
    if result.returncode:
        raise RuntimeError("remote_operator_failed")
    return result.stdout


def import_on_unraid():
    release = json.loads(
        (ROOT / "docs/investigations/iowa-fields-20261020/current-release.json").read_text()
    )["release"]
    destination = (
        "/mnt/cache/appdata/bord-food-api/operator-imports/openai-IA-quality-pilot-20261020"
    )
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name in ["plan.json", "output.jsonl", "status.json"]:
            body = (DIRECTORY / name).read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o600
            info.uid = 99
            info.gid = 100
            tar.addfile(info, io.BytesIO(body))
    remote(["mkdir", "-p", destination])
    remote(["tar", "-xf", "-", "-C", destination], archive.getvalue())
    remote(["chown", "99:100", destination])
    code = """import json,time
from pathlib import Path
from bord_food_api.platform import Platform,atomic_json
from bord_food_api.runtime import heavy_lock
from bord_food_api.state_batch import import_results
root=Path('/data');d=root/'operator-imports/openai-IA-quality-pilot-20261020'
for attempt in range(60):
 try:
  with heavy_lock(root):
   if (d/'import.json').exists():result=json.loads((d/'import.json').read_text())
   else:
    result=import_results(Platform(root),json.loads((d/'plan.json').read_text()),(d/'output.jsonl').read_text().splitlines(),now=time.time());atomic_json(d/'import.json',result)
  break
 except BlockingIOError:time.sleep(5)
else:raise RuntimeError('worker_slot_timeout')
print(json.dumps({'state':'import_completed','changed':result['changed'],'accepted':len(result['accepted']),'held':len(result['held']),'held_reasons':dict(__import__('collections').Counter(r['reason'] for r in result['held'])),'generation':result['generation']}))
"""
    args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--entrypoint",
        "python",
        "--workdir",
        "/operator-release",
        "--env",
        "PYTHONPATH=/operator-release:/app",
        "--no-healthcheck",
        "--memory",
        "1g",
        "--cpus",
        "1",
        "--user",
        "99:100",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=128m",
        "--mount",
        "type=bind,src=/mnt/cache/appdata/bord-food-api,dst=/data",
        "--mount",
        f"type=bind,src={release},dst=/operator-release,readonly",
        "sha256:169264bb538c8add672750b01d0124489237e1cc7379c24975915466a8e3ded3",
        "-c",
        code,
    ]
    return json.loads(remote(args))


def main():
    key = None
    for line in (
        Path("/home/callum/Documents/GitHub/food-api-viewer/.env.local").read_text().splitlines()
    ):
        if line.startswith("OPENAI_API_KEY="):
            key = line.split("=", 1)[1].strip().strip("\"'")
    client = Client(key)
    deadline = time.time() + 26 * 3600
    try:
        while time.time() < deadline:
            status = client.collect(DIRECTORY)
            atomic_json(HERE / "openai-runtime.json", status)
            if status["state"] in {"completed", "expired", "cancelled", "failed"}:
                if (DIRECTORY / "output.jsonl").exists():
                    receipt = import_on_unraid()
                else:
                    receipt = {
                        "state": "terminal_no_output",
                        "provider_state": status["state"],
                        "changed": 0,
                    }
                atomic_json(HERE / "openai-import.json", receipt)
                print(json.dumps(receipt), flush=True)
                return
            time.sleep(60)
        atomic_json(HERE / "openai-import.json", {"state": "collector_deadline", "changed": 0})
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        atomic_json(
            HERE / "openai-import.json",
            {
                "state": "collector_requires_review",
                "error_type": type(error).__name__,
                "changed": 0,
            },
        )
        print(
            json.dumps({"state": "collector_requires_review", "error_type": type(error).__name__}),
            flush=True,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
