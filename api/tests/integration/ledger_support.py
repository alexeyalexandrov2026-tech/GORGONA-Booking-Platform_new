"""TEST ONLY removal of technical acceptance to verify the publication gate."""

import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness


def mark_finance_implemented_in_test(monkeypatch: pytest.MonkeyPatch) -> None:
    withheld = tuple(
        m.model_copy(update={"readiness": Readiness.IMPLEMENTED, "enableable": False})
        if m.id == "finance"
        else m
        for m in modules.MODULES
    )
    monkeypatch.setattr(modules, "MODULES", withheld)
    monkeypatch.setattr(modules, "MODULES_BY_ID", {m.id: m for m in withheld})
    monkeypatch.setattr(modules, "MODULE_CATALOG", modules.ModuleCatalog(modules=withheld))
