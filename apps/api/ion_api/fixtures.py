"""Synthetic-only fixture helpers for development and tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_synthetic_fixture(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fixture_file:
        fixture = json.load(fixture_file)
    if fixture.get("synthetic") is not True:
        raise ValueError("Ion fixture must explicitly declare synthetic: true")
    return fixture
