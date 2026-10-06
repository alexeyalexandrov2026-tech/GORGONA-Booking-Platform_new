"""Write gate of optional modules (ADR-0020).

The database trigger `gba.require_enabled_module()` is the final arbiter: it refuses an
insert with SQLSTATE GBM01 unless a published configuration enables the module. The
early check only answers sooner; reads, history and downloads are never gated.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import psycopg

from gorgona_booking.business.configurations import module_enabled
from gorgona_booking.business.modules import MODULES_BY_ID, ModuleDisabledError
from gorgona_booking.db.pool import RuntimeConnection

MODULE_DISABLED_SQLSTATE = "GBM01"
COUNTERPARTIES_MODULE = "counterparties"
DOCUMENTS_MODULE = "documents"
FINANCE_MODULE = "finance"


def _disabled(module_id: str) -> ModuleDisabledError:
    name = MODULES_BY_ID[module_id].name
    return ModuleDisabledError(
        f"{name} is turned off in this business's configuration", module_id=module_id
    )


async def require_module(conn: RuntimeConnection, business_id: UUID, module_id: str) -> None:
    if not await module_enabled(conn, business_id, module_id):
        raise _disabled(module_id)


@asynccontextmanager
async def module_writes(*module_ids: str) -> AsyncIterator[None]:
    """Map the database gate to 409 MODULE_DISABLED for writes inside the block."""
    try:
        yield
    except psycopg.DatabaseError as exc:
        if exc.sqlstate != MODULE_DISABLED_SQLSTATE:
            raise
        message = exc.diag.message_primary or ""
        refused = next((m for m in module_ids if f"the {m} module" in message), module_ids[0])
        raise _disabled(refused) from exc
