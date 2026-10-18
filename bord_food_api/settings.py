import os
from dataclasses import dataclass, field
from pathlib import Path

DATASETS = ("branded", "foundation", "fndds", "sr_legacy")


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "./data")))
    import_dir: Path = field(default_factory=lambda: Path(os.getenv("IMPORT_DIR", "./imports")))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", "").strip(), repr=False)
    datasets: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            dict.fromkeys(
                item.strip()
                for item in os.getenv("DATASETS", ",".join(DATASETS)).split(",")
                if item.strip()
            )
        )
    )
    auto_download: bool = field(
        default_factory=lambda: os.getenv("AUTO_DOWNLOAD", "true").lower() == "true"
    )

    def __post_init__(self):
        if not self.datasets or set(self.datasets) - set(DATASETS):
            raise ValueError(
                f"DATASETS must be a comma-separated selection of {', '.join(DATASETS)}"
            )

    @property
    def database(self) -> Path:
        return self.data_dir / "foods.sqlite"


# These are reviewed delivery origins, never wildcard suffix matches. A new CDN
# requires explicit operator configuration and the same connection-time guard.
SOURCE_DEFAULTS = {
    "usda_fdc": {"enabled": True, "origins": ["https://fdc.nal.usda.gov"]},
    "all_the_places": {
        "enabled": True,
        "origins": ["https://data.alltheplaces.xyz"],
        "spiders": ["walmart_us", "aldi_sud_us", "target_us", "kroger_us"],
        "selection_mode": "selected_spiders",
    },
    "usda_snap": {"enabled": False, "origins": ["https://www.fns.usda.gov"]},
    "open_food_facts": {
        "enabled": False,
        "origins": ["https://static.openfoodfacts.org", "https://world.openfoodfacts.org"],
    },
    "open_prices": {"enabled": False, "origins": ["https://prices.openfoodfacts.org"]},
    "foodkeeper": {
        "enabled": False,
        "origins": [
            "https://www.foodsafety.gov",
            "https://www.fsis.usda.gov",
            "https://catalog.data.gov",
        ],
    },
}


def load_policy(settings):
    """Resolve new policy, explicit legacy restrictions, and core-only defaults."""
    import copy
    import json

    filename = os.getenv("BORD_FOOD_CONFIG")
    configured = json.loads(Path(filename).read_text()) if filename else {}
    if not isinstance(configured, dict):
        raise TypeError("BORD_FOOD_CONFIG must contain an object")
    mode = configured.get("network", {}).get("mode", "bulk_only")
    if mode not in {"offline", "bulk_only"}:
        raise ValueError("network.mode must be offline or bulk_only")
    if configured.get("network", {}).get("allow_paid_sources", False):
        raise ValueError(
            "Paid source activation requires a separately implemented budget connector"
        )
    policy = {
        "network": {"mode": mode, "crawl_enabled": False},
        "crawler": {
            "enabled": False,
            "adapters_enabled": [],
            "operator_contact": "",
            "max_pages_per_run": 50,
            "max_pages_per_day": 500,
            "min_delay_seconds": 5,
            "max_html_bytes": 2 * 1024**2,
            "adapters": {
                "woodmans_maps": {
                    "enabled": False,
                    "source_authorized": False,
                    "terms_reviewed": False,
                    "robots_reviewed": False,
                    "allowed_host": "www.woodmans-food.com",
                    "scope_prefix": "/store-locations/",
                    "approved_targets": [],
                }
            },
        },
        "sources": copy.deepcopy(SOURCE_DEFAULTS),
        "scheduler": {
            "enabled": True,
            "tick_seconds": 30,
            "lease_seconds": 120,
            "heartbeat_seconds": 20,
            "max_retries": 5,
            "retry_base_seconds": 60,
        },
        "budgets": {
            "max_artifact_bytes": 20 * 1024**3,
            "max_decompressed_bytes": 200 * 1024**3,
            "free_space_reserve_bytes": 5 * 1024**3,
            "data_quota_bytes": 50 * 1024**3,
        },
        "runtime": {"required_packs": ["usda", "stores"]},
        "bootstrap": {"mode": "automatic"},
    }
    policy["network"].update(configured.get("network", {}))
    configured_crawler = configured.get("crawler", {})
    for key, value in configured_crawler.items():
        if key != "adapters":
            policy["crawler"][key] = value
    for name, descriptor in configured_crawler.get("adapters", {}).items():
        if name != "woodmans_maps":
            raise ValueError("Unsupported crawler adapter")
        policy["crawler"]["adapters"][name].update(descriptor)
    if set(policy["crawler"]["adapters_enabled"]) - {"woodmans_maps"}:
        raise ValueError("Unsupported enabled crawler adapter")
    for name in ("enabled",):
        if type(policy["crawler"][name]) is not bool:
            raise TypeError("Crawler activation gates must be boolean")
    if type(policy["network"]["crawl_enabled"]) is not bool:
        raise TypeError("network.crawl_enabled must be boolean")
    for section in ("scheduler", "budgets", "runtime", "bootstrap"):
        policy[section].update(configured.get(section, {}))
    for name, limit in policy["budgets"].items():
        if name.endswith("_bytes") and (type(limit) is not int or limit < 0):
            raise ValueError("Resource budgets must be nonnegative integer bytes")
    for name in (
        "tick_seconds",
        "lease_seconds",
        "heartbeat_seconds",
        "max_retries",
        "retry_base_seconds",
    ):
        value = policy["scheduler"][name]
        if type(value) not in (int, float) or not 0 < value <= 86400:
            raise ValueError("Scheduler limits must be positive and bounded")
    if policy["scheduler"]["heartbeat_seconds"] >= policy["scheduler"]["lease_seconds"]:
        raise ValueError("Scheduler heartbeat must be shorter than lease")
    required = policy["runtime"]["required_packs"]
    if not isinstance(required, list) or set(required) - {
        "usda",
        "stores",
        "products",
        "prices",
        "guidance",
        "maps",
    }:
        raise ValueError("runtime.required_packs contains an unsupported pack")
    explicit = configured.get("sources", {})
    unknown = set(explicit) - set(SOURCE_DEFAULTS)
    if any(explicit[name].get("enabled") for name in unknown):
        raise ValueError("Unsupported enabled source")
    for source, defaults in policy["sources"].items():
        defaults.update(explicit.get(source, {}))
        defaults.update({"mode": mode, **policy["budgets"]})
        if source == "usda_fdc":
            defaults.setdefault("datasets", list(settings.datasets))
            if not settings.auto_download and "enabled" not in explicit.get(source, {}):
                defaults["enabled"] = False
                defaults["legacy_auto_download_disabled"] = True
        if mode == "offline":
            defaults["enabled"] = False
        from .transport import approved_url

        if type(defaults["enabled"]) is not bool or not isinstance(defaults.get("origins"), list):
            raise ValueError("Source policy needs boolean enabled and exact origins")
        for origin in defaults["origins"]:
            parsed = approved_url(origin, defaults["origins"])
            if parsed.path or parsed.query:
                raise ValueError("Source origins cannot contain path/query")
        if defaults.get("crawler") or defaults.get("paid"):
            raise ValueError("Crawler and paid connectors cannot use bulk source policy")
        for action in (
            "can_fetch",
            "can_store_raw",
            "can_store_normalized",
            "can_display",
            "can_rehost_media",
            "can_redistribute",
        ):
            if action in defaults and (
                not isinstance(defaults[action], (str, bool))
                or defaults[action] not in (True, False, "allow", "deny", "review_required")
            ):
                raise ValueError("Source rights actions require allow/deny/review_required")
        if "can_retain" in defaults and type(defaults["can_retain"]) is not bool:
            raise TypeError("Source can_retain must be boolean")
        retention = defaults.get("retention_until")
        if retention is not None:
            from datetime import UTC, datetime

            if isinstance(retention, str):
                parsed = datetime.fromisoformat(retention)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                retention = parsed.timestamp()
            if type(retention) not in (int, float) or not 0 <= retention < 253402300800:
                raise ValueError("Source retention_until must be a bounded UTC timestamp")
            defaults["retention_until"] = retention
        interval = defaults.setdefault("interval_seconds", 86400)
        if not isinstance(interval, (int, float)) or interval < 60:
            raise ValueError("source interval_seconds must be at least 60")
    return policy
