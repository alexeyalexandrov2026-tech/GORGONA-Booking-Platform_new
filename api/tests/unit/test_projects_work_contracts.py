"""PRO-01 Slice 2 unit contract tests (ADR-0038)."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.projects_work import (
    StageDecisionInput,
    StageInput,
    StageSubmitInput,
    TaskDependencyInput,
    TaskInput,
)


def test_stage_inputs_strict() -> None:
    s = StageInput(
        schema_version=1,
        expected_revision=0,
        stage_no=1,
        title="Discovery & Document Review",
        due_on=date(2026, 12, 15),
        fixed_fee_minor=150_000,
    )
    assert s.stage_no == 1

    sub = StageSubmitInput(
        schema_version=1,
        expected_revision=1,
        deliverable_summary="Completed discovery packet v1.",
    )
    assert sub.expected_revision == 1

    dec = StageDecisionInput(schema_version=1, expected_revision=2, decision="accept")
    assert dec.decision == "accept"

    with pytest.raises(ValidationError):
        StageInput(schema_version=1, expected_revision=0, stage_no=0, title="Bad no")

    with pytest.raises(ValidationError):
        StageInput(
            schema_version=1,
            expected_revision=0,
            stage_no=1,
            title="Bad fee",
            fixed_fee_minor=-1,
        )


def test_task_and_dependency_inputs_strict() -> None:
    t = TaskInput(
        schema_version=1,
        expected_revision=0,
        stage_id=uuid7(),
        title="Draft motion to dismiss",
        priority="high",
        status="in_progress",
    )
    assert t.priority == "high"

    dep = TaskDependencyInput(schema_version=1, depends_on_task_id=uuid7())
    assert dep.depends_on_task_id is not None

    with pytest.raises(ValidationError):
        TaskInput(schema_version=1, expected_revision=0, title="Line\nBreak")
