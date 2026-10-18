"""Discover the newest official JSON releases; download ZIPs without unpacking them."""

import hashlib
import json
import logging
import os
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zipfile import ZipFile

PAGE = "https://fdc.nal.usda.gov/download-datasets/"
PATTERN = re.compile(
    r"FoodData_Central_(branded|foundation|survey|sr_legacy)_food_json_"
    r"(\d{4}-\d{2}(?:-\d{2})?)\.zip$",
    re.IGNORECASE,
)
LOG = logging.getLogger(__name__)


class DownloadLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(urljoin(PAGE, href))


def discover(html: str) -> dict[str, str]:
    parser = DownloadLinks()
    parser.feed(html)
    releases = {}
    for url in parser.links:
        parsed = urlparse(url)
        match = PATTERN.search(parsed.path)
        if parsed.scheme != "https" or parsed.hostname != "fdc.nal.usda.gov" or not match:
            continue
        name, date = match.groups()
        name = "fndds" if name.lower() == "survey" else name.lower()
        if name not in releases or date > releases[name][0]:
            releases[name] = (date, url)
    return {name: value[1] for name, value in releases.items()}


def open_url(url: str):
    from .transport import Transport

    return Transport(
        {
            "mode": "bulk_only",
            "origins": ["https://fdc.nal.usda.gov"],
            "max_artifact_bytes": 20 * 1024**3,
        }
    ).get(url)


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download_datasets(
    names: tuple[str, ...], directory: Path, force=False, *, transport=None
) -> list[Path]:
    def request(url):
        return transport.get(url) if transport is not None else open_url(url)

    with request(PAGE) as response:
        releases = discover(response.read(4 * 1024 * 1024).decode("utf-8"))
    missing = set(names) - releases.keys()
    if missing:
        raise ValueError(
            f"No official JSON download found for {sorted(missing)}; supply local ZIPs instead"
        )
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        url = releases[name]
        target = directory / Path(urlparse(url).path).name
        manifest = target.with_suffix(target.suffix + ".source.json")
        if target.exists() and manifest.exists() and not force:
            saved = json.loads(manifest.read_text())
            if saved.get("url") == url and saved.get("sha256") == sha256(target):
                LOG.info("Reusing verified download %s", target.name)
                paths.append(target)
                continue
        LOG.info("Downloading dataset %s", name)
        fd, temp_name = tempfile.mkstemp(prefix="download-", suffix=".part", dir=directory)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as output, request(url) as response:
                expected = response.headers.get("Content-Length")
                received = 0
                progress = 0
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    received += len(chunk)
                    if received > 20 * 1024**3:
                        raise ValueError("Download exceeds artifact byte limit")
                    if received - progress >= 50 * 1024 * 1024:
                        LOG.info("Downloaded %s: %d MiB", name, received // (1024 * 1024))
                        progress = received
                if expected and received != int(expected):
                    raise ValueError(f"Incomplete download for {name}")
                output.flush()
                os.fsync(output.fileno())
            from .transport import validate_zip

            validate_zip(temp)
            with ZipFile(temp) as archive:
                if not any(item.filename.lower().endswith(".json") for item in archive.infolist()):
                    raise ValueError(f"Download for {name} contains no JSON")
            digest = sha256(temp)
            os.replace(temp, target)
            manifest.write_text(json.dumps({"url": url, "sha256": digest}, indent=2) + "\n")
            paths.append(target)
        finally:
            temp.unlink(missing_ok=True)
    return paths
