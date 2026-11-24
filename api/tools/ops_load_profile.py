"""OPS-02: Reproducible multi-tenant load profile generator and PG18 benchmark runner."""

import argparse
import asyncio
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.conninfo import conninfo_to_dict
from pydantic import BaseModel, ConfigDict

from gorgona_booking.db.pool import RuntimePool, create_runtime_pool, tenant_transaction

GENERATOR_VERSION = "1.0.0"
READ_P95_TARGET_MS = 500.0
WRITE_P95_TARGET_MS = 1000.0
MAX_UNEXPECTED_ERROR_RATE_PCT = 0.1
_LOOPBACK_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})

OpKind = Literal["read", "write", "report"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LatencySummary(_Strict):
    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


class DataDistribution(_Strict):
    companies: int
    enterprise_branches: int
    enterprise_staff: int
    historical_records: int
    service_variants: int


class BenchmarkEnvironment(_Strict):
    python_version: str
    platform: str
    cpu_count: int
    postgres_version: str
    pool_min_size: int
    pool_max_size: int
    concurrency: int
    adapters: str
    git_sha: str
    full_soak_40m_completed: bool


class LoadProfileConfig(_Strict):
    mode: Literal["ci-smoke", "full-1000"]
    seed: int = 20261123
    companies: int
    enterprise_branches: int
    enterprise_staff: int
    historical_records: int
    total_operations: int
    concurrency: int
    pool_max_size: int
    inject_conflict_every: int = 20
    full_soak_40m_completed: bool = False


class LoadBenchmarkReport(_Strict):
    schema_version: Literal[1] = 1
    generator_version: str = GENERATOR_VERSION
    mode: Literal["ci-smoke", "full-1000"]
    seed: int
    distribution: DataDistribution
    seed_seconds: float
    benchmark_seconds: float
    total_operations: int
    read_ops: int
    write_ops: int
    report_ops: int
    expected_conflicts: int
    unexpected_errors: int
    unexpected_error_rate_pct: float
    cross_tenant_leaks: int
    invariant_violations: int
    throughput_ops_per_sec: float
    read_latency_ms: LatencySummary
    write_latency_ms: LatencySummary
    report_latency_ms: LatencySummary
    targets_met: bool
    environment: BenchmarkEnvironment


@dataclass(frozen=True)
class SeededDataset:
    tenant_ids: tuple[UUID, ...]
    enterprise_tenant_id: UUID
    enterprise_branch_ids: tuple[UUID, ...]
    variant_by_tenant: dict[UUID, UUID]
    distribution: DataDistribution
    seed_seconds: float


def preset_config(mode: Literal["ci-smoke", "full-1000"]) -> LoadProfileConfig:
    if mode == "ci-smoke":
        return LoadProfileConfig(
            mode="ci-smoke",
            companies=20,
            enterprise_branches=10,
            enterprise_staff=100,
            historical_records=1_000,
            total_operations=200,
            concurrency=8,
            pool_max_size=12,
            inject_conflict_every=20,
            full_soak_40m_completed=False,
        )
    return LoadProfileConfig(
        mode="full-1000",
        companies=1_000,
        enterprise_branches=100,
        enterprise_staff=10_000,
        historical_records=1_000_000,
        total_operations=4_000,
        concurrency=24,
        pool_max_size=32,
        inject_conflict_every=25,
        full_soak_40m_completed=False,
    )


def require_fake_company_name(name: str) -> str:
    if not name.startswith("FAKE "):
        raise ValueError(f"Synthetic load company name must start with 'FAKE ': {name!r}")
    return name


def assert_isolated_test_target(dsn: str, *, allow_remote: bool = False) -> None:
    if allow_remote:
        return
    params = conninfo_to_dict(dsn)
    host = str(params.get("host") or "").strip().lower()
    if host not in _LOOPBACK_HOSTS and not host.startswith("/"):
        raise ValueError(
            f"Refusing to run load generator against non-loopback host {host!r} "
            "without allow_remote=True"
        )


def compute_latency_summary(samples_ms: Sequence[float]) -> LatencySummary:
    if not samples_ms:
        return LatencySummary(count=0, p50_ms=0.0, p95_ms=0.0, p99_ms=0.0, max_ms=0.0)
    ordered = sorted(samples_ms)
    n = len(ordered)

    def pct(p: float) -> float:
        idx = max(0, min(n - 1, math.ceil(p * n) - 1))
        return round(ordered[idx], 3)

    return LatencySummary(
        count=n,
        p50_ms=pct(0.50),
        p95_ms=pct(0.95),
        p99_ms=pct(0.99),
        max_ms=round(ordered[-1], 3),
    )


def build_operation_schedule(total_operations: int, seed: int) -> tuple[OpKind, ...]:
    """Build exact 70% read / 20% write / 10% report operation schedule."""
    if total_operations < 10:
        raise ValueError("total_operations must be at least 10")
    read_count = (total_operations * 70) // 100
    write_count = (total_operations * 20) // 100
    report_count = total_operations - read_count - write_count
    ops: list[OpKind] = []
    for _ in range(read_count):
        ops.append("read")
    for _ in range(write_count):
        ops.append("write")
    for _ in range(report_count):
        ops.append("report")
    rng = random.Random(seed)  # noqa: S311
    rng.shuffle(ops)
    return tuple(ops)


def evaluate_targets(
    *,
    read_latency: LatencySummary,
    write_latency: LatencySummary,
    unexpected_error_rate_pct: float,
    cross_tenant_leaks: int,
    invariant_violations: int,
) -> bool:
    return (
        read_latency.p95_ms <= READ_P95_TARGET_MS
        and write_latency.p95_ms <= WRITE_P95_TARGET_MS
        and unexpected_error_rate_pct < MAX_UNEXPECTED_ERROR_RATE_PCT
        and cross_tenant_leaks == 0
        and invariant_violations == 0
    )


def _det_uuid(seed: int, kind: str, idx: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"gorgona-ops02:{GENERATOR_VERSION}:{seed}:{kind}:{idx}")


def seed_synthetic_dataset(
    admin_db_dsn: str,
    config: LoadProfileConfig,
    *,
    allow_remote: bool = False,
) -> SeededDataset:
    """Seed synthetic FAKE companies, enterprise branches/staff, and historical records via COPY."""
    assert_isolated_test_target(admin_db_dsn, allow_remote=allow_remote)
    t0 = time.perf_counter()

    tenant_ids = tuple(_det_uuid(config.seed, "tenant", i) for i in range(config.companies))
    enterprise_id = tenant_ids[0]
    branch_ids = tuple(
        _det_uuid(config.seed, "ent-branch", i) for i in range(config.enterprise_branches)
    )
    variant_by_tenant: dict[UUID, UUID] = {}

    with psycopg.connect(admin_db_dsn) as conn:
        with conn.cursor() as cur:
            # 1. Seed companies (tenants)
            with cur.copy("copy gba.tenants (id, slug, display_name, status) from stdin") as copy:
                for i, tid in enumerate(tenant_ids):
                    name = require_fake_company_name(
                        f"FAKE Enterprise Holding {config.seed}"
                        if i == 0
                        else f"FAKE Company {i:04d} {config.seed}"
                    )
                    slug = f"fake-ops02-{config.seed}-{i:04d}"
                    copy.write_row((tid, slug, name, "active"))

            # 2. Seed locations (100 branches for enterprise, 1 branch for each other company)
            with cur.copy("copy gba.locations (tenant_id, id, name, timezone) from stdin") as copy:
                for b_idx, bid in enumerate(branch_ids):
                    copy.write_row((enterprise_id, bid, f"FAKE Branch {b_idx:03d}", "UTC"))
                for i, tid in enumerate(tenant_ids[1:], start=1):
                    loc_id = _det_uuid(config.seed, "loc", i)
                    copy.write_row((tid, loc_id, f"FAKE Main Location {i:04d}", "UTC"))

            # 3. Seed enterprise staff users & branch-scoped memberships
            user_ids = tuple(
                _det_uuid(config.seed, "staff-user", i) for i in range(config.enterprise_staff)
            )
            with cur.copy(
                "copy gba.users (id, display_name, email_normalized, status) from stdin"
            ) as copy:
                for i, uid in enumerate(user_ids):
                    copy.write_row(
                        (
                            uid,
                            f"FAKE Staff {i:05d}",
                            f"fake-staff-{config.seed}-{i:05d}@example.invalid",
                            "active",
                        )
                    )

            roles = ("manager", "front_desk", "artist")
            with cur.copy(
                "copy gba.memberships (tenant_id, id, user_id, role, location_id, status) "
                "from stdin"
            ) as copy:
                for i, uid in enumerate(user_ids):
                    mid = _det_uuid(config.seed, "staff-mem", i)
                    role = "owner" if i == 0 else roles[i % len(roles)]
                    loc = None if i == 0 else branch_ids[i % len(branch_ids)]
                    copy.write_row((enterprise_id, mid, uid, role, loc, "active"))

            # 4. Seed one published bookable service + variant per company for read/write workload
            with cur.copy("copy gba.services (tenant_id, id, code, name) from stdin") as copy:
                for i, tid in enumerate(tenant_ids):
                    sid = _det_uuid(config.seed, "svc", i)
                    copy.write_row((tid, sid, f"SVC_{i:04d}", f"FAKE Service {i:04d}"))

            with cur.copy(
                "copy gba.service_variants "
                "(tenant_id, id, service_id, code, name, status, price_cents, currency, "
                "booking_duration_minutes, is_bookable) from stdin"
            ) as copy:
                for i, tid in enumerate(tenant_ids):
                    sid = _det_uuid(config.seed, "svc", i)
                    vid = _det_uuid(config.seed, "var", i)
                    variant_by_tenant[tid] = vid
                    copy.write_row(
                        (
                            tid,
                            vid,
                            sid,
                            f"VAR_{i:04d}",
                            f"FAKE Variant {i:04d}",
                            "published",
                            5000 + (i % 50) * 100,
                            "USD",
                            60,
                            True,
                        )
                    )

            # 5. Seed historical operational records across all companies in gba.audit_events
            base_ts = datetime(2026, 1, 1, tzinfo=UTC)
            with cur.copy(
                "copy gba.audit_events "
                "(id, tenant_id, actor, action, target_type, target_id, details, occurred_at) "
                "from stdin"
            ) as copy:
                n_tenants = len(tenant_ids)
                for i in range(config.historical_records):
                    tid = tenant_ids[i % n_tenants]
                    eid = _det_uuid(config.seed, "hist", i)
                    occurred = base_ts + timedelta(seconds=i * 15)
                    copy.write_row(
                        (
                            eid,
                            tid,
                            "ops02:seeder",
                            "booking.recorded",
                            "booking",
                            f"fake-hist-{i}",
                            "{}",
                            occurred,
                        )
                    )
            cur.execute("analyze gba.audit_events")
            cur.execute("analyze gba.service_variants")
        conn.commit()

    seed_seconds = round(time.perf_counter() - t0, 3)
    return SeededDataset(
        tenant_ids=tenant_ids,
        enterprise_tenant_id=enterprise_id,
        enterprise_branch_ids=branch_ids,
        variant_by_tenant=variant_by_tenant,
        distribution=DataDistribution(
            companies=config.companies,
            enterprise_branches=config.enterprise_branches,
            enterprise_staff=config.enterprise_staff,
            historical_records=config.historical_records,
            service_variants=config.companies,
        ),
        seed_seconds=seed_seconds,
    )


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


async def _run_read(
    pool: RuntimePool,
    tenant_id: UUID,
    location_id: UUID | None,
) -> tuple[int, int]:
    """Return (cross_tenant_leaks, invariant_violations)."""
    leaks = 0
    violations = 0
    async with tenant_transaction(pool, tenant_id) as conn:
        if location_id is not None:
            await conn.execute(
                "select pg_catalog.set_config('gba.location_id', %s, true)",
                (str(location_id),),
            )
        rows = await (
            await conn.execute(
                "select tenant_id, id, price_cents, revision "
                "from gba.service_variants order by id limit 20"
            )
        ).fetchall()
        locs = await (
            await conn.execute("select tenant_id, id from gba.locations order by id limit 25")
        ).fetchall()
    for row in rows:
        if row[0] != tenant_id:
            leaks += 1
        if int(row[2]) < 0 or int(row[3]) < 1:
            violations += 1
    for loc in locs:
        if loc[0] != tenant_id or (location_id is not None and loc[1] != location_id):
            leaks += 1
    return leaks, violations


async def _run_write(
    pool: RuntimePool,
    tenant_id: UUID,
    variant_id: UUID,
    *,
    force_stale_conflict: bool,
) -> tuple[bool, int, int]:
    """Return (expected_conflict, cross_tenant_leaks, invariant_violations)."""
    leaks = 0
    violations = 0
    async with tenant_transaction(pool, tenant_id) as conn:
        cur = await conn.execute(
            "select tenant_id, price_cents, revision from gba.service_variants where id = %s",
            (variant_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return False, 0, 1
        if row[0] != tenant_id:
            leaks += 1
        old_price = int(row[1])
        current_rev = int(row[2])
        expected_rev = current_rev - 1 if force_stale_conflict else current_rev
        new_price = old_price + 10 if old_price < 50_000 else 5_000
        upd = await conn.execute(
            "update gba.service_variants set price_cents = %s "
            "where id = %s and revision = %s returning tenant_id, price_cents, revision",
            (new_price, variant_id, expected_rev),
        )
        updated = await upd.fetchone()
        if updated is None:
            return True, leaks, violations
        if updated[0] != tenant_id:
            leaks += 1
        if int(updated[1]) != new_price or int(updated[2]) != current_rev + 1:
            violations += 1
    return False, leaks, violations


async def _run_report(
    pool: RuntimePool,
    tenant_id: UUID,
) -> tuple[int, int]:
    """Run aggregate report/search over catalog and historical audit records under RLS."""
    leaks = 0
    violations = 0
    async with tenant_transaction(pool, tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select tenant_id, count(*), min(occurred_at), max(occurred_at) "
                "from gba.audit_events group by tenant_id"
            )
        ).fetchall()
        cat = await (
            await conn.execute(
                "select tenant_id, count(*), coalesce(sum(price_cents), 0) "
                "from gba.service_variants group by tenant_id"
            )
        ).fetchall()
    for row in rows:
        if row[0] != tenant_id:
            leaks += 1
        if int(row[1]) < 0:
            violations += 1
    for row in cat:
        if row[0] != tenant_id:
            leaks += 1
        if int(row[2]) < 0:
            violations += 1
    return leaks, violations


async def run_load_benchmark(
    *,
    admin_db_dsn: str,
    app_dsn: str,
    config: LoadProfileConfig,
    allow_remote: bool = False,
) -> LoadBenchmarkReport:
    """Seed dataset and execute mixed 70/20/10 concurrent workload under gba_runtime RLS."""
    assert_isolated_test_target(admin_db_dsn, allow_remote=allow_remote)
    assert_isolated_test_target(app_dsn, allow_remote=allow_remote)

    dataset = seed_synthetic_dataset(admin_db_dsn, config, allow_remote=allow_remote)
    schedule = build_operation_schedule(config.total_operations, config.seed)

    with psycopg.connect(admin_db_dsn) as conn:
        ver_row = conn.execute("show server_version").fetchone()
        pg_version = str(ver_row[0]) if ver_row is not None else "unknown"

    read_samples: list[float] = []
    write_samples: list[float] = []
    report_samples: list[float] = []
    expected_conflicts = 0
    unexpected_errors = 0
    cross_tenant_leaks = 0
    invariant_violations = 0
    write_counter = 0

    queue: asyncio.Queue[tuple[int, OpKind]] = asyncio.Queue()
    for idx, op in enumerate(schedule):
        queue.put_nowait((idx, op))

    lock = asyncio.Lock()

    async def worker(pool: RuntimePool) -> None:
        nonlocal expected_conflicts, unexpected_errors, cross_tenant_leaks
        nonlocal invariant_violations, write_counter
        while True:
            try:
                idx, op = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            t_start = time.perf_counter()
            tid = dataset.tenant_ids[idx % len(dataset.tenant_ids)]
            try:
                if op == "read":
                    loc_id = (
                        dataset.enterprise_branch_ids[idx % len(dataset.enterprise_branch_ids)]
                        if tid == dataset.enterprise_tenant_id
                        else None
                    )
                    leaks, viols = await _run_read(pool, tid, loc_id)
                    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
                    async with lock:
                        read_samples.append(elapsed_ms)
                        cross_tenant_leaks += leaks
                        invariant_violations += viols
                elif op == "write":
                    async with lock:
                        write_counter += 1
                        w_num = write_counter
                    stale = (
                        config.inject_conflict_every > 0
                        and w_num % config.inject_conflict_every == 0
                    )
                    conflict, leaks, viols = await _run_write(
                        pool,
                        tid,
                        dataset.variant_by_tenant[tid],
                        force_stale_conflict=stale,
                    )
                    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
                    async with lock:
                        write_samples.append(elapsed_ms)
                        if conflict:
                            expected_conflicts += 1
                        cross_tenant_leaks += leaks
                        invariant_violations += viols
                else:
                    leaks, viols = await _run_report(pool, tid)
                    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
                    async with lock:
                        report_samples.append(elapsed_ms)
                        cross_tenant_leaks += leaks
                        invariant_violations += viols
            except Exception:
                async with lock:
                    unexpected_errors += 1
            finally:
                queue.task_done()

    t_bench = time.perf_counter()
    async with create_runtime_pool(
        app_dsn,
        min_size=min(4, config.pool_max_size),
        max_size=config.pool_max_size,
    ) as pool:
        tasks = [asyncio.create_task(worker(pool)) for _ in range(config.concurrency)]
        await asyncio.gather(*tasks)
    bench_seconds = round(time.perf_counter() - t_bench, 3)

    read_lat = compute_latency_summary(read_samples)
    write_lat = compute_latency_summary(write_samples)
    report_lat = compute_latency_summary(report_samples)
    err_rate = round((unexpected_errors / config.total_operations) * 100.0, 4)
    throughput = round(config.total_operations / max(bench_seconds, 0.001), 2)
    targets_met = evaluate_targets(
        read_latency=read_lat,
        write_latency=write_lat,
        unexpected_error_rate_pct=err_rate,
        cross_tenant_leaks=cross_tenant_leaks,
        invariant_violations=invariant_violations,
    )
    return LoadBenchmarkReport(
        mode=config.mode,
        seed=config.seed,
        distribution=dataset.distribution,
        seed_seconds=dataset.seed_seconds,
        benchmark_seconds=bench_seconds,
        total_operations=config.total_operations,
        read_ops=len(read_samples),
        write_ops=len(write_samples),
        report_ops=len(report_samples),
        expected_conflicts=expected_conflicts,
        unexpected_errors=unexpected_errors,
        unexpected_error_rate_pct=err_rate,
        cross_tenant_leaks=cross_tenant_leaks,
        invariant_violations=invariant_violations,
        throughput_ops_per_sec=throughput,
        read_latency_ms=read_lat,
        write_latency_ms=write_lat,
        report_latency_ms=report_lat,
        targets_met=targets_met,
        environment=BenchmarkEnvironment(
            python_version=platform.python_version(),
            platform=platform.platform(),
            cpu_count=os.cpu_count() or 1,
            postgres_version=pg_version,
            pool_min_size=min(4, config.pool_max_size),
            pool_max_size=config.pool_max_size,
            concurrency=config.concurrency,
            adapters="real_pg18_rls+synthetic_fake_tenants_no_external_providers",
            git_sha=_git_sha(),
            full_soak_40m_completed=config.full_soak_40m_completed,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OPS-02 reproducible load profile.")
    parser.add_argument("--admin-db-dsn", required=True)
    parser.add_argument("--app-dsn", required=True)
    parser.add_argument("--mode", choices=["ci-smoke", "full-1000"], default="ci-smoke")
    parser.add_argument("--operations", type=int, default=None)
    parser.add_argument("--historical-records", type=int, default=None)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--out-json", default=None)
    args = parser.parse_args()

    cfg = preset_config(args.mode)
    updates: dict[str, object] = {}
    if args.operations is not None:
        updates["total_operations"] = args.operations
    if args.historical_records is not None:
        updates["historical_records"] = args.historical_records
    if updates:
        cfg = cfg.model_copy(update=updates)

    report = asyncio.run(
        run_load_benchmark(
            admin_db_dsn=args.admin_db_dsn,
            app_dsn=args.app_dsn,
            config=cfg,
            allow_remote=args.allow_remote,
        )
    )
    payload = json.dumps(report.model_dump(mode="json"), indent=2) + "\n"
    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 0 if report.targets_met else 1


if __name__ == "__main__":
    sys.exit(main())
