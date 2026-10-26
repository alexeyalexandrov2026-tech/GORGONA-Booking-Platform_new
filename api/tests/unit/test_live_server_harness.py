"""D-01: a live test server that dies during a test fails that test with its own error."""

import time

import pytest
import uvicorn
from fastapi import FastAPI

from tests.integration.live_server import LiveServerStoppedError, free_port, live_server

BUFFER = (
    "An operation on a socket could not be performed because the system lacked sufficient buffer"
)


def test_a_server_that_dies_during_the_test_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(self: uvicorn.Server, counter: int) -> bool:
        raise OSError(10055, BUFFER)

    monkeypatch.setattr(uvicorn.Server, "on_tick", broken)
    with (
        pytest.raises(LiveServerStoppedError, match=r"stopped during the test.*10055") as caught,
        live_server(FastAPI(), free_port()),
    ):
        time.sleep(0.5)
    assert isinstance(caught.value.__cause__, OSError)


def test_a_healthy_server_stops_quietly() -> None:
    with live_server(FastAPI(), free_port()) as url:
        assert url.startswith("http://127.0.0.1:")
