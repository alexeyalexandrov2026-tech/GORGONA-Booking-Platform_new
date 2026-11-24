"""Unit contract tests for OPS-02 load profile guards, mix schedule, and SLA targets."""

import pytest
from tools.ops_load_profile import (
    GENERATOR_VERSION,
    LatencySummary,
    assert_isolated_test_target,
    build_operation_schedule,
    compute_latency_summary,
    evaluate_targets,
    preset_config,
    require_fake_company_name,
)


def test_fake_company_name_guard_enforces_prefix() -> None:
    assert require_fake_company_name("FAKE Enterprise Holding") == "FAKE Enterprise Holding"
    with pytest.raises(ValueError, match="FAKE "):
        require_fake_company_name("Real Salon LLC")


def test_isolated_test_target_blocks_remote_hosts_by_default() -> None:
    assert_isolated_test_target("postgresql://postgres@127.0.0.1:5432/gba_test")
    assert_isolated_test_target("postgresql://postgres@localhost:5432/gba_test")
    with pytest.raises(ValueError, match="non-loopback"):
        assert_isolated_test_target("postgresql://postgres@prod-db.example.com:5432/gba")
    assert_isolated_test_target(
        "postgresql://postgres@prod-db.example.com:5432/gba",
        allow_remote=True,
    )


def test_operation_schedule_matches_exact_70_20_10_mix_deterministically() -> None:
    s1 = build_operation_schedule(1000, seed=42)
    s2 = build_operation_schedule(1000, seed=42)
    assert s1 == s2
    assert s1.count("read") == 700
    assert s1.count("write") == 200
    assert s1.count("report") == 100


def test_latency_summary_and_target_evaluation() -> None:
    assert GENERATOR_VERSION == "1.0.0"
    summary = compute_latency_summary([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
    assert summary.count == 10
    assert summary.p50_ms == 50.0
    assert summary.p95_ms == 100.0
    assert summary.max_ms == 100.0

    ok_read = LatencySummary(count=70, p50_ms=5.0, p95_ms=25.0, p99_ms=40.0, max_ms=50.0)
    ok_write = LatencySummary(count=20, p50_ms=10.0, p95_ms=80.0, p99_ms=120.0, max_ms=150.0)
    assert (
        evaluate_targets(
            read_latency=ok_read,
            write_latency=ok_write,
            unexpected_error_rate_pct=0.0,
            cross_tenant_leaks=0,
            invariant_violations=0,
        )
        is True
    )
    assert (
        evaluate_targets(
            read_latency=LatencySummary(
                count=70, p50_ms=10.0, p95_ms=501.0, p99_ms=600.0, max_ms=700.0
            ),
            write_latency=ok_write,
            unexpected_error_rate_pct=0.0,
            cross_tenant_leaks=0,
            invariant_violations=0,
        )
        is False
    )
    assert (
        evaluate_targets(
            read_latency=ok_read,
            write_latency=ok_write,
            unexpected_error_rate_pct=0.1,
            cross_tenant_leaks=0,
            invariant_violations=0,
        )
        is False
    )
    assert (
        evaluate_targets(
            read_latency=ok_read,
            write_latency=ok_write,
            unexpected_error_rate_pct=0.0,
            cross_tenant_leaks=1,
            invariant_violations=0,
        )
        is False
    )


def test_full_1000_preset_matches_master_plan_scale() -> None:
    full = preset_config("full-1000")
    assert full.companies == 1_000
    assert full.enterprise_branches == 100
    assert full.enterprise_staff == 10_000
    assert full.historical_records == 1_000_000
    assert full.full_soak_40m_completed is False
