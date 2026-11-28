"""Unit tests for AMARKAL v2.33.0 Visual BPMN Workflow & Approval Chain Engine."""

from __future__ import annotations

from pathlib import Path

import gorgona_booking
from gorgona_booking.api.workflow_bpmn import CreateWorkflowRequest
from gorgona_booking.business.workflow_bpmn import (
    BPMN_PRESET_TEMPLATES,
    advance_bpmn_execution,
    evaluate_gateway_condition,
    export_bpmn_20_xml,
    generate_bpmn_from_prompt,
    validate_bpmn_graph,
)


def test_all_enterprise_bpmn_presets_are_valid_acyclic_dags() -> None:
    assert len(BPMN_PRESET_TEMPLATES) == 3
    for tpl in BPMN_PRESET_TEMPLATES:
        parsed = CreateWorkflowRequest.model_validate(tpl)
        check = validate_bpmn_graph(
            [n.model_dump() for n in parsed.nodes],
            [e.model_dump() for e in parsed.edges],
            trigger_entity=parsed.trigger_entity,
        )
        assert check.valid is True, check.errors
        assert check.warnings == ()


def test_validator_rejects_cycles_invalid_ops_and_warns_missing_hitl() -> None:
    cyclic_nodes = [
        {"id": "s", "node_type": "start_trigger", "label": "Start", "x": 0, "y": 0, "config": {}},
        {"id": "a", "node_type": "human_approval", "label": "A", "x": 100, "y": 0, "config": {}},
        {"id": "b", "node_type": "human_approval", "label": "B", "x": 200, "y": 0, "config": {}},
        {"id": "e", "node_type": "end_approved", "label": "End", "x": 300, "y": 0, "config": {}},
    ]
    cyclic_edges = [
        {"id": "e1", "source_id": "s", "target_id": "a", "label": "", "branch": "default"},
        {"id": "e2", "source_id": "a", "target_id": "b", "label": "", "branch": "default"},
        {"id": "e3", "source_id": "b", "target_id": "a", "label": "", "branch": "default"},
        {"id": "e4", "source_id": "b", "target_id": "e", "label": "", "branch": "default"},
    ]
    res_cycle = validate_bpmn_graph(cyclic_nodes, cyclic_edges, trigger_entity="contract")
    assert res_cycle.valid is False
    assert any("cycle" in e.lower() for e in res_cycle.errors)

    # Financial trigger without human approval produces HITL warning
    no_hitl_nodes = [
        {"id": "s", "node_type": "start_trigger", "label": "Start", "x": 0, "y": 0, "config": {}},
        {
            "id": "ai",
            "node_type": "ai_compliance_check",
            "label": "AI",
            "x": 100,
            "y": 0,
            "config": {},
        },
        {"id": "e", "node_type": "end_approved", "label": "End", "x": 200, "y": 0, "config": {}},
    ]
    no_hitl_edges = [
        {"id": "e1", "source_id": "s", "target_id": "ai", "label": "", "branch": "default"},
        {"id": "e2", "source_id": "ai", "target_id": "e", "label": "", "branch": "default"},
    ]
    res_warn = validate_bpmn_graph(no_hitl_nodes, no_hitl_edges, trigger_entity="contract")
    assert res_warn.valid is True
    assert any("HITL" in w for w in res_warn.warnings)


def test_50k_contract_bpmn_routes_high_value_to_legal_cfo_ai_and_low_to_fasttrack() -> None:
    tpl = BPMN_PRESET_TEMPLATES[0]

    # Live run for $75,000 contract -> must pause at Legal Counsel HITL gate
    status_live, cur_live, trace_live, visited_live = advance_bpmn_execution(
        nodes=tpl["nodes"],
        edges=tpl["edges"],
        amount_cents=7_500_000,
        context={"region": "Midwest", "risk_score": 15},
        dry_run=False,
    )
    assert status_live == "awaiting_approval"
    assert cur_live == "n_legal"
    assert visited_live == ["n_start", "n_gate_50k", "n_legal"]
    assert trace_live[1]["outcome"] == "branch_yes"

    # Dry-run for $75,000 contract -> Legal -> CFO -> AI Check -> Approved
    status_dry, _, _, visited_dry = advance_bpmn_execution(
        nodes=tpl["nodes"],
        edges=tpl["edges"],
        amount_cents=7_500_000,
        context={"region": "Midwest", "risk_score": 15},
        dry_run=True,
    )
    assert status_dry == "approved"
    assert visited_dry == ["n_start", "n_gate_50k", "n_legal", "n_cfo", "n_ai_check", "n_end_ok"]

    # Dry-run for $20,000 contract -> Manager Fast-Track -> Approved
    status_low, _, _, visited_low = advance_bpmn_execution(
        nodes=tpl["nodes"],
        edges=tpl["edges"],
        amount_cents=2_000_000,
        context={"region": "Midwest"},
        dry_run=True,
    )
    assert status_low == "approved"
    assert visited_low == ["n_start", "n_gate_50k", "n_mgr_fast", "n_end_ok"]


def test_gateway_in_operator_and_ru_prompt_generation_and_bpmn_xml_export() -> None:
    ok, _ = evaluate_gateway_condition(
        {"field": "region", "operator": "in", "value": ["Midwest", "South"]},
        amount_cents=100_000,
        context={"region": "midwest"},
    )
    assert ok is True

    draft = generate_bpmn_from_prompt(
        "если сумма контракта > $50k -> отправить юристу -> затем фин директору -> ИИ-проверка"
    )
    check = validate_bpmn_graph(draft["nodes"], draft["edges"], trigger_entity="contract")
    assert check.valid is True
    node_ids = {n["id"] for n in draft["nodes"]}
    assert {"n_start", "n_gate", "n_legal", "n_cfo", "n_ai", "n_mgr", "n_approved"}.issubset(
        node_ids
    )

    xml_str = export_bpmn_20_xml(
        workflow_code=draft["workflow_code"],
        display_name="Contract > $50k & Audit",
        nodes=draft["nodes"],
        edges=draft["edges"],
    )
    assert "<bpmn:definitions " in xml_str
    assert "<bpmn:exclusiveGateway " in xml_str
    assert "<bpmn:sequenceFlow " in xml_str
    assert "&amp;" in xml_str
    assert xml_str.strip().endswith("</bpmn:definitions>")


def test_migration_0170_enforces_force_rls_without_security_definer() -> None:
    mig_path = (
        Path(gorgona_booking.__file__).parent
        / "db"
        / "migrations"
        / "0170_bpmn_visual_workflows.sql"
    )
    sql = mig_path.read_text(encoding="utf-8")
    non_comment_sql = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    assert "ENABLE ROW LEVEL SECURITY" in non_comment_sql
    assert "FORCE ROW LEVEL SECURITY" in non_comment_sql
    assert "gba.bpmn_workflows" in non_comment_sql
    assert "gba.bpmn_workflow_instances" in non_comment_sql
    assert "SECURITY DEFINER" not in non_comment_sql.upper()
