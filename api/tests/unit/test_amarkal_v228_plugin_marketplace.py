"""Unit tests for AMARKAL v2.28.0 Plugin Marketplace & Developer SDK manifest validator."""

from __future__ import annotations

from gorgona_booking.api.plugin_marketplace import (
    CURATED_MARKETPLACE_PLUGINS,
    SDK_MANIFEST_TEMPLATE,
    validate_plugin_manifest,
)


def test_sdk_manifest_template_and_curated_catalog_are_valid() -> None:
    ok, errors, _warnings, norm = validate_plugin_manifest(SDK_MANIFEST_TEMPLATE)
    assert ok is True
    assert errors == []
    assert norm is not None
    assert norm["slug"] == "my-customs-terminal-bridge"
    assert len(CURATED_MARKETPLACE_PLUGINS) == 12
    assert len({p["slug"] for p in CURATED_MARKETPLACE_PLUGINS}) == 12


def test_validate_plugin_manifest_blocks_ssrf_and_invalid_scopes() -> None:
    bad = {
        "schema_version": "1.0",
        "slug": "ssrf-bad-plugin",
        "version": "1.0.0",
        "display_name": "Bad SSRF Plugin",
        "publisher_name": "Test Dev",
        "category": "Custom",
        "protocol": "https_api",
        "endpoint_url": "https://169.254.169.254/latest/meta-data",
        "scopes": ["read:invoices", "admin:drop_database"],
        "events": ["invoice.issued", "system.root_shell"],
    }
    ok, errors, _warnings, norm = validate_plugin_manifest(bad)
    assert ok is False
    assert norm is None
    joined = " | ".join(errors)
    assert "private, loopback, or link-local" in joined
    assert "admin:drop_database" in joined
    assert "system.root_shell" in joined


def test_validate_plugin_manifest_blocks_http_and_localhost() -> None:
    bad_http = dict(SDK_MANIFEST_TEMPLATE, endpoint_url="http://api.example.com/v1")
    ok1, errs1, _, _ = validate_plugin_manifest(bad_http)
    assert ok1 is False
    assert any("https://" in e for e in errs1)

    bad_local = dict(SDK_MANIFEST_TEMPLATE, endpoint_url="https://service.internal/v1")
    ok2, errs2, _, _ = validate_plugin_manifest(bad_local)
    assert ok2 is False
    assert any("internal" in e for e in errs2)
