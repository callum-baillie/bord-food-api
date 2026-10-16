import os
from dataclasses import dataclass, field
from pathlib import Path

DATASETS = ("branded", "foundation", "fndds", "sr_legacy")


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "./data")))
    import_dir: Path = field(default_factory=lambda: Path(os.getenv("IMPORT_DIR", "./imports")))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", "").strip())
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
