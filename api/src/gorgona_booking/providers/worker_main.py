"""The receipt worker process: `python -m gorgona_booking.providers.worker_main [--once]` (K0b).

Needs `GBA_RECEIPT_WORKER_DATABASE_URL` (the receipt worker login). Without `--once` it decides a
batch every `--interval` seconds (default 5, 1 to 300) and stops after the current batch on
Ctrl+C or SIGTERM.
"""

import asyncio
import os
import signal
import sys

from gorgona_booking.observability import configure_logging
from gorgona_booking.providers.receipt_processes import (
    ReceiptProcessError,
    run_worker,
    worker_settings,
)


async def _run(argv: list[str]) -> None:
    try:
        settings = worker_settings(os.environ, argv)
    except ReceiptProcessError as error:
        raise SystemExit(f"receipt worker: {error}") from None
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: loop.call_soon_threadsafe(stop.set))
    await run_worker(settings, stop=stop)


def main(argv: list[str] | None = None) -> None:
    configure_logging(os.environ.get("GBA_LOG_LEVEL", "INFO"))
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(_run(sys.argv[1:] if argv is None else argv), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
