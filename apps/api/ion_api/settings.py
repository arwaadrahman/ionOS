"""Non-secret local settings. Secrets are intentionally not modeled here."""

from __future__ import annotations

import os
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

DEFAULT_API_PORT = 8765
DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:1420",
    "http://localhost:1420",
    "tauri://localhost",
)


class RuntimeMode(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseModel):
    """Validated settings sourced from code defaults, TOML, then safe overrides."""

    data_dir: Path
    api_host: str = "127.0.0.1"
    api_port: int = DEFAULT_API_PORT
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS
    runtime_mode: RuntimeMode = RuntimeMode.DEVELOPMENT

    @field_validator("api_host")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("Ion API must bind only to 127.0.0.1")
        return value

    @field_validator("api_port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("api_port must be between 1 and 65535")
        return value

    @property
    def database_path(self) -> Path:
        filename = (
            "ion.sqlite3"
            if self.runtime_mode is RuntimeMode.PRODUCTION
            else "ion-development.sqlite3"
        )
        return self.data_dir / filename

    @property
    def log_path(self) -> Path:
        return self.data_dir / "logs" / "ion.log"


def default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Ion OS"


def read_user_config(data_dir: Path) -> dict[str, Any]:
    config_path = data_dir / "config.toml"
    if not config_path.is_file():
        return {}
    with config_path.open("rb") as config_file:
        parsed = tomllib.load(config_file)
    return parsed.get("ion", {})


def load_settings(runtime_mode: RuntimeMode = RuntimeMode.DEVELOPMENT) -> Settings:
    """Load optional non-secret TOML and narrowly scoped development overrides.

    `ION_DATA_DIR` and `ION_API_PORT` exist for tests and local development.
    They are not an Ion secret-management mechanism.
    """

    data_dir = Path(os.environ.get("ION_DATA_DIR", default_data_dir())).expanduser()
    values: dict[str, Any] = {
        "data_dir": data_dir,
        **read_user_config(data_dir),
        "runtime_mode": runtime_mode,
    }
    if port := os.environ.get("ION_API_PORT"):
        values["api_port"] = int(port)
    return Settings.model_validate(values)
