"""K1i: the running-total keys are approved unique indexes that end with the company expression."""

import psycopg
import pytest

from gorgona_booking.db.inventory_guard import assert_inventory_ready
from gorgona_booking.db.pool import RuntimePool, unscoped_transaction
from gorgona_booking.errors import DatabaseUnavailableError

pytestmark = pytest.mark.anyio

_MOVEMENTS = (
    "create unique index stock_movements_sequence_key on gba.stock_movements "
    "(item_id,place_id,legal_entity_id,sequence,(tenant_id::text))"
)
_VALUATIONS = (
    "create unique index stock_valuations_sequence_key on gba.stock_valuations "
    "(item_id,legal_entity_id,sequence,(tenant_id::text))"
)


@pytest.mark.parametrize(
    ("damage", "repair"),
    [
        pytest.param(
            ["drop index gba.stock_movements_sequence_key"],
            [_MOVEMENTS],
            id="movements-key-missing",
        ),
        pytest.param(
            ["drop index gba.stock_valuations_sequence_key"],
            [_VALUATIONS],
            id="valuations-key-missing",
        ),
        pytest.param(
            [
                "drop index gba.stock_movements_sequence_key",
                "create unique index stock_movements_sequence_key on gba.stock_movements "
                "(tenant_id,item_id,place_id,legal_entity_id,sequence)",
            ],
            ["drop index gba.stock_movements_sequence_key", _MOVEMENTS],
            id="movements-key-company-first",
        ),
        pytest.param(
            [
                "drop index gba.stock_valuations_sequence_key",
                "alter table gba.stock_valuations add constraint stock_valuations_sequence_key "
                "unique (tenant_id,legal_entity_id,item_id,sequence)",
            ],
            [
                "alter table gba.stock_valuations drop constraint stock_valuations_sequence_key",
                _VALUATIONS,
            ],
            id="valuations-old-constraint",
        ),
    ],
)
async def test_history_key_drift_refuses_inventory_work(
    app_pool: RuntimePool, owner_conn: psycopg.Connection, damage: list[str], repair: list[str]
) -> None:
    async with unscoped_transaction(app_pool) as conn:
        await assert_inventory_ready(conn)
    try:
        for statement in damage:
            owner_conn.execute(statement.encode())
        with pytest.raises(DatabaseUnavailableError):
            async with unscoped_transaction(app_pool) as conn:
                await assert_inventory_ready(conn)
    finally:
        for statement in repair:
            owner_conn.execute(statement.encode())
    async with unscoped_transaction(app_pool) as conn:
        await assert_inventory_ready(conn)
