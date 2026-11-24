"""OPS-02 integration test: reproducible 70/20/10 load profile against real PG18 RLS."""

import secrets

import pytest
from psycopg.conninfo import make_conninfo
from tools.ops_load_profile import preset_config, run_load_benchmark

from tests.integration.conftest import ProvisionedDatabase

pytestmark = pytest.mark.anyio


async def test_ops02_ci_smoke_load_profile_meets_targets_with_zero_leaks(
    test_database: ProvisionedDatabase,
) -> None:
    admin_db_dsn = make_conninfo(test_database.admin_dsn, dbname=test_database.name)
    cfg = preset_config("ci-smoke").model_copy(update={"seed": secrets.randbelow(900_000) + 10_000})
    report = await run_load_benchmark(
        admin_db_dsn=admin_db_dsn,
        app_dsn=test_database.app_dsn,
        config=cfg,
    )
    assert report.distribution.companies == 20
    assert report.distribution.enterprise_branches == 10
    assert report.distribution.enterprise_staff == 100
    assert report.distribution.historical_records == 1_000
    assert report.read_ops == 140
    assert report.write_ops == 40
    assert report.report_ops == 20
    assert report.expected_conflicts >= 2
    assert report.unexpected_errors == 0
    assert report.unexpected_error_rate_pct == 0.0
    assert report.cross_tenant_leaks == 0
    assert report.invariant_violations == 0
    assert report.read_latency_ms.p95_ms <= 500.0
    assert report.write_latency_ms.p95_ms <= 1000.0
    assert report.targets_met is True
