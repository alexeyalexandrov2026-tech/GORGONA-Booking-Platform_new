"""An additional policy must not discard or weaken an existing file policy."""

import httpx
import pytest
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from gorgona_booking.api.framing import FramingPolicyMiddleware

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "policy",
    [
        "default-src 'none'; sandbox; frame-ancestors 'none'",
        "default-src 'none'; sandbox; frame-ancestors *",
    ],
)
async def test_api_preserves_existing_csp_as_independent_policy(policy: str) -> None:
    async def endpoint(scope: Scope, receive: Receive, send: Send) -> None:
        await Response(b"FAKE file", headers={"Content-Security-Policy": policy})(
            scope, receive, send
        )

    app = FramingPolicyMiddleware(endpoint, allow_loopback=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/businesses/FAKE/documents/FAKE/file")
    assert response.headers.get_list("content-security-policy") == [
        policy,
        "frame-ancestors 'none'",
    ]
    assert response.headers["cache-control"] == "private, no-store"


async def test_api_without_csp_gets_framing_restriction() -> None:
    app = FramingPolicyMiddleware(Response(b"FAKE"), allow_loopback=True)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/FAKE")
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
