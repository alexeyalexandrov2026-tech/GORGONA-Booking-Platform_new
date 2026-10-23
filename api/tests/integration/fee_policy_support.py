"""L9a test support: publish a visit fee policy version (FAKE data only)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx

from gorgona_booking.booking.models import ReservationRequest
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool
from tests.integration.booking_support import BookingWorld

# A year: every cancellation of a visit a few hours ahead is late.
ALWAYS_LATE = 525600


async def publish_fee_policy(
    client: httpx.AsyncClient,
    business: UUID,
    headers: dict[str, str],
    *,
    expected_version: int = 0,
    free_minutes: int = ALWAYS_LATE,
    late: dict[str, str] | None = None,
    no_show: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.post(
        f"/v1/salons/{business}/visit-fee-policy",
        json={
            "expected_version": expected_version,
            "free_cancellation_minutes": free_minutes,
            "late_cancellation_fee": late,
            "no_show_fee": no_show,
        },
        headers=headers,
    )


async def soon_visit(
    world: BookingWorld,
    pool: RuntimePool,
    *,
    hours: int,
    variant: UUID | None = None,
    add_ons: tuple[UUID, ...] | None = None,
    cancel: bool = False,
) -> UUID:
    """A confirmed visit `hours` ahead (base 50.00 + massage 20.00 unless named), cancelled now."""
    start = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(hours=hours)
    service = BookingService(pool)
    result = await service.create_confirmed_booking(
        world.a.tenant_id,
        ReservationRequest(
            resource_id=world.artist_a1,
            variant_id=variant or world.catalog_a.base_variant_id,
            starts_at=start,
            add_on_ids=(world.catalog_a.massage_add_on_id,) if add_ons is None else add_ons,
        ),
        actor="test:l9a",
        idempotency_key=None,
    )
    if cancel:
        await service.cancel(world.a.tenant_id, result.booking_id, actor="test:l9a")
    return result.booking_id
