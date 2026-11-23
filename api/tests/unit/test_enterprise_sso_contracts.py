"""Unit contract tests for ENTERPRISE-01 Slice 1 (0143): analytics module, enterprise
permissions, SSO provider validation, and deprovisioning input validation.
"""

from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import DELEGABLE_PERMISSIONS, PERMISSIONS_VERSION, Permission
from gorgona_booking.business import modules
from gorgona_booking.business.enterprise_sso import (
    DeprovisionInput,
    DirectoryLinkInput,
    SsoProviderInput,
)
from gorgona_booking.business.readiness_registry import Readiness


def test_analytics_module_and_enterprise_permissions_registered_conservatively() -> None:
    assert modules.MODULE_REGISTRY_VERSION == 13
    mod = modules.MODULES_BY_ID["analytics"]
    assert mod.readiness == Readiness.IMPLEMENTED
    assert mod.enableable is False
    assert set(mod.depends_on) == {"organization"}
    assert PERMISSIONS_VERSION == 22
    for perm in (Permission.ENTERPRISE_READ, Permission.ENTERPRISE_MANAGE):
        assert perm not in DELEGABLE_PERMISSIONS


def test_sso_provider_and_lifecycle_contracts_validate_inputs() -> None:
    ok = SsoProviderInput(
        expected_revision=0,
        code="okta_corp",
        display_name="Okta Corporate SSO",
        protocol="oidc",
        issuer_url="https://corp.okta.com/oauth2/default",
        email_domain="ACME.COM",
    )
    assert ok.code == "OKTA_CORP"
    assert ok.email_domain == "acme.com"

    with pytest.raises(ValidationError):
        SsoProviderInput(
            expected_revision=0,
            code="OKTA",
            display_name="Bad Issuer",
            issuer_url="ftp://invalid.example.com",
            email_domain="acme.com",
        )
    with pytest.raises(ValidationError):
        DirectoryLinkInput(
            expected_revision=0,
            provider_id=uuid7(),
            user_id=uuid7(),
            external_subject="   ",
            employee_code="EMP-1",
        )
    with pytest.raises(ValidationError):
        DeprovisionInput(reason="   ")
