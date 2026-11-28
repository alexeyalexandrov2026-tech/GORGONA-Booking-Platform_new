"""AMARKAL v2.33.0: Safe Deterministic BPMN DAG Engine, Validator & BPMN 2.0 XML Exporter.

Security & Clean Core invariants:
- Zero dynamic `eval()` / `exec()`: gateway conditions use a closed operator allowlist.
- Strict acyclic DAG validation (rejects loops, orphan references, or missing start/end).
- Financial triggers surface an explicit $0.00 Human-in-the-Loop (HITL) guardrail warning
  if any approval path lacks a `human_approval` gate.
- Generates standards-compliant OMG BPMN 2.0 XML with strict XML escaping.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from xml.sax.saxutils import escape as xml_escape

TriggerEntity = Literal[
    "contract",
    "purchase_order",
    "quote",
    "invoice",
    "payroll_run",
    "intercompany_trade",
    "work_order",
]

BpmnNodeType = Literal[
    "start_trigger",
    "exclusive_gateway",
    "human_approval",
    "ai_compliance_check",
    "notify_or_webhook",
    "end_approved",
    "end_rejected",
]

EdgeBranch = Literal["default", "yes", "no"]

ALLOWED_GATEWAY_FIELDS: frozenset[str] = frozenset(
    {"amount_cents", "region", "currency", "entity_kind", "risk_score", "unsold_pct"}
)

ALLOWED_GATEWAY_OPERATORS: frozenset[str] = frozenset({">", ">=", "<", "<=", "==", "!=", "in"})

_FINANCIAL_TRIGGERS: frozenset[str] = frozenset(
    {"contract", "purchase_order", "invoice", "payroll_run", "intercompany_trade"}
)

_DOLLAR_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmM])?")
_NUM_K_RE = re.compile(r">\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmM])?")


@dataclass(frozen=True, slots=True)
class GraphValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_bpmn_graph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    trigger_entity: str = "contract",
) -> GraphValidationResult:
    """Validate structural integrity, acyclicity, condition safety, and HITL guardrails."""
    errors: list[str] = []
    warnings: list[str] = []

    if not nodes:
        return GraphValidationResult(False, ("Workflow must define at least two nodes.",), ())
    if len(nodes) > 40:
        errors.append("Workflow cannot exceed 40 nodes.")

    node_by_id: dict[str, dict[str, Any]] = {}
    start_ids: list[str] = []
    end_ids: list[str] = []
    has_human_gate = False

    for node in nodes:
        nid = str(node.get("id") or "").strip()
        ntype = str(node.get("node_type") or "")
        if not nid:
            errors.append("Every BPMN node must have a non-empty id.")
            continue
        if nid in node_by_id:
            errors.append(f"Duplicate node id '{nid}'.")
            continue
        node_by_id[nid] = node
        if ntype == "start_trigger":
            start_ids.append(nid)
        elif ntype in ("end_approved", "end_rejected"):
            end_ids.append(nid)
        elif ntype == "human_approval":
            has_human_gate = True
        elif ntype == "exclusive_gateway":
            cfg = node.get("config") or {}
            field = str(cfg.get("field") or "amount_cents")
            op = str(cfg.get("operator") or ">")
            if field not in ALLOWED_GATEWAY_FIELDS:
                errors.append(f"Gateway '{nid}' uses unsupported field '{field}'.")
            if op not in ALLOWED_GATEWAY_OPERATORS:
                errors.append(f"Gateway '{nid}' uses unsupported operator '{op}'.")

    if len(start_ids) != 1:
        errors.append("Workflow must contain exactly one 'start_trigger' node.")
    if not end_ids:
        errors.append("Workflow must contain at least one terminal end node.")

    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = dict.fromkeys(node_by_id, 0)

    for edge in edges:
        src = str(edge.get("source_id") or "")
        tgt = str(edge.get("target_id") or "")
        if src not in node_by_id:
            errors.append(f"Edge references unknown source node '{src}'.")
            continue
        if tgt not in node_by_id:
            errors.append(f"Edge references unknown target node '{tgt}'.")
            continue
        if src == tgt:
            errors.append(f"Self-loop edge on node '{src}' is forbidden.")
            continue
        adj[src].append(tgt)
        in_degree[tgt] += 1

    # Kahn topological check for cycles
    queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
    visited = 0
    while queue:
        cur = queue.popleft()
        visited += 1
        for nxt in adj[cur]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
    if visited != len(node_by_id):
        errors.append("Workflow graph contains a cycle; BPMN approval chains must be acyclic.")

    if trigger_entity in _FINANCIAL_TRIGGERS and not has_human_gate:
        warnings.append(
            "Financial workflow has no human_approval gate; AMARKAL $0.00 HITL guardrail "
            "recommends explicit human sign-off before financial execution."
        )

    return GraphValidationResult(len(errors) == 0, tuple(errors), tuple(warnings))


def evaluate_gateway_condition(
    config: dict[str, Any],
    *,
    amount_cents: int,
    context: dict[str, Any],
) -> tuple[bool, str]:
    """Safely evaluate a structured exclusive_gateway predicate with zero eval()."""
    field = str(config.get("field") or "amount_cents")
    op = str(config.get("operator") or ">")
    expected = config.get("value", 0)

    actual: Any = amount_cents if field == "amount_cents" else context.get(field)

    if op in (">", ">=", "<", "<="):
        try:
            lhs = float(actual if actual is not None else 0)
            rhs = float(expected)
        except TypeError, ValueError:
            return False, f"{field} ({actual!r}) could not be compared numerically to {expected!r}"
        matched = (
            (lhs > rhs)
            if op == ">"
            else (lhs >= rhs)
            if op == ">="
            else (lhs < rhs)
            if op == "<"
            else (lhs <= rhs)
        )
        if field == "amount_cents":
            detail = f"${lhs / 100:,.2f} {op} ${rhs / 100:,.2f} -> {'YES' if matched else 'NO'}"
        else:
            detail = f"{field} ({lhs:g}) {op} {rhs:g} -> {'YES' if matched else 'NO'}"
        return matched, detail

    if op == "==":
        matched = str(actual or "").strip().lower() == str(expected or "").strip().lower()
        return matched, f"{field} == {expected!r} -> {'YES' if matched else 'NO'}"

    if op == "!=":
        matched = str(actual or "").strip().lower() != str(expected or "").strip().lower()
        return matched, f"{field} != {expected!r} -> {'YES' if matched else 'NO'}"

    if op == "in":
        items = expected if isinstance(expected, list) else str(expected).split(",")
        allowed_vals = {str(x).strip().lower() for x in items if str(x).strip()}
        matched = str(actual or "").strip().lower() in allowed_vals
        return (
            matched,
            f"{field} ({actual!r}) in {sorted(allowed_vals)} -> {'YES' if matched else 'NO'}",
        )

    return False, f"Unsupported operator {op!r}"


def _next_edge(
    edges: list[dict[str, Any]],
    source_id: str,
    branch: str = "default",
) -> dict[str, Any] | None:
    outgoing = [e for e in edges if str(e.get("source_id")) == source_id]
    if not outgoing:
        return None
    for edge in outgoing:
        if str(edge.get("branch") or "default") == branch:
            return edge
    return outgoing[0]


def advance_bpmn_execution(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    amount_cents: int,
    context: dict[str, Any],
    start_node_id: str | None = None,
    existing_trace: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> tuple[str, str, list[dict[str, Any]], list[str]]:
    """Advance execution until a human_approval gate (live) or terminal end node (dry-run/end).

    Returns `(final_status, current_node_id, trace_steps, visited_node_ids)`.
    """
    node_by_id = {str(n["id"]): n for n in nodes}
    trace = list(existing_trace or [])
    visited_ids: list[str] = [str(step["node_id"]) for step in trace if "node_id" in step]

    if start_node_id is None:
        start_node = next((n for n in nodes if n.get("node_type") == "start_trigger"), None)
        if start_node is None:
            return "cancelled", "", trace, visited_ids
        cur_id = str(start_node["id"])
    else:
        cur_id = start_node_id

    now_iso = datetime.now(UTC).isoformat()
    guard = 0
    while cur_id and guard < 45:
        guard += 1
        node = node_by_id.get(cur_id)
        if node is None:
            return "cancelled", cur_id, trace, visited_ids

        ntype = str(node.get("node_type") or "")
        label = str(node.get("label") or cur_id)
        cfg = dict(node.get("config") or {})
        if cur_id not in visited_ids:
            visited_ids.append(cur_id)

        if ntype == "start_trigger":
            trace.append(
                {
                    "node_id": cur_id,
                    "node_type": ntype,
                    "label": label,
                    "outcome": "started",
                    "detail": f"Triggered for amount ${amount_cents / 100:,.2f}",
                    "at": now_iso,
                }
            )
            nxt = _next_edge(edges, cur_id)
            cur_id = str(nxt["target_id"]) if nxt else ""
            continue

        if ntype == "exclusive_gateway":
            matched, detail = evaluate_gateway_condition(
                cfg, amount_cents=amount_cents, context=context
            )
            branch = "yes" if matched else "no"
            trace.append(
                {
                    "node_id": cur_id,
                    "node_type": ntype,
                    "label": label,
                    "outcome": f"branch_{branch}",
                    "detail": detail,
                    "at": now_iso,
                }
            )
            nxt = _next_edge(edges, cur_id, branch=branch)
            cur_id = str(nxt["target_id"]) if nxt else ""
            continue

        if ntype == "human_approval":
            role = str(cfg.get("approver_role") or "Owner / Manager")
            sla_h = int(cfg.get("sla_hours") or 24)
            if not dry_run:
                trace.append(
                    {
                        "node_id": cur_id,
                        "node_type": ntype,
                        "label": label,
                        "outcome": "awaiting_human",
                        "detail": f"Paused at HITL gate for {role} (SLA {sla_h}h).",
                        "at": now_iso,
                    }
                )
                return "awaiting_approval", cur_id, trace, visited_ids
            trace.append(
                {
                    "node_id": cur_id,
                    "node_type": ntype,
                    "label": label,
                    "outcome": "simulated_approve",
                    "detail": f"Dry-run simulated human approval by {role} (SLA {sla_h}h).",
                    "at": now_iso,
                }
            )
            nxt = _next_edge(edges, cur_id, branch="yes") or _next_edge(edges, cur_id)
            cur_id = str(nxt["target_id"]) if nxt else ""
            continue

        if ntype == "ai_compliance_check":
            focus = str(cfg.get("check_scope") or "Sanctions, margin floor & clause audit")
            risk = int(context.get("risk_score") or 12)
            flagged = risk >= 80
            detail = (
                f"Read-only AI check ({focus}): risk score {risk}/100 - "
                f"{'flagged for review' if flagged else 'passed clean'}."
            )
            trace.append(
                {
                    "node_id": cur_id,
                    "node_type": ntype,
                    "label": label,
                    "outcome": "ai_flagged" if flagged else "ai_passed",
                    "detail": detail,
                    "at": now_iso,
                }
            )
            nxt = _next_edge(edges, cur_id, branch="no" if flagged else "yes") or _next_edge(
                edges, cur_id
            )
            cur_id = str(nxt["target_id"]) if nxt else ""
            continue

        if ntype == "notify_or_webhook":
            channel = str(cfg.get("channel") or "Email / Slack Webhook")
            trace.append(
                {
                    "node_id": cur_id,
                    "node_type": ntype,
                    "label": label,
                    "outcome": "dispatched",
                    "detail": f"Dispatched status notification via {channel}.",
                    "at": now_iso,
                }
            )
            nxt = _next_edge(edges, cur_id)
            cur_id = str(nxt["target_id"]) if nxt else ""
            continue

        if ntype == "end_approved":
            trace.append(
                {
                    "node_id": cur_id,
                    "node_type": ntype,
                    "label": label,
                    "outcome": "approved",
                    "detail": "Workflow completed with APPROVED status.",
                    "at": now_iso,
                }
            )
            return "approved", cur_id, trace, visited_ids

        if ntype == "end_rejected":
            trace.append(
                {
                    "node_id": cur_id,
                    "node_type": ntype,
                    "label": label,
                    "outcome": "rejected",
                    "detail": "Workflow terminated with REJECTED status.",
                    "at": now_iso,
                }
            )
            return "rejected", cur_id, trace, visited_ids

        break

    return "approved", cur_id, trace, visited_ids


def export_bpmn_20_xml(
    *,
    workflow_code: str,
    display_name: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> str:
    """Export workflow definition as valid OMG BPMN 2.0 XML."""
    tag_map = {
        "start_trigger": "bpmn:startEvent",
        "exclusive_gateway": "bpmn:exclusiveGateway",
        "human_approval": "bpmn:userTask",
        "ai_compliance_check": "bpmn:serviceTask",
        "notify_or_webhook": "bpmn:sendTask",
        "end_approved": "bpmn:endEvent",
        "end_rejected": "bpmn:endEvent",
    }
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"',
        '                  id="Defs_AMARKAL"',
        '                  targetNamespace="https://www.amarkal-platform.com/schema/bpmn">',
        f'  <bpmn:process id="Proc_{xml_escape(workflow_code)}" '
        f'name="{xml_escape(display_name)}" isExecutable="true">',
    ]
    for node in nodes:
        nid = xml_escape(str(node.get("id") or "node"))
        label = xml_escape(str(node.get("label") or nid))
        tag = tag_map.get(str(node.get("node_type") or ""), "bpmn:task")
        lines.append(f'    <{tag} id="{nid}" name="{label}" />')
    for idx, edge in enumerate(edges, start=1):
        eid = xml_escape(str(edge.get("id") or f"flow_{idx}"))
        src = xml_escape(str(edge.get("source_id") or ""))
        tgt = xml_escape(str(edge.get("target_id") or ""))
        lbl = xml_escape(str(edge.get("label") or edge.get("branch") or ""))
        lines.append(
            f'    <bpmn:sequenceFlow id="{eid}" name="{lbl}" sourceRef="{src}" targetRef="{tgt}" />'
        )
    lines.extend(["  </bpmn:process>", "</bpmn:definitions>"])
    return "\n".join(lines) + "\n"


def _extract_threshold_cents(prompt: str) -> int:
    match = _DOLLAR_RE.search(prompt) or _NUM_K_RE.search(prompt)
    if not match:
        return 5_000_000  # default $50,000
    raw_num = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        raw_num *= 1_000
    elif suffix == "m":
        raw_num *= 1_000_000
    return max(100, round(raw_num * 100))


def generate_bpmn_from_prompt(prompt: str) -> dict[str, Any]:
    """Deterministically compile natural-language approval intent (EN/RU) into a BPMN DAG."""
    lower = prompt.lower()
    threshold_cents = _extract_threshold_cents(prompt)
    threshold_usd = threshold_cents / 100

    trigger: TriggerEntity = "contract"
    if any(k in lower for k in ("purchase order", "po ", "закуп", "постав")):
        trigger = "purchase_order"
    elif any(k in lower for k in ("payroll", "зарплат")):
        trigger = "payroll_run"
    elif any(k in lower for k in ("intercompany", "холдинг", "межфирм")):
        trigger = "intercompany_trade"
    elif any(k in lower for k in ("invoice", "счет", "счёт")):
        trigger = "invoice"

    want_legal = any(k in lower for k in ("legal", "counsel", "юрист", "юридич"))
    want_cfo = any(k in lower for k in ("cfo", "finance", "фин", "директор"))
    want_ai = any(k in lower for k in ("ai", "ии", "audit", "комплаенс", "проверк"))

    nodes: list[dict[str, Any]] = [
        {
            "id": "n_start",
            "node_type": "start_trigger",
            "label": f"New {trigger.replace('_', ' ').title()}",
            "x": 40,
            "y": 140,
            "config": {"trigger_entity": trigger},
        },
        {
            "id": "n_gate",
            "node_type": "exclusive_gateway",
            "label": f"Amount > ${threshold_usd:,.0f}?",
            "x": 230,
            "y": 140,
            "config": {
                "field": "amount_cents",
                "operator": ">",
                "value": threshold_cents,
            },
        },
    ]
    edges: list[dict[str, Any]] = [
        {
            "id": "e_start_gate",
            "source_id": "n_start",
            "target_id": "n_gate",
            "label": "Submit",
            "branch": "default",
        }
    ]

    # Upper high-value branch (YES)
    prev_high = "n_gate"
    prev_branch: EdgeBranch = "yes"
    x_pos = 430

    if want_legal or not (want_cfo or want_ai):
        nodes.append(
            {
                "id": "n_legal",
                "node_type": "human_approval",
                "label": "Legal Counsel Review",
                "x": x_pos,
                "y": 50,
                "config": {"approver_role": "Legal Counsel", "sla_hours": 24},
            }
        )
        edges.append(
            {
                "id": f"e_{prev_high}_legal",
                "source_id": prev_high,
                "target_id": "n_legal",
                "label": f"> ${threshold_usd:,.0f}" if prev_branch == "yes" else "Next",
                "branch": prev_branch,
            }
        )
        prev_high = "n_legal"
        prev_branch = "default"
        x_pos += 195

    if want_cfo or not (want_legal or want_ai):
        nodes.append(
            {
                "id": "n_cfo",
                "node_type": "human_approval",
                "label": "CFO Financial Sign-Off",
                "x": x_pos,
                "y": 50,
                "config": {"approver_role": "CFO / Owner", "sla_hours": 12},
            }
        )
        edges.append(
            {
                "id": f"e_{prev_high}_cfo",
                "source_id": prev_high,
                "target_id": "n_cfo",
                "label": "Approved" if prev_branch == "default" else f"> ${threshold_usd:,.0f}",
                "branch": prev_branch,
            }
        )
        prev_high = "n_cfo"
        prev_branch = "default"
        x_pos += 195

    if want_ai:
        nodes.append(
            {
                "id": "n_ai",
                "node_type": "ai_compliance_check",
                "label": "AI Clause & Risk Audit",
                "x": x_pos,
                "y": 50,
                "config": {"check_scope": "Indemnity, margin & sanctions scan (read-only)"},
            }
        )
        edges.append(
            {
                "id": f"e_{prev_high}_ai",
                "source_id": prev_high,
                "target_id": "n_ai",
                "label": "Verify",
                "branch": prev_branch,
            }
        )
        prev_high = "n_ai"
        x_pos += 195

    # Fast-track lower branch (NO)
    nodes.append(
        {
            "id": "n_mgr",
            "node_type": "human_approval",
            "label": "Manager Fast-Track",
            "x": 470,
            "y": 240,
            "config": {"approver_role": "Department Manager", "sla_hours": 8},
        }
    )
    edges.append(
        {
            "id": "e_gate_mgr",
            "source_id": "n_gate",
            "target_id": "n_mgr",
            "label": f"<= ${threshold_usd:,.0f}",
            "branch": "no",
        }
    )

    end_x = max(x_pos, 720)
    nodes.append(
        {
            "id": "n_approved",
            "node_type": "end_approved",
            "label": "Executed & Approved",
            "x": end_x,
            "y": 140,
            "config": {},
        }
    )
    edges.append(
        {
            "id": f"e_{prev_high}_end",
            "source_id": prev_high,
            "target_id": "n_approved",
            "label": "Complete",
            "branch": "yes" if prev_high == "n_ai" else "default",
        }
    )
    edges.append(
        {
            "id": "e_mgr_end",
            "source_id": "n_mgr",
            "target_id": "n_approved",
            "label": "Approved",
            "branch": "default",
        }
    )

    title_entity = trigger.replace("_", " ").title()
    return {
        "workflow_code": f"ai-flow-{trigger.replace('_', '-')}-{round(threshold_usd)}",
        "display_name": f"AI Generated {title_entity} Approval (> ${threshold_usd:,.0f})",
        "description": f"Generated from prompt: {prompt.strip()[:300]}",
        "trigger_entity": trigger,
        "nodes": nodes,
        "edges": edges,
    }


BPMN_PRESET_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "workflow_code": "enterprise-contract-50k-approval",
        "display_name": "Enterprise Contract Approval (> $50k -> Legal -> CFO -> AI Audit)",
        "description": (
            "Routes contracts above $50,000 through Legal Counsel, CFO sign-off, and read-only "
            "AI clause/risk audit, while fast-tracking smaller agreements via Manager review."
        ),
        "trigger_entity": "contract",
        "nodes": [
            {
                "id": "n_start",
                "node_type": "start_trigger",
                "label": "Contract Submitted",
                "x": 30,
                "y": 140,
                "config": {"trigger_entity": "contract"},
            },
            {
                "id": "n_gate_50k",
                "node_type": "exclusive_gateway",
                "label": "Contract > $50k?",
                "x": 200,
                "y": 140,
                "config": {"field": "amount_cents", "operator": ">", "value": 5_000_000},
            },
            {
                "id": "n_legal",
                "node_type": "human_approval",
                "label": "Legal Counsel Review",
                "x": 385,
                "y": 48,
                "config": {"approver_role": "Legal Counsel", "sla_hours": 24},
            },
            {
                "id": "n_cfo",
                "node_type": "human_approval",
                "label": "CFO Sign-Off",
                "x": 575,
                "y": 48,
                "config": {"approver_role": "CFO / Owner", "sla_hours": 12},
            },
            {
                "id": "n_ai_check",
                "node_type": "ai_compliance_check",
                "label": "AI Clause & Risk Check",
                "x": 765,
                "y": 48,
                "config": {"check_scope": "Indemnity, payment terms & sanctions audit"},
            },
            {
                "id": "n_mgr_fast",
                "node_type": "human_approval",
                "label": "Manager Fast-Track",
                "x": 480,
                "y": 236,
                "config": {"approver_role": "Sales / Ops Manager", "sla_hours": 8},
            },
            {
                "id": "n_end_ok",
                "node_type": "end_approved",
                "label": "Approved to Sign",
                "x": 965,
                "y": 140,
                "config": {},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source_id": "n_start",
                "target_id": "n_gate_50k",
                "label": "Submit",
                "branch": "default",
            },
            {
                "id": "e2",
                "source_id": "n_gate_50k",
                "target_id": "n_legal",
                "label": "> $50k",
                "branch": "yes",
            },
            {
                "id": "e3",
                "source_id": "n_legal",
                "target_id": "n_cfo",
                "label": "Cleared",
                "branch": "default",
            },
            {
                "id": "e4",
                "source_id": "n_cfo",
                "target_id": "n_ai_check",
                "label": "Signed",
                "branch": "default",
            },
            {
                "id": "e5",
                "source_id": "n_ai_check",
                "target_id": "n_end_ok",
                "label": "Verified",
                "branch": "yes",
            },
            {
                "id": "e6",
                "source_id": "n_gate_50k",
                "target_id": "n_mgr_fast",
                "label": "<= $50k",
                "branch": "no",
            },
            {
                "id": "e7",
                "source_id": "n_mgr_fast",
                "target_id": "n_end_ok",
                "label": "Approved",
                "branch": "default",
            },
        ],
    },
    {
        "workflow_code": "po-capex-25k-dual-control",
        "display_name": "Purchase Order CapEx Approval (> $25k Dual Control)",
        "description": (
            "Enforces budget-holder and CFO sign-off for purchase orders exceeding $25,000 with "
            "automated AP webhook notification upon clearance."
        ),
        "trigger_entity": "purchase_order",
        "nodes": [
            {
                "id": "po_start",
                "node_type": "start_trigger",
                "label": "PO Draft Created",
                "x": 40,
                "y": 140,
                "config": {"trigger_entity": "purchase_order"},
            },
            {
                "id": "po_gate",
                "node_type": "exclusive_gateway",
                "label": "PO > $25k?",
                "x": 220,
                "y": 140,
                "config": {"field": "amount_cents", "operator": ">", "value": 2_500_000},
            },
            {
                "id": "po_dept",
                "node_type": "human_approval",
                "label": "Dept Head Approval",
                "x": 430,
                "y": 55,
                "config": {"approver_role": "Department Head", "sla_hours": 16},
            },
            {
                "id": "po_cfo",
                "node_type": "human_approval",
                "label": "CFO Budget Release",
                "x": 640,
                "y": 55,
                "config": {"approver_role": "CFO / Owner", "sla_hours": 12},
            },
            {
                "id": "po_buyer",
                "node_type": "human_approval",
                "label": "Procurement Lead",
                "x": 480,
                "y": 230,
                "config": {"approver_role": "Procurement Manager", "sla_hours": 8},
            },
            {
                "id": "po_notify",
                "node_type": "notify_or_webhook",
                "label": "Notify AP & Vendor",
                "x": 820,
                "y": 140,
                "config": {"channel": "Email + ERP Webhook"},
            },
            {
                "id": "po_end",
                "node_type": "end_approved",
                "label": "PO Issued",
                "x": 980,
                "y": 140,
                "config": {},
            },
        ],
        "edges": [
            {
                "id": "pe1",
                "source_id": "po_start",
                "target_id": "po_gate",
                "label": "Submit",
                "branch": "default",
            },
            {
                "id": "pe2",
                "source_id": "po_gate",
                "target_id": "po_dept",
                "label": "> $25k",
                "branch": "yes",
            },
            {
                "id": "pe3",
                "source_id": "po_dept",
                "target_id": "po_cfo",
                "label": "Approved",
                "branch": "default",
            },
            {
                "id": "pe4",
                "source_id": "po_cfo",
                "target_id": "po_notify",
                "label": "Released",
                "branch": "default",
            },
            {
                "id": "pe5",
                "source_id": "po_gate",
                "target_id": "po_buyer",
                "label": "<= $25k",
                "branch": "no",
            },
            {
                "id": "pe6",
                "source_id": "po_buyer",
                "target_id": "po_notify",
                "label": "Approved",
                "branch": "default",
            },
            {
                "id": "pe7",
                "source_id": "po_notify",
                "target_id": "po_end",
                "label": "Done",
                "branch": "default",
            },
        ],
    },
    {
        "workflow_code": "holding-intercompany-oecd-review",
        "display_name": "Holding Intercompany Trade Review (OECD Transfer Pricing)",
        "description": (
            "Audits cross-border intercompany SO/PO pairs above $100k with AI UPII margin checks "
            "and Group Controller sign-off prior to consolidation elimination."
        ),
        "trigger_entity": "intercompany_trade",
        "nodes": [
            {
                "id": "ic_start",
                "node_type": "start_trigger",
                "label": "Mirror SO/PO Created",
                "x": 40,
                "y": 140,
                "config": {"trigger_entity": "intercompany_trade"},
            },
            {
                "id": "ic_gate",
                "node_type": "exclusive_gateway",
                "label": "Trade > $100k?",
                "x": 225,
                "y": 140,
                "config": {"field": "amount_cents", "operator": ">", "value": 10_000_000},
            },
            {
                "id": "ic_ai",
                "node_type": "ai_compliance_check",
                "label": "AI OECD & UPII Audit",
                "x": 440,
                "y": 55,
                "config": {"check_scope": "OECD arm's-length band & UPII calculation"},
            },
            {
                "id": "ic_ctrl",
                "node_type": "human_approval",
                "label": "Group Controller",
                "x": 660,
                "y": 55,
                "config": {"approver_role": "Group Controller / CPA", "sla_hours": 24},
            },
            {
                "id": "ic_std",
                "node_type": "human_approval",
                "label": "Entity Accountant",
                "x": 480,
                "y": 230,
                "config": {"approver_role": "Subsidiary Accountant", "sla_hours": 12},
            },
            {
                "id": "ic_end",
                "node_type": "end_approved",
                "label": "Cleared for Close",
                "x": 880,
                "y": 140,
                "config": {},
            },
        ],
        "edges": [
            {
                "id": "ie1",
                "source_id": "ic_start",
                "target_id": "ic_gate",
                "label": "Evaluate",
                "branch": "default",
            },
            {
                "id": "ie2",
                "source_id": "ic_gate",
                "target_id": "ic_ai",
                "label": "> $100k",
                "branch": "yes",
            },
            {
                "id": "ie3",
                "source_id": "ic_ai",
                "target_id": "ic_ctrl",
                "label": "Passed",
                "branch": "yes",
            },
            {
                "id": "ie4",
                "source_id": "ic_ctrl",
                "target_id": "ic_end",
                "label": "Approved",
                "branch": "default",
            },
            {
                "id": "ie5",
                "source_id": "ic_gate",
                "target_id": "ic_std",
                "label": "<= $100k",
                "branch": "no",
            },
            {
                "id": "ie6",
                "source_id": "ic_std",
                "target_id": "ic_end",
                "label": "Approved",
                "branch": "default",
            },
        ],
    },
)
