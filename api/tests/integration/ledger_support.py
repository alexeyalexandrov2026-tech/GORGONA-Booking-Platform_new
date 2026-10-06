"""TEST ONLY readiness promotion to exercise finance before exact-SHA CI acceptance."""

import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness


def allow_finance_in_test(monkeypatch: pytest.MonkeyPatch) -> None:
    promoted = tuple(
        m.model_copy(update={"readiness": Readiness.TECHNICALLY_VERIFIED, "enableable": True})
        if m.id == "finance"
        else m
        for m in modules.MODULES
    )
    monkeypatch.setattr(modules, "MODULES", promoted)
    monkeypatch.setattr(modules, "MODULES_BY_ID", {m.id: m for m in promoted})
    monkeypatch.setattr(modules, "MODULE_CATALOG", modules.ModuleCatalog(modules=promoted))
