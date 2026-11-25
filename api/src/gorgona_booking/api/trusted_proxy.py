"""Azure Front Door trusted-proxy boundary (ADR-0012).

Behind Front Door the origin receives `Host: <container app FQDN>`. Front Door
overwrites `X-Forwarded-Host` with the host the client requested and adds
`X-Azure-FDID` with its profile ID. Only when that ID is exactly ours does the
forwarded host become the effective Host. Tenant resolution, static redirects and
the framing policy then see the tenant host. Every other request is refused as an
unknown site. The origin is also reachable only through Private Link; this check is
the application half of that boundary.
"""

import hmac
import logging
import re

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from gorgona_booking.api.errors import error_response
from gorgona_booking.observability import record_domain_error

logger = logging.getLogger("gorgona_booking.trusted_proxy")

# Exact paths only: platform probes reach the container directly, without Front Door.
_PROBE_PATHS = frozenset({"/health/live", "/health/ready"})
_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?(?::[0-9]{1,5})?$")


def _values(scope: Scope, name: bytes) -> list[bytes]:
    return [value for key, value in scope["headers"] if key == name]


class AzureFrontDoorMiddleware:
    def __init__(self, app: ASGIApp, front_door_id: str) -> None:
        self.app = app
        self._front_door_id = front_door_id.lower().encode("ascii")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _PROBE_PATHS:
            await self.app(scope, receive, send)
            return

        profile_ids = _values(scope, b"x-azure-fdid")
        forwarded_hosts = _values(scope, b"x-forwarded-host")
        host = (
            forwarded_hosts[0].decode("latin-1").strip().lower()
            if len(forwarded_hosts) == 1
            else ""
        )
        from_our_front_door = len(profile_ids) == 1 and hmac.compare_digest(
            profile_ids[0].strip().lower(), self._front_door_id
        )
        if not from_our_front_door or not _HOST.fullmatch(host):
            # No header values are logged: they are attacker-controlled.
            logger.warning(
                "request refused at trusted-proxy boundary",
                extra={"reason": "profile_id" if not from_our_front_door else "forwarded_host"},
            )
            record_domain_error("TENANT_NOT_FOUND", "trusted_proxy")
            response = error_response(Request(scope), 404, "TENANT_NOT_FOUND", "Unknown site")
            await response(scope, receive, send)
            return

        headers = [(key, value) for key, value in scope["headers"] if key != b"host"]
        headers.append((b"host", host.encode("ascii")))
        rewritten = dict(scope)
        rewritten["headers"] = headers
        protos = _values(scope, b"x-forwarded-proto")
        if len(protos) == 1 and protos[0] in (b"http", b"https"):
            rewritten["scheme"] = protos[0].decode("ascii")
        await self.app(rewritten, receive, send)


class GoogleCloudLoadBalancerMiddleware:
    """Fail-closed trusted-proxy boundary for Google Cloud External HTTPS LB + Cloud Armor.

    Cloud Run is configured with `internal-and-cloud-load-balancing` ingress; the Global
    External Application Load Balancer injects `X-Gorgona-Edge-Secret` as a custom request
    header on the backend service. Requests without an exact constant-time secret match or
    a valid single host are refused with 404 TENANT_NOT_FOUND.
    """

    def __init__(self, app: ASGIApp, edge_secret: str) -> None:
        self.app = app
        self._edge_secret = edge_secret.strip().encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _PROBE_PATHS:
            await self.app(scope, receive, send)
            return

        secrets = _values(scope, b"x-gorgona-edge-secret")
        from_our_lb = len(secrets) == 1 and hmac.compare_digest(
            secrets[0].strip(), self._edge_secret
        )
        forwarded_hosts = _values(scope, b"x-forwarded-host")
        raw_hosts = forwarded_hosts if forwarded_hosts else _values(scope, b"host")
        host = raw_hosts[0].decode("latin-1").strip().lower() if len(raw_hosts) == 1 else ""
        if not from_our_lb or not _HOST.fullmatch(host):
            logger.warning(
                "request refused at google_cloud_lb boundary",
                extra={"reason": "edge_secret" if not from_our_lb else "forwarded_host"},
            )
            record_domain_error("TENANT_NOT_FOUND", "trusted_proxy")
            response = error_response(Request(scope), 404, "TENANT_NOT_FOUND", "Unknown site")
            await response(scope, receive, send)
            return

        headers = [
            (key, value)
            for key, value in scope["headers"]
            if key not in (b"host", b"x-gorgona-edge-secret")
        ]
        headers.append((b"host", host.encode("ascii")))
        rewritten = dict(scope)
        rewritten["headers"] = headers
        protos = _values(scope, b"x-forwarded-proto")
        if len(protos) == 1 and protos[0] in (b"http", b"https"):
            rewritten["scheme"] = protos[0].decode("ascii")
        await self.app(rewritten, receive, send)
