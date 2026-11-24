"""Run the full pytest suite across isolated worker databases inside one PostgreSQL server.

Design:
- Collect all tests once (`pytest --collect-only`) so zero tests can be silently dropped.
- Partition collected test files into three mathematically disjoint lanes:
  1. Serial lane: files that mutate cluster-global PostgreSQL roles or drop shared schema objects
     (e.g. `test_location_access.py`, followed by policy-sensitive tests in the same session).
  2. Browser lane: all `test_*_browser.py` files run sequentially in one dedicated lane to avoid
     Playwright `web/test-results/` races and Chromium CPU contention.
  3. Parallel API/unit lanes: remaining files balanced across N workers via greedy LPT packing.
- Build ONE template database with all migrations once, clone one database per parallel/browser
  worker with `CREATE DATABASE ... TEMPLATE`, run the parallel and browser lanes concurrently,
  drop all cloned + template databases, then run the serial lane on a fresh bootstrapped database.
- Merge JUnit XML reports and verify exact executed test count == collected test count with zero
  duplicates.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from tests.integration.conftest import TEST_APP_ROLE, TEST_OWNER_ROLE
from tests.integration.test_provider_event_inbox import WRITER_ROLE
from tests.integration.test_provider_receipt_decisions import WORKER_ROLE

from gorgona_booking.db.bootstrap import RUNTIME_GROUP, BootstrapSpec, bootstrap
from gorgona_booking.db.migrate import apply_migrations

# Ordered serial lane: test_location_access runs before delegations and R-09 problem reports
# in the same session so any missing policy restore after CASCADE drop is caught immediately.
SERIAL_FILES: tuple[str, ...] = (
    "tests/integration/test_location_access.py",
    "tests/integration/test_delegations.py",
    "tests/integration/test_r09_rental_problem_reports.py",
    "tests/integration/test_bootstrap_order.py",
    "tests/integration/test_roles_and_migrations.py",
    "tests/integration/test_resource_occupancy.py",
    "tests/integration/test_provider_admission_anchor.py",
    "tests/integration/test_provider_receipt_processes.py",
    "tests/integration/test_provider_guard_additions.py",
    "tests/integration/test_provider_event_inbox.py",
    "tests/integration/test_provider_receipt_decisions.py",
    "tests/integration/test_provider_receipt_attestations.py",
    "tests/integration/test_provider_receipt_guard_review.py",
    "tests/integration/test_workforce_guards.py",
    "tests/integration/test_ops_recovery_and_replay.py",
    "tests/integration/test_ops_load_profile.py",
)

# Heavier non-browser integration files get explicit weights so LPT balances worker runtimes.
KNOWN_WEIGHTS: dict[str, float] = {
    "tests/integration/test_k6a_event_permutations.py": 120.0,
    "tests/integration/test_k6a_bounded_retries.py": 85.0,
    "tests/integration/test_stock_upgrade.py": 75.0,
    "tests/integration/test_timesheet_guards.py": 42.0,
    "tests/integration/test_stock_guards.py": 35.0,
    "tests/integration/test_shift_changes_guards.py": 34.0,
    "tests/integration/test_provider_payments.py": 32.0,
    "tests/integration/test_k6b_event_backfill.py": 30.0,
    "tests/integration/test_settlements.py": 26.0,
    "tests/integration/test_credit_notes.py": 25.0,
    "tests/integration/test_external_payments.py": 25.0,
}


@dataclass(frozen=True, slots=True)
class LanePartition:
    serial: list[str]
    browser: list[str]
    parallel_buckets: list[list[str]]


@dataclass(frozen=True, slots=True)
class LaneResult:
    name: str
    returncode: int
    seconds: float
    xml_path: Path
    log_path: Path
    tests: int
    passed: int
    failed: int
    skipped: int
    failures: tuple[str, ...]
    skips: tuple[str, ...]
    case_ids: tuple[str, ...]


def is_browser_file(rel_path: str) -> bool:
    name = Path(rel_path).name
    return name.startswith("test_") and name.endswith("_browser.py")


def partition_files(
    collected_files: list[str],
    *,
    workers: int,
    api_dir: Path,
    serial_files: tuple[str, ...] = SERIAL_FILES,
) -> LanePartition:
    if workers < 1:
        raise ValueError("workers must be at least 1")
    collected_set = set(collected_files)
    serial = [f for f in serial_files if f in collected_set]
    serial_set = set(serial)
    browser = sorted(f for f in collected_files if f not in serial_set and is_browser_file(f))
    browser_set = set(browser)
    parallel_all = [f for f in collected_files if f not in serial_set and f not in browser_set]

    def weight(rel: str) -> float:
        if rel in KNOWN_WEIGHTS:
            return KNOWN_WEIGHTS[rel]
        path = api_dir / rel
        size_kb = (path.stat().st_size / 1024.0) if path.exists() else 1.0
        if rel.startswith("tests/unit/"):
            return max(0.2, size_kb * 0.05)
        return max(1.0, size_kb * 0.4)

    buckets: list[list[str]] = [[] for _ in range(workers)]
    loads = [0.0 for _ in range(workers)]
    for rel in sorted(parallel_all, key=lambda item: (-weight(item), item)):
        idx = min(range(workers), key=lambda i: loads[i])
        buckets[idx].append(rel)
        loads[idx] += weight(rel)
    non_empty = [sorted(bucket) for bucket in buckets if bucket]

    # Mathematical invariants: pairwise disjoint and complete union.
    seen: set[str] = set()
    for group in (serial, browser, *non_empty):
        overlap = seen.intersection(group)
        if overlap:
            raise AssertionError(f"Duplicate files across lanes: {sorted(overlap)}")
        seen.update(group)
    if seen != collected_set:
        missing = sorted(collected_set - seen)
        extra = sorted(seen - collected_set)
        raise AssertionError(f"Partition mismatch: missing={missing} extra={extra}")
    return LanePartition(serial=serial, browser=browser, parallel_buckets=non_empty)


def collect_suite(api_dir: Path, python_exe: str) -> tuple[list[str], int]:
    proc = subprocess.run(  # noqa: S603 - fixed local pytest invocation
        [python_exe, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=api_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pytest --collect-only failed:\n{proc.stdout}\n{proc.stderr}")
    files: set[str] = set()
    node_count = 0
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if "::" in line and line.startswith("tests/"):
            node_count += 1
            files.add(line.split("::", 1)[0])
    if node_count == 0 or not files:
        raise RuntimeError(f"No tests collected:\n{proc.stdout}")
    return sorted(files), node_count


def create_template_and_clones(
    admin_dsn: str,
    clone_names: list[str],
    *,
    owner_password: str,
    app_password: str,
    writer_password: str,
    worker_password: str,
) -> str:
    template_name = f"gba_test_tpl_{secrets.token_hex(5)}"
    bootstrap(
        admin_dsn,
        BootstrapSpec(
            database=template_name,
            owner_role=TEST_OWNER_ROLE,
            owner_password=owner_password,
            app_role=TEST_APP_ROLE,
            app_password=app_password,
            receipt_writer_role=WRITER_ROLE,
            receipt_writer_password=writer_password,
            receipt_worker_role=WORKER_ROLE,
            receipt_worker_password=worker_password,
        ),
    )
    owner_dsn = make_conninfo(
        admin_dsn, dbname=template_name, user=TEST_OWNER_ROLE, password=owner_password
    )
    apply_migrations(owner_dsn)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        for db_name in clone_names:
            conn.execute(
                sql.SQL("create database {} owner {} template {}").format(
                    sql.Identifier(db_name),
                    sql.Identifier(TEST_OWNER_ROLE),
                    sql.Identifier(template_name),
                )
            )
            conn.execute(
                sql.SQL("revoke all on database {} from public").format(sql.Identifier(db_name))
            )
            for grantee in (RUNTIME_GROUP, WRITER_ROLE, WORKER_ROLE):
                conn.execute(
                    sql.SQL("grant connect on database {} to {}").format(
                        sql.Identifier(db_name), sql.Identifier(grantee)
                    )
                )
    return template_name


def drop_databases(admin_dsn: str, names: list[str]) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        for name in names:
            conn.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
            )


def parse_junit(
    xml_path: Path,
) -> tuple[int, int, int, int, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    cases = list(ElementTree.parse(xml_path).iter("testcase"))  # noqa: S314 - local pytest XML
    failures: list[str] = []
    skips: list[str] = []
    case_ids: list[str] = []
    for c in cases:
        cid = f"{c.get('classname', '')}::{c.get('name', '')}"
        case_ids.append(cid)
        fail_node = c.find("failure") if c.find("failure") is not None else c.find("error")
        skip_node = c.find("skipped")
        if fail_node is not None:
            msg = " ".join((fail_node.get("message") or "").split())[:220]
            failures.append(f"{cid} {msg}")
        elif skip_node is not None:
            msg = (skip_node.get("message") or "")[:160]
            skips.append(f"{cid} {msg}")
    total = len(cases)
    failed = len(failures)
    skipped = len(skips)
    passed = total - failed - skipped
    return total, passed, failed, skipped, tuple(failures), tuple(skips), tuple(case_ids)


def run_lane(
    name: str,
    files: list[str],
    *,
    api_dir: Path,
    out_dir: Path,
    python_exe: str,
    env: dict[str, str],
) -> LaneResult:
    xml_path = out_dir / f"{name}.xml"
    log_path = out_dir / f"{name}.log"
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.run(  # noqa: S603 - fixed local pytest invocation
            [
                python_exe,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--junitxml={xml_path}",
                *files,
            ],
            cwd=api_dir,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.monotonic() - started
    if not xml_path.exists():
        return LaneResult(
            name=name,
            returncode=proc.returncode or 1,
            seconds=elapsed,
            xml_path=xml_path,
            log_path=log_path,
            tests=0,
            passed=0,
            failed=1,
            skipped=0,
            failures=(f"{name} produced no JUnit XML (exit={proc.returncode})",),
            skips=(),
            case_ids=(),
        )
    tests, passed, failed, skipped, failures, skips, case_ids = parse_junit(xml_path)
    return LaneResult(
        name=name,
        returncode=proc.returncode,
        seconds=elapsed,
        xml_path=xml_path,
        log_path=log_path,
        tests=tests,
        passed=passed,
        failed=failed,
        skipped=skipped,
        failures=failures,
        skips=skips,
        case_ids=case_ids,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run full GORGONA pytest suite in parallel.")
    parser.add_argument("--workers", type=int, default=6, help="Number of parallel API workers.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for logs and XML.")
    args = parser.parse_args(argv)

    admin_dsn = os.environ.get("GBA_TEST_ADMIN_DSN")
    if not admin_dsn:
        sys.stderr.write("GBA_TEST_ADMIN_DSN must be set\n")
        return 2

    api_dir = Path(__file__).resolve().parents[1]
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    python_exe = sys.executable

    t0 = time.monotonic()
    collected_files, expected_count = collect_suite(api_dir, python_exe)
    partition = partition_files(collected_files, workers=args.workers, api_dir=api_dir)
    sys.stdout.write(
        f"PAR_PLAN collected={expected_count} files={len(collected_files)} "
        f"workers={len(partition.parallel_buckets)} browser_files={len(partition.browser)} "
        f"serial_files={len(partition.serial)}\n"
    )
    sys.stdout.flush()

    owner_pw = secrets.token_urlsafe(24)
    app_pw = secrets.token_urlsafe(24)
    writer_pw = secrets.token_urlsafe(32)
    worker_pw = secrets.token_urlsafe(32)

    run_tag = secrets.token_hex(4)
    clone_map: dict[str, str] = {}
    if partition.browser:
        clone_map["browser"] = f"gba_test_browser_{run_tag}"
    for i in range(len(partition.parallel_buckets)):
        clone_map[f"worker_{i + 1}"] = f"gba_test_w{i + 1}_{run_tag}"

    t_db = time.monotonic()
    template_db = create_template_and_clones(
        admin_dsn,
        list(clone_map.values()),
        owner_password=owner_pw,
        app_password=app_pw,
        writer_password=writer_pw,
        worker_password=worker_pw,
    )
    sys.stdout.write(
        f"PAR_TEMPLATE db={template_db} clones={len(clone_map)} "
        f"seconds={time.monotonic() - t_db:.2f}\n"
    )
    sys.stdout.flush()

    results: list[LaneResult] = []
    try:
        base_env = dict(os.environ)
        base_env["GBA_REQUIRE_POSTGRES"] = "1"
        base_env.setdefault("GBA_REQUIRE_BROWSER", "1")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(clone_map)) as pool:
            futures: list[concurrent.futures.Future[LaneResult]] = []
            if partition.browser:
                b_env = {
                    **base_env,
                    "GBA_TEST_PREBUILT_DB": clone_map["browser"],
                    "GBA_TEST_OWNER_PASSWORD": owner_pw,
                    "GBA_TEST_APP_PASSWORD": app_pw,
                    "GBA_TEST_WRITER_PASSWORD": writer_pw,
                    "GBA_TEST_WORKER_PASSWORD": worker_pw,
                }
                futures.append(
                    pool.submit(
                        run_lane,
                        "browser",
                        partition.browser,
                        api_dir=api_dir,
                        out_dir=out_dir,
                        python_exe=python_exe,
                        env=b_env,
                    )
                )
            for i, bucket in enumerate(partition.parallel_buckets):
                lane_name = f"worker_{i + 1}"
                w_env = {
                    **base_env,
                    "GBA_TEST_PREBUILT_DB": clone_map[lane_name],
                    "GBA_TEST_OWNER_PASSWORD": owner_pw,
                    "GBA_TEST_APP_PASSWORD": app_pw,
                    "GBA_TEST_WRITER_PASSWORD": writer_pw,
                    "GBA_TEST_WORKER_PASSWORD": worker_pw,
                }
                futures.append(
                    pool.submit(
                        run_lane,
                        lane_name,
                        bucket,
                        api_dir=api_dir,
                        out_dir=out_dir,
                        python_exe=python_exe,
                        env=w_env,
                    )
                )
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                results.append(res)
                sys.stdout.write(
                    f"PAR_LANE name={res.name} exit={res.returncode} seconds={res.seconds:.1f} "
                    f"tests={res.tests} passed={res.passed} "
                    f"failed={res.failed} skipped={res.skipped}\n"
                )
                sys.stdout.flush()
    finally:
        drop_databases(admin_dsn, [*clone_map.values(), template_db])

    if partition.serial:
        serial_env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in (
                "GBA_TEST_PREBUILT_DB",
                "GBA_TEST_OWNER_PASSWORD",
                "GBA_TEST_APP_PASSWORD",
                "GBA_TEST_WRITER_PASSWORD",
                "GBA_TEST_WORKER_PASSWORD",
            )
        }
        serial_env["GBA_REQUIRE_POSTGRES"] = "1"
        serial_env.setdefault("GBA_REQUIRE_BROWSER", "1")
        s_res = run_lane(
            "serial",
            partition.serial,
            api_dir=api_dir,
            out_dir=out_dir,
            python_exe=python_exe,
            env=serial_env,
        )
        results.append(s_res)
        sys.stdout.write(
            f"PAR_LANE name={s_res.name} exit={s_res.returncode} seconds={s_res.seconds:.1f} "
            f"tests={s_res.tests} passed={s_res.passed} "
            f"failed={s_res.failed} skipped={s_res.skipped}\n"
        )
        sys.stdout.flush()

    total_seconds = time.monotonic() - t0
    all_ids: list[str] = []
    all_failures: list[str] = []
    all_skips: list[str] = []
    total_tests = total_passed = total_failed = total_skipped = 0
    for r in results:
        total_tests += r.tests
        total_passed += r.passed
        total_failed += r.failed
        total_skipped += r.skipped
        all_ids.extend(r.case_ids)
        all_failures.extend(r.failures)
        all_skips.extend(r.skips)

    unique_ids = len(set(all_ids))
    duplicates = len(all_ids) - unique_ids
    count_ok = total_tests == expected_count and duplicates == 0

    summary = {
        "wall_seconds": round(total_seconds, 2),
        "expected_tests": expected_count,
        "executed_tests": total_tests,
        "unique_tests": unique_ids,
        "duplicates": duplicates,
        "passed": total_passed,
        "failed": total_failed,
        "skipped": total_skipped,
        "count_ok": count_ok,
        "lanes": [
            {
                "name": r.name,
                "returncode": r.returncode,
                "seconds": round(r.seconds, 2),
                "tests": r.tests,
                "passed": r.passed,
                "failed": r.failed,
                "skipped": r.skipped,
            }
            for r in sorted(results, key=lambda item: item.name)
        ],
        "failures": all_failures,
        "skips": all_skips,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    sys.stdout.write(
        f"PAR_SUMMARY wall={total_seconds:.1f}s expected={expected_count} tests={total_tests} "
        f"passed={total_passed} failed={total_failed} skipped={total_skipped} "
        f"duplicates={duplicates} count_ok={count_ok}\n"
    )
    for skip_line in all_skips:
        sys.stdout.write(f"PAR_SKIP {skip_line}\n")
    for fail_line in all_failures:
        sys.stdout.write(f"PAR_FAIL {fail_line}\n")
    sys.stdout.flush()

    if not count_ok or total_failed > 0 or any(r.returncode != 0 for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
