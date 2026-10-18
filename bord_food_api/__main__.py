"""Read server, acquisition worker, and network-free operator inspection."""

import argparse
import json
import logging
import os
import time
from pathlib import Path

from .catalog import connect, metadata
from .runtime import (
    apply_rights_policy,
    crawl_plan,
    effective_sources,
    heavy_lock,
    import_usda,
    local_sources,
    plan,
    supervise,
    worker,
    worker_once,
)
from .settings import Settings, load_policy


def _parser():
    parser = argparse.ArgumentParser(description="Bòrd food and store reference service")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser(
        "serve", help="Start HTTP immediately; acquisition is a worker responsibility"
    )
    commands.add_parser("run", help="Supervise one API and one acquisition worker")
    running = commands.add_parser("worker", help="Run the durable bulk-only scheduler")
    running.add_argument("--once", action="store_true")
    commands.add_parser("worker-health", help="Check a recent durable worker heartbeat")
    importing = commands.add_parser("import", help="Replace only USDA from local JSON/ZIP files")
    importing.add_argument("paths", type=Path, nargs="*")
    refresh = commands.add_parser(
        "refresh", help="Explicitly refresh USDA through the safe publisher"
    )
    refresh.add_argument("--force-download", action="store_true")
    status = commands.add_parser("status", help="Print catalog provenance and safe system status")
    status.add_argument("--json", action="store_true")
    sync = commands.add_parser("sync", help="Plan or execute one bounded due batch")
    sync.add_argument("--plan", action="store_true")
    sync.add_argument("--due", action="store_true")
    sync.add_argument("--once", action="store_true")
    sync.add_argument("--source", choices=list(load_policy(Settings())["sources"]))
    crawl = commands.add_parser("crawl", help="Explicit independently gated map-link discovery")
    crawl.add_argument("--adapter", choices=["woodmans_maps"], required=True)
    mode = crawl.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--once", action="store_true")
    sources = commands.add_parser("sources")
    operations = sources.add_subparsers(dest="operation", required=True)
    listing = operations.add_parser("list")
    listing.add_argument("--json", action="store_true")
    for operation in ("pause", "resume", "explain-due"):
        action = operations.add_parser(operation)
        action.add_argument("source")
    jobs = commands.add_parser("jobs")
    operations = jobs.add_subparsers(dest="operation", required=True)
    listing = operations.add_parser("list")
    listing.add_argument("--json", action="store_true")
    for operation in ("retry", "cancel", "inspect"):
        action = operations.add_parser(operation)
        action.add_argument("job_id")
    rights = commands.add_parser("rights", help="Reviewed source retention and display controls")
    operations = rights.add_subparsers(dest="operation", required=True)
    for operation in ("restrict", "allow"):
        action = operations.add_parser(operation)
        action.add_argument("source")
        action.add_argument("--reason", required=True)
        if operation == "restrict":
            action.add_argument("--retention-until", type=float)
    purge = operations.add_parser("purge")
    purge.add_argument(
        "--quiesced",
        action="store_true",
        required=True,
        help="Operator confirms read processes are stopped; requires idle worker",
    )
    identities = commands.add_parser("identity", help="Audited reviewed identity correction")
    operations = identities.add_subparsers(dest="operation", required=True)
    alias = operations.add_parser("alias")
    for name in ("source", "kind", "source_key", "target", "reason"):
        alias.add_argument(name)
    undo = operations.add_parser("undo")
    undo.add_argument("decision_id", type=int)
    catalog = commands.add_parser("catalog")
    operations = catalog.add_subparsers(dest="operation", required=True)
    rollback = operations.add_parser("rollback")
    rollback.add_argument("generation")
    flags = rollback.add_mutually_exclusive_group(required=True)
    flags.add_argument("--plan", action="store_true")
    flags.add_argument("--apply", action="store_true")
    backup = commands.add_parser("backup")
    backup.add_argument("destination", type=Path)
    restore = commands.add_parser("restore")
    restore.add_argument("source", type=Path)
    restore.add_argument("--apply", action="store_true", required=True)
    return parser


def main():
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    # Validate all effective policy before role initialization or subprocess creation.
    load_policy(settings)
    command = args.command or "serve"
    if command == "run":
        raise SystemExit(supervise())
    if command == "worker":
        result = worker(settings, once=args.once)
        if args.once:
            print(json.dumps(result))
        return
    if command == "worker-health":
        path = settings.data_dir / "control" / "worker-heartbeat.json"
        if not path.exists() or time.time() - json.loads(path.read_text())["at"] > 300:
            raise SystemExit(1)
        print(json.dumps({"worker_alive": True}))
        return
    from .platform import Platform

    platform = Platform(settings.data_dir)
    platform.initialize()
    apply_rights_policy(settings, platform.control)
    if command == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(
            create_app(settings),
            host="0.0.0.0",
            port=int(os.getenv("PORT", "8080")),
            access_log=False,
            proxy_headers=False,
        )
    elif command == "status":
        if not args.json and platform.legacy_path().exists():
            with connect(platform.legacy_path()) as connection:
                result = metadata(connection)
        else:
            result = platform.status()
        print(json.dumps(result, indent=2))
    elif command == "import":
        paths = args.paths or local_sources(settings.import_dir)
        if not paths:
            raise ValueError("No source files found in IMPORT_DIR")
        for path in paths:
            # Explicit CLI paths authorize their parent; symbolic indirection is rejected.
            if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
                raise ValueError("Import paths must be regular files without symbolic links")
        print(json.dumps(import_usda(settings, paths, platform=platform), default=str))
    elif command == "refresh":
        from .download import download_datasets
        from .importer import import_lock

        config = effective_sources(settings, platform.control)["sources"]["usda_fdc"]
        if not config["enabled"]:
            raise ValueError("USDA refresh is disabled by effective source policy")
        from .transport import PolicyError, Transport

        def check():
            if not effective_sources(settings, platform.control)["sources"]["usda_fdc"]["enabled"]:
                raise PolicyError("source_disabled_by_policy")

        transport = Transport({**config, "_check": check, "data_root": str(settings.data_dir)})
        with import_lock(settings.data_dir):
            paths = download_datasets(
                settings.datasets,
                settings.data_dir / "downloads",
                args.force_download,
                transport=transport,
            )
            result = import_usda(settings, paths, platform=platform, local=False)
        print(json.dumps(result, default=str))
    elif command == "sync":
        if args.plan:
            print(json.dumps(plan(settings, source=args.source), indent=2))
        elif args.due or args.once:
            if args.source:
                config = effective_sources(settings, platform.control)["sources"][args.source]
                if not config["enabled"]:
                    raise ValueError("Source disabled by effective policy")
                platform.control.enqueue(args.source, "all")
            print(json.dumps(worker(settings, once=True)))
        else:
            raise ValueError("Use --plan or --due --once")
    elif command == "crawl":
        result = crawl_plan(settings, args.adapter, control=platform.control)
        if args.plan:
            print(json.dumps(result, indent=2))
        else:
            if not result["allowed"]:
                raise ValueError(
                    "Crawler activation gates remain blocked: "
                    + ",".join(result["blocked_reasons"])
                )
            job_id = platform.control.enqueue(args.adapter, "maps", operation="discover_map")
            print(
                json.dumps(worker_once(settings, batch_size=1, job_id=job_id, schedule_due=False))
            )
    elif command == "sources":
        if args.operation == "list":
            print(json.dumps(plan(settings), indent=2))
        elif args.operation == "explain-due":
            print(json.dumps(plan(settings, source=args.source), indent=2))
        else:
            policy = load_policy(settings)
            is_crawler = args.source in policy["crawler"]["adapters"]
            if args.source not in policy["sources"] and not is_crawler:
                raise ValueError("Unknown source")
            configured_enabled = (
                crawl_plan(settings, args.source)["allowed"]
                if is_crawler
                else policy["sources"][args.source]["enabled"]
            )
            if args.operation == "resume" and not configured_enabled:
                raise ValueError(
                    "Source remains disabled in config; review and enable its policy first"
                )
            platform.control.set_source(args.source, args.operation == "resume")
            state = (
                crawl_plan(settings, args.source, control=platform.control)
                if is_crawler
                else plan(settings, source=args.source)
            )
            print(
                json.dumps(
                    {"source": args.source, "operation": args.operation, "effective_policy": state}
                )
            )
    elif command == "jobs":
        with platform.control.connect() as db:
            if args.operation == "list":
                result = [
                    dict(row)
                    for row in db.execute(
                        "SELECT id,source,partition,operation,state,due,attempt,reason,heartbeat FROM jobs ORDER BY due"
                    )
                ]
            else:
                row = db.execute("SELECT * FROM jobs WHERE id=?", (args.job_id,)).fetchone()
                if row is None:
                    raise ValueError("Unknown job")
                if args.operation == "retry":
                    if row["operation"] == "discover_map":
                        enabled = crawl_plan(settings, row["source"], control=platform.control)[
                            "allowed"
                        ]
                    else:
                        enabled = effective_sources(settings, platform.control)["sources"][
                            row["source"]
                        ]["enabled"]
                    if not enabled:
                        raise ValueError("Source disabled by effective policy")
                    if row["state"] not in {
                        "failed",
                        "quarantined",
                        "blocked_by_policy",
                        "blocked_by_credentials",
                        "cancelled",
                    }:
                        raise ValueError("Only terminal jobs can be retried")
                    db.execute(
                        "UPDATE jobs SET state='queued',due=?,reason=NULL,attempt=0 WHERE id=?",
                        (time.time(), args.job_id),
                    )
                elif args.operation == "cancel":
                    db.execute(
                        "UPDATE jobs SET state='cancelled',reason='operator_cancelled' WHERE id=?",
                        (args.job_id,),
                    )
                row = db.execute("SELECT * FROM jobs WHERE id=?", (args.job_id,)).fetchone()
                result = {
                    key: row[key]
                    for key in (
                        "id",
                        "source",
                        "partition",
                        "operation",
                        "state",
                        "due",
                        "attempt",
                        "reason",
                    )
                }
            print(json.dumps(result, indent=2))
    elif command == "rights":
        if args.operation == "purge":
            with heavy_lock(settings.data_dir):
                result = platform.purge_revoked(quiesced=args.quiesced)
            print(json.dumps({"status": "purged", "generation": (result or {}).get("generation")}))
        else:
            policy = load_policy(settings)
            if args.operation == "allow":
                source_policy = policy["sources"].get(args.source, {})
                if source_policy.get("can_retain", True) is False or (
                    source_policy.get("retention_until") is not None
                    and source_policy["retention_until"] <= time.time()
                ):
                    raise ValueError(
                        "Configuration still denies retention; review policy before rights allow"
                    )
            platform.control.restrict_source(
                args.source,
                denied=args.operation == "restrict",
                retention_until=getattr(args, "retention_until", None),
                reason=args.reason,
            )
            print(
                json.dumps(
                    {
                        "source": args.source,
                        "operation": args.operation,
                        "acquisition_paused": not platform.control.enabled(args.source),
                    }
                )
            )
    elif command == "identity":
        if args.operation == "alias":
            platform.control.alias(
                args.source, args.kind, args.source_key, args.target, args.reason
            )
        else:
            platform.control.undo_alias(args.decision_id)
        print(json.dumps({"operation": args.operation, "status": "recorded"}))
    elif command == "catalog":
        if args.plan:
            result = platform.rollback(args.generation, apply=False)
            print(
                json.dumps(
                    {
                        **result,
                        "would_rollback": True,
                        "would_discover": False,
                        "would_download": False,
                    }
                )
            )
        else:
            print(json.dumps(platform.rollback(args.generation, apply=True), default=str))
    elif command == "backup":
        print(json.dumps(platform.backup(args.destination), default=str))
    elif command == "restore":
        print(json.dumps(platform.restore(args.source), default=str))


if __name__ == "__main__":
    main()
