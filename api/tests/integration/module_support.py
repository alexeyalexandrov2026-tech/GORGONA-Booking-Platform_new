"""Test-only registry override; module configuration still uses real publication."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from gorgona_booking.api import configurations as api
from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness


@contextmanager
def verified_modules(*module_ids: str) -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        for module_id in module_ids:
            original = modules.MODULES_BY_ID[module_id]
            patch.setitem(
                modules.MODULES_BY_ID,
                module_id,
                original.model_copy(
                    update={
                        "readiness": Readiness.TECHNICALLY_VERIFIED,
                        "enableable": True,
                    }
                ),
            )
        catalog = modules.ModuleCatalog(
            modules=tuple(modules.MODULES_BY_ID[m.id] for m in modules.MODULES)
        )
        patch.setattr(api, "MODULE_CATALOG", catalog)
        yield
