"""Exercise Bòrd's existing USDA provider against a temporary synthetic loopback API.

No companion files are written. BORD_SOURCE_DIR must identify an existing checkout
with tsx installed. There is no worker, external source request, or deployment.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bord_food_api.importer import build_catalog
from bord_food_api.platform import Platform


def main():
    companion = Path(os.environ["BORD_SOURCE_DIR"]).resolve()
    executable = companion / "node_modules/.bin/tsx"
    with tempfile.TemporaryDirectory(prefix="bord-provider-smoke-") as directory:
        data = Path(directory)
        build_catalog([ROOT / "tests/fixtures/foods.json"], data / "foods.sqlite")
        Platform(data).adopt_legacy()
        policy = data / "offline.json"
        policy.write_text(
            json.dumps({"network": {"mode": "offline"}, "scheduler": {"enabled": False}})
        )
        environment = {
            **os.environ,
            "DATA_DIR": str(data),
            "IMPORT_DIR": str(data / "empty"),
            "API_KEY": "synthetic-local-key",
            "BORD_FOOD_CONFIG": str(policy),
            "AUTO_DOWNLOAD": "false",
            "PYTHONPATH": str(ROOT),
        }
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        address = f"http://127.0.0.1:{listener.getsockname()[1]}"
        code = (
            "import sys,uvicorn; from bord_food_api.api import create_app; "
            'uvicorn.run(create_app(),fd=int(sys.argv[1]),access_log=False,log_level="error")'
        )
        server = subprocess.Popen(
            [sys.executable, "-c", code, str(listener.fileno())],
            pass_fds=(listener.fileno(),),
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    with urlopen(address + "/live", timeout=1) as response:
                        assert json.load(response)["status"] == "ok"
                    break
                except (URLError, TimeoutError):
                    if server.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Temporary API failed to start") from None
                    time.sleep(0.05)
            environment.update(
                {
                    "BORD_SOURCE_DIR": str(companion),
                    "USDA_FDC_BASE_URL": address + "/fdc/v1",
                    "USDA_FDC_API_KEY": "synthetic-local-key",
                    "NODE_OPTIONS": "--conditions=react-server",
                }
            )
            result = subprocess.run(
                [
                    str(executable),
                    "--tsconfig",
                    str(companion / "tsconfig.json"),
                    str(ROOT / "scripts/verify-bord.mts"),
                ],
                env=environment,
                check=False,
                cwd=companion,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode:
                raise RuntimeError(result.stderr.strip())
            print(result.stdout.strip())
        finally:
            server.terminate()
            try:
                server.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.communicate()
            listener.close()


if __name__ == "__main__":
    main()
