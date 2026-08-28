"""Private production-sidecar bootstrap and control protocol."""

from __future__ import annotations

import json
import socket
import sys
import threading
from dataclasses import dataclass
from typing import BinaryIO

import uvicorn

from ion_api.main import create_production_app
from ion_api.migrations import upgrade_to_head
from ion_api.settings import RuntimeMode, load_settings

MAX_CONTROL_MESSAGE_BYTES = 4096
READY_PREFIX = b"ION_RUNTIME_READY "


class RuntimeProtocolError(ValueError):
    """Raised when the private parent-to-sidecar protocol is invalid."""


@dataclass(frozen=True)
class Bootstrap:
    session_token: str


def _read_bounded_line(stream: BinaryIO) -> bytes:
    line = stream.readline(MAX_CONTROL_MESSAGE_BYTES + 1)
    if not line:
        raise RuntimeProtocolError("missing bootstrap message")
    if len(line) > MAX_CONTROL_MESSAGE_BYTES or not line.endswith(b"\n"):
        raise RuntimeProtocolError("invalid bootstrap message length")
    return line[:-1]


def _parse_message(line: bytes) -> dict[str, object]:
    try:
        message = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeProtocolError("invalid control message") from error
    if not isinstance(message, dict):
        raise RuntimeProtocolError("control message must be an object")
    return message


def read_bootstrap(stream: BinaryIO) -> Bootstrap:
    message = _parse_message(_read_bounded_line(stream))
    if set(message) != {"type", "session_token"} or message["type"] != "bootstrap":
        raise RuntimeProtocolError("invalid bootstrap shape")
    token = message["session_token"]
    if not isinstance(token, str) or len(token) < 43 or len(token) > 256:
        raise RuntimeProtocolError("invalid bootstrap token")
    return Bootstrap(session_token=token)


def production_socket() -> socket.socket:
    """Bind once and retain the socket, avoiding a port reservation race."""

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    listener.bind(("127.0.0.1", 0))
    listener.listen(socket.SOMAXCONN)
    listener.setblocking(False)
    return listener


def _emit_ready(port: int) -> None:
    record = json.dumps({"port": port}, separators=(",", ":")).encode("ascii")
    sys.stdout.buffer.write(READY_PREFIX + record + b"\n")
    sys.stdout.buffer.flush()


def _control_loop(stream: BinaryIO, server: uvicorn.Server) -> None:
    """Only a bounded shutdown command is valid after one bootstrap message."""

    try:
        while True:
            line = stream.readline(MAX_CONTROL_MESSAGE_BYTES + 1)
            if not line:
                server.should_exit = True
                return
            if len(line) > MAX_CONTROL_MESSAGE_BYTES or not line.endswith(b"\n"):
                server.should_exit = True
                return
            message = _parse_message(line[:-1])
            if set(message) != {"type"} or message["type"] != "shutdown":
                server.should_exit = True
                return
            server.should_exit = True
            return
    except RuntimeProtocolError:
        server.should_exit = True


def run_production(stream: BinaryIO | None = None) -> None:
    """Run the self-contained production service using its inherited stdin."""

    control_stream = stream or sys.stdin.buffer
    bootstrap = read_bootstrap(control_stream)
    settings = load_settings(RuntimeMode.PRODUCTION)
    upgrade_to_head(settings.database_path)
    listener = production_socket()
    port = listener.getsockname()[1]
    config = uvicorn.Config(
        create_production_app(settings, bootstrap.session_token),
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)
    control_thread = threading.Thread(
        target=_control_loop,
        args=(control_stream, server),
        daemon=True,
        name="ion-runtime-control",
    )
    control_thread.start()
    _emit_ready(port)
    try:
        server.run(sockets=[listener])
    finally:
        listener.close()
