"""Application settings loaded once; paths can be overridden for tests or deployment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Resolved filesystem locations for the week2 app."""

    base_dir: Path
    data_dir: Path
    db_path: Path


@lru_cache
def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parents[1]
    data_override = os.getenv("WEEK2_DATA_DIR")
    data_dir = Path(data_override).resolve() if data_override else base_dir / "data"
    return Settings(base_dir=base_dir, data_dir=data_dir, db_path=data_dir / "app.db")


def reset_settings_cache() -> None:
    """Clear cached settings (used from tests if paths change)."""
    get_settings.cache_clear()
