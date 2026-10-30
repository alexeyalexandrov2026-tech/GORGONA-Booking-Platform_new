"""Run the real ASGI app on a loopback port for black-box HTTP/browser tests."""

import asyncio
import os
import selectors
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn
from fastapi import FastAPI


class LiveServerStoppedError(AssertionError):
    """D-01: the server thread died while the test was still using it."""


# Playwright's request client (page.request, route.fetch) pools sockets with no idle limit
# (http.Agent keepAlive: true). With uvicorn's default 5 s limit the server could close a socket
# at the moment the client reused it, and the request failed with "read ECONNRESET". An idle
# connection now outlives any test; stopping the server still closes it.
KEEP_ALIVE_SECONDS = 3600


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def live_server(app: FastAPI, port: int) -> Iterator[str]:
    """Serve `app` on 127.0.0.1:`port`; yields the base URL and stops it on exit."""
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="error",
            access_log=False,
            proxy_headers=False,
            timeout_keep_alive=KEEP_ALIVE_SECONDS,
        )
    )

    # D-01: a server whose loop dies (for example WinError 10055 in select) must fail the test
    # with its own error, not leave the browser to time out against a silent port.
    crashed: list[BaseException] = []

    def serve() -> None:
        try:
            if os.name == "nt":
                asyncio.run(
                    server.serve(),
                    loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
                )
            else:
                asyncio.run(server.serve())
        except BaseException as error:  # reported when the test leaves the block
            crashed.append(error)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started, "live server did not start"
        yield f"http://127.0.0.1:{port}"
    finally:
        if crashed:
            raise LiveServerStoppedError(
                f"the live server stopped during the test: {crashed[0]!r}"
            ) from crashed[0]
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "live server did not stop"
