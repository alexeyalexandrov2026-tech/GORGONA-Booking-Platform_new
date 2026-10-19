"""K4b (R-09): the provider runbook covers every state and refusal code the screen can show."""

import re
from pathlib import Path
from typing import get_args

from gorgona_booking.business import provider_payments, provider_review
from gorgona_booking.business.settlement_contracts import ProviderOperationState
from gorgona_booking.errors import ConflictError

RUNBOOK = Path(__file__).resolve().parents[3] / "docs/runbooks/PROVIDER_OPERATIONS.md"


def _codes() -> set[str]:
    return {
        value.code
        for module in (provider_payments, provider_review)
        for value in vars(module).values()
        if isinstance(value, type)
        and issubclass(value, ConflictError)
        and value.code.startswith("PROVIDER_")
    }


def test_the_runbook_names_every_operation_state() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for state in get_args(ProviderOperationState):
        assert f"| `{state}` |" in text, state


def test_the_runbook_explains_every_provider_refusal_code() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    codes = _codes()
    assert len(codes) == 10
    for code in codes:
        assert f"| `{code}` |" in text, code


def test_the_runbook_links_resolve() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)#\s]+)", text)
    assert links
    for link in links:
        assert (RUNBOOK.parent / link).exists(), link
