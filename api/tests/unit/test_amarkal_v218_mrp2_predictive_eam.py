"""Unit tests for AMARKAL v2.18.0: Enterprise MRP II BOM Explosion & Predictive EAM / IoT."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gorgona_booking.business.industrial_mrp_eam import (
    MrpMaterialView,
    MrpRecipeLineView,
    MrpRecipeView,
    compute_bom_explosion,
    evaluate_predictive_rule,
    generate_iot_ingest_token,
    hash_iot_token,
)


def _mat(
    sku: str,
    *,
    kind: str = "raw",
    unit: str = "ton",
    on_hand_milli: int = 0,
    reserved_milli: int = 0,
    unit_cost_cents: int = 10_000,
) -> MrpMaterialView:
    now = datetime.now(UTC)
    return MrpMaterialView(
        id=uuid4(),
        sku=sku,
        name=f"Material {sku}",
        material_kind=kind,  # type: ignore[arg-type]
        unit=unit,  # type: ignore[arg-type]
        on_hand_milli=on_hand_milli,
        reserved_milli=reserved_milli,
        available_milli=max(0, on_hand_milli - reserved_milli),
        reorder_point_milli=500,
        unit_cost_cents=unit_cost_cents,
        preferred_vendor_name="Midwest Raw Supply LLC",
        preferred_vendor_email="orders@midwestsupply.us",
        created_at=now,
        updated_at=now,
    )


def test_multilevel_bom_explosion_with_scrap_and_shortage() -> None:
    """1.000 ton finished steel mix needs 0.600 ton Raw A (+5% scrap) + 0.400 ton Sub B,
    where 1.000 ton Sub B needs 0.500 ton Raw A + 0.500 ton Raw C."""
    now = datetime.now(UTC)
    raw_a = _mat("RAW-A", on_hand_milli=1000, reserved_milli=300, unit_cost_cents=50_000)
    raw_c = _mat("RAW-C", on_hand_milli=100, reserved_milli=0, unit_cost_cents=80_000)
    sub_b = _mat("SUB-B", kind="subassembly", on_hand_milli=0, unit_cost_cents=0)
    fin_p = _mat("FIN-STEEL", kind="finished", on_hand_milli=0, unit_cost_cents=0)

    sub_recipe_id = uuid4()
    sub_recipe = MrpRecipeView(
        id=sub_recipe_id,
        code="BOM-SUB-B",
        name="Sub-Assembly B",
        output_material_id=sub_b.id,
        output_sku=sub_b.sku,
        output_name=sub_b.name,
        output_unit="ton",
        output_qty_milli=1000,
        lead_time_days=1,
        notes="",
        is_active=True,
        lines=[
            MrpRecipeLineView(
                id=uuid4(),
                recipe_id=sub_recipe_id,
                component_material_id=raw_a.id,
                component_sku=raw_a.sku,
                component_name=raw_a.name,
                component_unit="ton",
                qty_per_batch_milli=500,
                scrap_bps=0,
                notes="",
            ),
            MrpRecipeLineView(
                id=uuid4(),
                recipe_id=sub_recipe_id,
                component_material_id=raw_c.id,
                component_sku=raw_c.sku,
                component_name=raw_c.name,
                component_unit="ton",
                qty_per_batch_milli=500,
                scrap_bps=0,
                notes="",
            ),
        ],
        created_at=now,
        updated_at=now,
    )

    root_id = uuid4()
    root_recipe = MrpRecipeView(
        id=root_id,
        code="BOM-FIN-STEEL",
        name="Structural Steel Blend (1 ton)",
        output_material_id=fin_p.id,
        output_sku=fin_p.sku,
        output_name=fin_p.name,
        output_unit="ton",
        output_qty_milli=1000,
        lead_time_days=2,
        notes="",
        is_active=True,
        lines=[
            MrpRecipeLineView(
                id=uuid4(),
                recipe_id=root_id,
                component_material_id=raw_a.id,
                component_sku=raw_a.sku,
                component_name=raw_a.name,
                component_unit="ton",
                qty_per_batch_milli=600,
                scrap_bps=500,  # +5% scrap -> 630 milli
                notes="",
            ),
            MrpRecipeLineView(
                id=uuid4(),
                recipe_id=root_id,
                component_material_id=sub_b.id,
                component_sku=sub_b.sku,
                component_name=sub_b.name,
                component_unit="ton",
                qty_per_batch_milli=400,  # explodes to 200 RAW-A + 200 RAW-C
                scrap_bps=0,
                notes="",
            ),
        ],
        created_at=now,
        updated_at=now,
    )

    result = compute_bom_explosion(
        root_recipe=root_recipe,
        target_qty_milli=1000,
        materials_by_id={m.id: m for m in (raw_a, raw_c, sub_b, fin_p)},
        recipes_by_output_id={sub_b.id: sub_recipe, fin_p.id: root_recipe},
    )

    by_sku = {r.sku: r for r in result.requirements}
    # RAW-A: 630 (direct +5% scrap) + 200 (from SUB-B) = 830 milli; avail = 700 -> shortage = 130
    assert by_sku["RAW-A"].required_milli == 830
    assert by_sku["RAW-A"].available_milli == 700
    assert by_sku["RAW-A"].reservable_milli == 700
    assert by_sku["RAW-A"].shortage_milli == 130
    # RAW-C: 200 milli; avail = 100 -> shortage = 100
    assert by_sku["RAW-C"].required_milli == 200
    assert by_sku["RAW-C"].reservable_milli == 100
    assert by_sku["RAW-C"].shortage_milli == 100
    assert result.shortage_count == 2
    assert result.can_fully_reserve is False
    # Exact cost: 830/1000 * 50000 (=41500) + 200/1000 * 80000 (=16000) = 57500 cents
    assert result.total_material_cost_cents == 57_500


def test_bom_explosion_detects_circular_subassembly_cycle() -> None:
    now = datetime.now(UTC)
    s1 = _mat("SUB-1", kind="subassembly")
    s2 = _mat("SUB-2", kind="subassembly")
    r1_id, r2_id = uuid4(), uuid4()
    r1 = MrpRecipeView(
        id=r1_id,
        code="R1",
        name="R1",
        output_material_id=s1.id,
        output_sku=s1.sku,
        output_name=s1.name,
        output_unit="ton",
        output_qty_milli=1000,
        lead_time_days=1,
        notes="",
        is_active=True,
        lines=[
            MrpRecipeLineView(
                id=uuid4(),
                recipe_id=r1_id,
                component_material_id=s2.id,
                component_sku=s2.sku,
                component_name=s2.name,
                component_unit="ton",
                qty_per_batch_milli=1000,
                scrap_bps=0,
                notes="",
            )
        ],
        created_at=now,
        updated_at=now,
    )
    r2 = MrpRecipeView(
        id=r2_id,
        code="R2",
        name="R2",
        output_material_id=s2.id,
        output_sku=s2.sku,
        output_name=s2.name,
        output_unit="ton",
        output_qty_milli=1000,
        lead_time_days=1,
        notes="",
        is_active=True,
        lines=[
            MrpRecipeLineView(
                id=uuid4(),
                recipe_id=r2_id,
                component_material_id=s1.id,
                component_sku=s1.sku,
                component_name=s1.name,
                component_unit="ton",
                qty_per_batch_milli=1000,
                scrap_bps=0,
                notes="",
            )
        ],
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(ValueError, match="Circular BOM"):
        compute_bom_explosion(
            root_recipe=r1,
            target_qty_milli=1000,
            materials_by_id={s1.id: s1, s2.id: s2},
            recipes_by_output_id={s1.id: r1, s2.id: r2},
        )


def test_predictive_eam_rule_evaluation_and_iot_tokens() -> None:
    # Interval rule: service every 500 engine hours, 90% lead -> triggers at 450h BEFORE breakdown
    ok_ev = evaluate_predictive_rule(
        operator="interval_every",
        threshold_milli=500_000,
        warning_lead_pct=90,
        value_milli=1_400_000,
        last_triggered_milli=1_000_000,
        metric_key="engine_hours",
    )
    assert ok_ev.outcome == "ok"

    pre_ev = evaluate_predictive_rule(
        operator="interval_every",
        threshold_milli=500_000,
        warning_lead_pct=90,
        value_milli=1_460_000,
        last_triggered_milli=1_000_000,
        metric_key="engine_hours",
    )
    assert pre_ev.outcome == "triggered"
    assert "Predictive service window" in pre_ev.reason

    # High vibration threshold >= 7.0 mm/s
    vib_warn = evaluate_predictive_rule(
        operator="gte",
        threshold_milli=7_000,
        warning_lead_pct=85,
        value_milli=6_200,
        last_triggered_milli=0,
        metric_key="vibration_mm_s",
    )
    assert vib_warn.outcome == "warning"

    vib_hit = evaluate_predictive_rule(
        operator="gte",
        threshold_milli=7_000,
        warning_lead_pct=85,
        value_milli=7_500,
        last_triggered_milli=0,
        metric_key="vibration_mm_s",
    )
    assert vib_hit.outcome == "triggered"
    assert vib_hit.health_penalty == 30

    # Low oil pressure threshold <= 25 psi
    oil_hit = evaluate_predictive_rule(
        operator="lte",
        threshold_milli=25_000,
        warning_lead_pct=90,
        value_milli=21_000,
        last_triggered_milli=0,
        metric_key="oil_pressure_psi",
    )
    assert oil_hit.outcome == "triggered"

    raw, prefix, digest = generate_iot_ingest_token()
    assert raw.startswith("amk_iot_")
    assert raw.startswith(prefix)
    assert len(digest) == 64
    assert hash_iot_token(raw) == digest
