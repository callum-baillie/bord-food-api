"""Stage an immutable operator release; validate offline before a scoped pilot launch."""

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

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
TOWER = Path("/home/callum/Documents/Projects/Tower/tower/Tower-build")


def remote(args, data=None):
    p = subprocess.run(
        SSH + [shlex.join(args)], input=data, capture_output=True, timeout=120, check=False
    )
    if p.returncode:
        raise RuntimeError(p.stderr.decode()[-3000:] + p.stdout.decode()[-3000:])
    return p.stdout


def main(config_path, launch=False, stage_only=False):
    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    files = {
        str(p.relative_to(ROOT)): p.read_bytes() for p in (ROOT / "bord_food_api").glob("*.py")
    }
    for name in [
        "quality-stores.py",
        "run-store-field-plan.py",
        "run-small-states.py",
        "discover-store-sites.py",
        "state-batch.py",
        "plan-iowa-places.py",
        "replay-crawl-fields.py",
        "enrich-retained-stores.py",
        "run-iowa-fields.py",
        "run-iowa-fields-campaign.py",
        "run-iowa-statewide.py",
        "run-iowa-crawl.py",
        "run-reviewed-crawl.py",
    ]:
        files["scripts/" + name] = (ROOT / "scripts" / name).read_bytes()
    digest = hashlib.sha256()
    for name, body in sorted(files.items()):
        digest.update(name.encode() + b"\0" + body)
    relative = "config/crawl-field-releases/" + digest.hexdigest()
    release = "/mnt/cache/git/compose/productivity/" + relative
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(body))
    remote(["mkdir", "-p", release])
    remote(["tar", "-xf", "-", "-C", release], archive.getvalue())
    for name, body in files.items():
        p = TOWER / "stacks/productivity" / relative / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    config_dir = "/mnt/cache/git/compose/productivity/config/iowa-fields/" + config["campaign_id"]
    remote(["mkdir", "-p", config_dir])
    remote(["tee", config_dir + "/crawl.json"], config_path.read_bytes())
    p = TOWER / "stacks/productivity/config/iowa-fields" / config["campaign_id"] / "crawl.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(config_path.read_bytes())
    image = "sha256:169264bb538c8add672750b01d0124489237e1cc7379c24975915466a8e3ded3"
    if stage_only:
        result = {"release": release, "image_id": image, "launched": False}
        (HERE / "current-release.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return
    cmd = [
        "docker",
        "run",
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
        "/tmp:rw,noexec,nosuid,size=32m",
        "--mount",
        "type=bind,src=/mnt/cache/appdata/bord-food-api,dst=/data",
        "--mount",
        f"type=bind,src={release},dst=/operator-release,readonly",
        "--mount",
        f"type=bind,src={config_dir}/crawl.json,dst=/config/crawl.json,readonly",
    ]
    entry = (
        "scripts/run-iowa-fields-campaign.py"
        if config.get("canonical_followup_enabled") is True
        else "scripts/run-iowa-fields.py"
    )
    plan = json.loads(
        remote(
            cmd[:2] + ["--rm", "--network", "none"] + cmd[2:] + [image, entry, "/config/crawl.json"]
        )
    )
    result = {
        "campaign_id": config["campaign_id"],
        "release": release,
        "image_id": image,
        "plan": plan,
        "launched": False,
    }
    if launch:
        worker = (
            cmd[:2]
            + ["-d", "--name", "bord-food-" + config["campaign_id"]]
            + cmd[2:]
            + [
                "--mount",
                "type=bind,src=/mnt/cache/appdata/bord-food-crawl-secrets/jev-api-key,dst=/run/secrets/jev-api-key,readonly",
                image,
                entry,
                "/config/crawl.json",
                "--run",
            ]
        )
        result.update(launched=True, container_id=remote(worker).decode().strip())
    (HERE / (config["campaign_id"] + "-launch.json")).write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main(sys.argv[1], "--launch" in sys.argv[2:], "--stage-only" in sys.argv[2:])
