"""The receipt ingress process: `python -m gorgona_booking.providers.ingress_main` (K0b).

Needs `GBA_RECEIPT_WRITER_DATABASE_URL` (the receipt writer login), `GBA_RECEIPT_SECRET_REFS`
(for example `env:GBA_STRIPE_TEST_WEBHOOK_SECRET`) and the named variables; listens on
127.0.0.1 port `GBA_RECEIPT_PORT` (default 8787). Never mounted in the ordinary API.
"""

import asyncio
import os
import sys

from gorgona_booking.observability import configure_logging
from gorgona_booking.providers.receipt_processes import (
    ReceiptProcessError,
    ingress_settings,
    serve_ingress,
)


def main() -> None:
    configure_logging(os.environ.get("GBA_LOG_LEVEL", "INFO"))
    try:
        settings = ingress_settings(os.environ)
    except ReceiptProcessError as error:
        raise SystemExit(f"receipt ingress: {error}") from None
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(serve_ingress(settings), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
