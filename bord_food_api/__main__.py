import argparse
import json
import logging
import os
from pathlib import Path

from .catalog import connect, metadata
from .download import download_datasets
from .importer import build_catalog, import_lock
from .settings import Settings


def local_sources(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.glob("*")
        if path.is_file()
        and path.suffix.lower() in {".json", ".zip"}
        and not path.name.endswith(".source.json")
    )


def main():
    parser = argparse.ArgumentParser(description="Local USDA FoodData Central API")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="Build a catalog on first start, then serve the API")
    importing = commands.add_parser("import", help="Replace the catalog from local JSON/ZIP files")
    importing.add_argument("paths", type=Path, nargs="*", help="Defaults to files in IMPORT_DIR")
    refresh = commands.add_parser(
        "refresh", help="Download selected USDA releases and replace the catalog"
    )
    refresh.add_argument(
        "--force-download", action="store_true", help="Redownload even verified cached archives"
    )
    commands.add_parser("status", help="Print catalog provenance and record counts")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    command = args.command or "serve"
    if command == "status":
        with connect(settings.database) as connection:
            print(json.dumps(metadata(connection), indent=2))
        return
    if command in {"refresh", "import"} or not settings.database.exists():
        with import_lock(settings.data_dir):
            # Another starter may have finished while this process was starting.
            if command != "serve" or not settings.database.exists():
                if command == "refresh":
                    paths = download_datasets(
                        settings.datasets, settings.data_dir / "downloads", args.force_download
                    )
                else:
                    paths = (
                        args.paths
                        if command == "import" and args.paths
                        else local_sources(settings.import_dir)
                    )
                    if not paths and command == "serve" and settings.auto_download:
                        paths = download_datasets(
                            settings.datasets, settings.data_dir / "downloads"
                        )
                if not paths:
                    raise ValueError(
                        "No source files found. Supply .json/.zip files in IMPORT_DIR or set AUTO_DOWNLOAD=true."
                    )
                build_catalog(paths, settings.database)
    if command == "serve":
        # Fail clearly on an incompatible/corrupt catalog instead of silently downloading again.
        with connect(settings.database) as connection:
            metadata(connection)
        import uvicorn

        from .api import create_app

        uvicorn.run(
            create_app(settings),
            host="0.0.0.0",
            port=int(os.getenv("PORT", "8080")),
            access_log=False,
            proxy_headers=False,
        )


if __name__ == "__main__":
    main()
