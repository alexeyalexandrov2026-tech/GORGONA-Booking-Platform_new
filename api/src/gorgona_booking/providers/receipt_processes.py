"""K0b (E-02): the receipt ingress and worker as local processes. No provider call, no Azure.

The ingress serves `create_receipt_ingress_app` on 127.0.0.1 only, with the writer login and a
key store read from named environment variables (`GBA_RECEIPT_SECRET_REFS` lists references such
as `env:GBA_STRIPE_TEST_WEBHOOK_SECRET`; a config's `secret_ref` names the same reference). The
worker runs `process_batch` once or in a bounded loop with the worker login. Keys and database
URLs live only in memory as secrets; logs carry counts and outcomes, never a payload, key, URL,
account or ingress ID. Each process refuses a login of the wrong group before it does anything.
"""

import argparse
import asyncio
import logging
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import NoReturn

import uvicorn
from pydantic import SecretStr

from gorgona_booking.db.pool import create_runtime_pool
from gorgona_booking.providers.authenticated_receipts import assert_safe_receipt_writer_role
from gorgona_booking.providers.receipt_ingress import create_receipt_ingress_app
from gorgona_booking.providers.receipt_worker import (
    assert_safe_receipt_worker_role,
    process_batch,
)

HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_INTERVAL = 5.0
MIN_INTERVAL, MAX_INTERVAL = 1.0, 300.0
WRITER_DATABASE = "GBA_RECEIPT_WRITER_DATABASE_URL"
WORKER_DATABASE = "GBA_RECEIPT_WORKER_DATABASE_URL"
REFERENCE_LIST = "GBA_RECEIPT_SECRET_REFS"
_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,99}")

logger = logging.getLogger("gorgona_booking.providers.receipt_processes")


class ReceiptProcessError(ValueError):
    """The process cannot start safely; the message never holds a secret or a URL."""


def _required(environ: Mapping[str, str], name: str) -> SecretStr:
    value = environ.get(name, "").strip()
    if not value:
        raise ReceiptProcessError(f"environment variable {name} is required")
    return SecretStr(value)


def load_key_store(environ: Mapping[str, str]) -> dict[str, SecretStr]:
    """Every listed `env:NAME` reference, each read from its own non-empty variable."""
    refs = [ref.strip() for ref in environ.get(REFERENCE_LIST, "").split(",") if ref.strip()]
    if not refs or len(set(refs)) != len(refs):
        raise ReceiptProcessError(f"{REFERENCE_LIST} must list one or more distinct references")
    store: dict[str, SecretStr] = {}
    for ref in refs:
        scheme, _, name = ref.partition(":")
        if scheme != "env" or not _NAME.fullmatch(name):
            raise ReceiptProcessError(f"unsupported secret reference {ref!r}; use env:NAME")
        store[ref] = _required(environ, name)
    return store


@dataclass(frozen=True)
class IngressSettings:
    database_url: SecretStr
    port: int
    key_store: Mapping[str, SecretStr] = field(repr=False)
    host: str = HOST


def ingress_settings(environ: Mapping[str, str]) -> IngressSettings:
    host = environ.get("GBA_RECEIPT_HOST", HOST)
    if host != HOST:
        raise ReceiptProcessError(f"the receipt ingress listens on {HOST} only")
    port_text = environ.get("GBA_RECEIPT_PORT", str(DEFAULT_PORT))
    # 0 asks the system for a free port (tests); a running ingress reports the port it bound.
    if not (port_text.isascii() and port_text.isdigit() and 0 <= int(port_text) <= 65535):
        raise ReceiptProcessError("GBA_RECEIPT_PORT must be a port number from 0 to 65535")
    return IngressSettings(
        database_url=_required(environ, WRITER_DATABASE),
        port=int(port_text),
        key_store=load_key_store(environ),
    )


@dataclass(frozen=True)
class WorkerSettings:
    database_url: SecretStr
    interval: float = DEFAULT_INTERVAL
    once: bool = False


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ReceiptProcessError(message)


def worker_settings(environ: Mapping[str, str], argv: Sequence[str]) -> WorkerSettings:
    parser = _Parser(prog="python -m gorgona_booking.providers.worker_main", add_help=False)
    parser.add_argument("--once", action="store_true", help="run one batch and exit")
    parser.add_argument("--interval", default=str(DEFAULT_INTERVAL), help="seconds between batches")
    args = parser.parse_args(list(argv))
    try:
        interval = float(args.interval)
    except ValueError:
        raise ReceiptProcessError("--interval must be a number of seconds") from None
    if not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        raise ReceiptProcessError(
            f"--interval must be {MIN_INTERVAL:g} to {MAX_INTERVAL:g} seconds"
        )
    return WorkerSettings(
        database_url=_required(environ, WORKER_DATABASE), interval=interval, once=args.once
    )


async def serve_ingress(
    settings: IngressSettings,
    *,
    started: Callable[[int], None] | None = None,
    stop: asyncio.Event | None = None,
) -> None:
    """Check the writer login, then serve until `stop` is set or the server is told to exit."""
    pool = create_runtime_pool(settings.database_url.get_secret_value())
    await pool.open(wait=True)
    try:
        async with pool.connection() as conn, conn.transaction():
            await assert_safe_receipt_writer_role(conn)
        app = create_receipt_ingress_app(pool, settings.key_store)
        # uvicorn writes its raw-path access log whenever that logger has any handler, whatever
        # `access_log` says; the path holds the ingress ID. The app logs route templates only.
        logging.getLogger("uvicorn.access").disabled = True
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=settings.host,
                port=settings.port,
                proxy_headers=False,
                lifespan="off",
                log_config=None,
                access_log=False,
                timeout_graceful_shutdown=25,
            )
        )
        task = asyncio.create_task(server.serve())
        while not server.started:
            if task.done():
                await task
                return
            await asyncio.sleep(0.01)
        port = int(server.servers[0].sockets[0].getsockname()[1])
        logger.info("provider receipt ingress listening", extra={"port": port})
        if started is not None:
            started(port)
        if stop is not None:
            waiter = asyncio.create_task(stop.wait())
            await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
            waiter.cancel()
            server.should_exit = True
        await task
    finally:
        await pool.close()


async def run_worker(settings: WorkerSettings, *, stop: asyncio.Event | None = None) -> int:
    """Check the worker login, then decide batches; returns how many events were decided."""
    pool = create_runtime_pool(settings.database_url.get_secret_value())
    await pool.open(wait=True)
    total = 0
    try:
        async with pool.connection() as conn, conn.transaction():
            await assert_safe_receipt_worker_role(conn)
        while True:
            try:
                decisions = await process_batch(pool)
            except Exception as exc:
                if settings.once:
                    raise
                # K5r (review R3): one failed batch never ends the worker; it waits one interval
                # and tries again. Only the error class is logged, never a payload or message.
                logger.warning("provider receipt batch failed", extra={"error": type(exc).__name__})
            else:
                total += len(decisions)
                outcomes = Counter(f"{d.outcome}:{d.reason}" for d in decisions)
                logger.info(
                    "provider receipt batch", extra={"decided": len(decisions), **dict(outcomes)}
                )
            if settings.once or (stop is not None and stop.is_set()):
                return total
            if stop is None:
                await asyncio.sleep(settings.interval)
                continue
            try:
                await asyncio.wait_for(stop.wait(), settings.interval)
            except TimeoutError:
                continue
            return total
    finally:
        await pool.close()
