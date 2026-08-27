from __future__ import annotations

import io
import socket

import pytest
from fastapi.testclient import TestClient

from ion_api.main import SESSION_HEADER, create_app, create_production_app
from ion_api.runtime import (
    READY_PREFIX,
    RuntimeProtocolError,
    production_socket,
    read_bootstrap,
)
from ion_api.settings import Settings

TOKEN = "a" * 43


def test_production_health_requires_the_session_token(tmp_path):
    app = create_production_app(Settings(data_dir=tmp_path), TOKEN)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 401
        assert (
            client.get("/health", headers={SESSION_HEADER: "wrong"}).status_code == 401
        )
        response = client.get("/health", headers={SESSION_HEADER: TOKEN})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "access-control-allow-origin" not in response.headers


def test_development_api_is_explicitly_distinct_from_production(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert client.get("/health").status_code == 200


def test_production_requires_a_nonempty_session_token(tmp_path):
    with pytest.raises(ValueError, match="session token"):
        create_production_app(Settings(data_dir=tmp_path), "")


def test_bootstrap_accepts_only_one_bounded_expected_message():
    bootstrap = read_bootstrap(
        io.BytesIO(b'{"type":"bootstrap","session_token":"' + TOKEN.encode() + b'"}\n')
    )

    assert bootstrap.session_token == TOKEN


@pytest.mark.parametrize(
    "payload",
    [b"", b"{}\n", b'{"type":"bootstrap","session_token":"short"}\n', b"x" * 4097],
)
def test_bootstrap_rejects_missing_malformed_or_oversized_messages(payload):
    with pytest.raises(RuntimeProtocolError):
        read_bootstrap(io.BytesIO(payload))


def test_production_socket_is_a_retained_ipv4_loopback_listener():
    listener = production_socket()
    try:
        host, port = listener.getsockname()
        assert host == "127.0.0.1"
        assert 1 <= port <= 65535
        assert listener.family == socket.AF_INET
        assert READY_PREFIX == b"ION_RUNTIME_READY "
    finally:
        listener.close()
