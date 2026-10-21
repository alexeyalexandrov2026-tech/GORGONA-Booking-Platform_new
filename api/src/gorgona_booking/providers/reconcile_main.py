"""The reconciler process: `python -m gorgona_booking.providers.reconcile_main [--once]` (K6b).

Needs `GBA_RECEIPT_WRITER_DATABASE_URL` (the receipt writer login), `GBA_STRIPE_NAMESPACE` (the
platform namespace of the key) and `GBA_STRIPE_API_KEY_REF` (`env:NAME`, with that variable set
to a read-only test key). Without `--once` it reconciles the last `--days` (default 3, 1 to 30)
every `--interval` seconds (default 900, 60 to 3600) and stops after the current run on Ctrl+C or
SIGTERM.
"""

import asyncio
import os
import signal
import sys

from gorgona_booking.observability import configure_logging
from gorgona_booking.providers.receipt_processes import (
    ReceiptProcessError,
    reconcile_settings,
    run_reconciler,
)


async def _run(argv: list[str]) -> None:
    try:
        settings = reconcile_settings(os.environ, argv)
    except ReceiptProcessError as error:
        raise SystemExit(f"provider reconciler: {error}") from None
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: loop.call_soon_threadsafe(stop.set))
    await run_reconciler(settings, stop=stop)


def main(argv: list[str] | None = None) -> None:
    configure_logging(os.environ.get("GBA_LOG_LEVEL", "INFO"))
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(_run(sys.argv[1:] if argv is None else argv), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
