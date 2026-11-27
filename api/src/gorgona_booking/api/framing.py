"""HTTP framing policy (ADR-0012; closes the M3 clickjacking finding in code).

- Customer-web HTML carries `Content-Security-Policy: frame-ancestors 'self' <origins>`,
  using only the governed, approved origins of the live tenant behind this Host.
  With no approved origin it is `'self'` only, plus `X-Frame-Options: SAMEORIGIN`
  for older browsers.
- API responses carry `frame-ancestors 'none'`.
- Probes and non-HTML assets are unchanged.

The policy is an HTTP header: `frame-ancestors` in a <meta> tag is ignored by browsers.
If the lookup fails, it falls back to `'self'` (no third-party framing).
"""

import logging

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gorgona_booking.tenancy.embedding import approved_embed_origins

logger = logging.getLogger("gorgona_booking.framing")

_PUBLIC_CACHEABLE_HTML_PATHS = frozenset(
    {
        "/",
        "/index.html",
        "/legal/privacy",
        "/legal/privacy/",
        "/legal/terms",
        "/legal/terms/",
    }
)


class FramingPolicyMiddleware:
    def __init__(self, app: ASGIApp, *, allow_loopback: bool) -> None:
        self.app = app
        self._allow_loopback = allow_loopback

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith("/health/"):
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith("/v1/")
        req_headers = Headers(scope=scope)
        forwarded_proto = req_headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        is_https = (
            not self._allow_loopback or scope.get("scheme") == "https" or forwarded_proto == "https"
        )

        async def send_with_policy(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("x-content-type-options", "nosniff")
                headers.setdefault("referrer-policy", "strict-origin-when-cross-origin")
                headers.setdefault("permissions-policy", "camera=(), microphone=(), geolocation=()")
                if is_https:
                    headers.setdefault(
                        "strict-transport-security",
                        "max-age=31536000; includeSubDomains",
                    )
                if is_api:
                    # Multiple CSP policies are enforced together. Keep any
                    # existing default-src/sandbox policy, and add a separate
                    # policy so a pre-existing frame-ancestors cannot win by
                    # appearing first inside one semicolon-delimited policy.
                    headers.append("content-security-policy", "frame-ancestors 'none'")
                    headers["cache-control"] = (
                        "no-store"
                        if scope["path"].startswith("/v1/customer/")
                        else "private, no-store"
                    )
                elif headers.get("content-type", "").startswith("text/html"):
                    if scope["path"] in ("/book", "/book/"):
                        origins = await self._origins(scope)
                        headers["content-security-policy"] = " ".join(
                            ["frame-ancestors 'self'", *origins]
                        )
                        if not origins:
                            headers["x-frame-options"] = "SAMEORIGIN"
                    else:
                        # A customer's embedding approval never grants framing of staff UI.
                        headers["content-security-policy"] = "frame-ancestors 'none'"
                        headers["x-frame-options"] = "DENY"
                        if scope["path"] in _PUBLIC_CACHEABLE_HTML_PATHS:
                            headers["cache-control"] = (
                                "public, max-age=300, stale-while-revalidate=600"
                            )
                        else:
                            headers["cache-control"] = "private, no-store"
            await send(message)

        await self.app(scope, receive, send_with_policy)

    async def _origins(self, scope: Scope) -> list[str]:
        pool = getattr(scope["app"].state, "pool", None)
        if pool is None:
            return []
        try:
            return await approved_embed_origins(
                pool, Headers(scope=scope).get("host", ""), allow_loopback=self._allow_loopback
            )
        except Exception as exc:
            logger.warning("framing policy lookup failed", extra={"error_type": type(exc).__name__})
            return []
