from pathlib import Path

import pytest

from ion_api.settings import Settings, load_settings


def test_load_settings_reads_optional_local_toml(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text("[ion]\napi_port = 9123\n")
    monkeypatch.setenv("ION_DATA_DIR", str(tmp_path))

    settings = load_settings()

    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 9123
    assert settings.database_path == tmp_path / "ion-development.sqlite3"


def test_settings_reject_non_loopback_host(tmp_path):
    with pytest.raises(ValueError, match="127.0.0.1"):
        Settings(data_dir=Path(tmp_path), api_host="0.0.0.0")
