"""Build/run the real image against synthetic data, then remove the test container."""

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, text=True, **kwargs)


def main():
    image = os.getenv("BORD_SMOKE_IMAGE", "bord-food-api:local")
    docker("build", "-t", image, str(ROOT))
    name = "bord-food-api-smoke-" + uuid.uuid4().hex[:10]
    volume = name + "-data"
    with tempfile.TemporaryDirectory(prefix="bord-food-api-smoke-") as temporary:
        directory = Path(temporary)
        (directory / "imports").mkdir()
        policy = directory / "offline.json"
        policy.write_text(
            json.dumps({"network": {"mode": "offline"}, "scheduler": {"enabled": False}})
        )
        shutil.copy(ROOT / "tests/fixtures/foods.json", directory / "imports/foods.json")
        try:
            docker(
                "run",
                "-d",
                "--rm",
                "--name",
                name,
                "-p",
                "127.0.0.1::8080",
                "-e",
                "API_KEY=smoke-local-key",
                "-e",
                "AUTO_DOWNLOAD=false",
                "-e",
                "BORD_FOOD_CONFIG=/offline.json",
                "--mount",
                f"type=volume,src={volume},dst=/data",
                "--mount",
                f"type=bind,src={directory / 'imports'},dst=/imports,readonly",
                "--mount",
                f"type=bind,src={policy},dst=/offline.json,readonly",
                image,
                capture_output=True,
            )
            address = docker("port", name, "8080/tcp", capture_output=True).stdout.strip()

            def request(path, body=None, key="smoke-local-key"):
                headers = {"X-Api-Key": key, "Content-Type": "application/json"}
                payload = json.dumps(body).encode() if body is not None else None
                with urlopen(
                    Request("http://" + address + path, data=payload, headers=headers), timeout=5
                ) as response:
                    return json.load(response)

            deadline = time.monotonic() + 45
            while True:
                try:
                    assert request("/live")["status"] == "ok"
                    assert request("/health")["totalFoods"] == 6
                    break
                except (URLError, OSError):
                    if time.monotonic() > deadline:
                        raise RuntimeError("Container did not become ready") from None
                    time.sleep(0.25)
            try:
                request("/fdc/v1/food/101", key="wrong")
                raise AssertionError("Wrong key was accepted")
            except HTTPError as error:
                assert error.code == 401
            search = request(
                "/fdc/v1/foods/search",
                {"query": "oats", "dataType": ["Foundation", "Survey (FNDDS)"]},
            )
            assert search["totalHits"] == 2
            assert request("/fdc/v1/food/101")["foodNutrients"][1]["amount"] == 0
            (directory / "imports/broken.json").write_text("[")
            failed = subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "python",
                    "-m",
                    "bord_food_api",
                    "import",
                    "/imports/broken.json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            assert failed.returncode != 0
            assert request("/health")["totalFoods"] == 6
            fixture = json.loads((directory / "imports/foods.json").read_text())
            (directory / "imports/replacement.json").write_text(json.dumps([fixture[-1]]))
            docker(
                "exec",
                name,
                "python",
                "-m",
                "bord_food_api",
                "import",
                "/imports/replacement.json",
                capture_output=True,
            )
            assert request("/health")["totalFoods"] == 1
            assert request("/fdc/v1/foods/search", {"query": "cocoa"})["totalHits"] == 1
            # The next startup must work with only the persisted database and no source files.
            for path in (directory / "imports").iterdir():
                path.unlink()
            docker("restart", name, capture_output=True)
            address = docker("port", name, "8080/tcp", capture_output=True).stdout.strip()
            deadline = time.monotonic() + 30
            while True:
                try:
                    assert request("/health")["totalFoods"] == 1
                    break
                except (URLError, OSError):
                    if time.monotonic() > deadline:
                        raise RuntimeError("Container did not restart") from None
                    time.sleep(0.25)
            print(
                "PASS: Docker boot, search, details, auth, failed import, atomic replacement, persisted restart"
            )
        except Exception:
            subprocess.run(["docker", "logs", name], check=False)
            raise
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True, check=False)


if __name__ == "__main__":
    main()
