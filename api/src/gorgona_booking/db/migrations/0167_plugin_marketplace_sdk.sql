-- 0167_plugin_marketplace_sdk.sql
-- AMARKAL v2.28.0: Plugin Marketplace (1-Click Scoped Extensions) & Developer SDK
-- (amarkal-plugin.json Manifest Validator & Private/Public Submission Registry).
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, zero SECURITY DEFINER.

CREATE TABLE gba.marketplace_plugin_installations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    plugin_slug text NOT NULL CHECK (plugin_slug ~ '^[a-z0-9][a-z0-9_-]{2,62}$'),
    plugin_version text NOT NULL DEFAULT '1.0.0' CHECK (
        char_length(plugin_version) BETWEEN 3 AND 32
    ),
    display_name text NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 2 AND 120),
    publisher_name text NOT NULL DEFAULT 'AMARKAL Verified' CHECK (
        char_length(btrim(publisher_name)) BETWEEN 2 AND 120
    ),
    category text NOT NULL DEFAULT 'General' CHECK (char_length(category) BETWEEN 2 AND 64),
    protocol text NOT NULL DEFAULT 'https_api' CHECK (
        protocol IN ('https_api', 'mcp_remote', 'webhook_bridge', 'oauth2_custom')
    ),
    endpoint_url text NOT NULL DEFAULT '' CHECK (
        endpoint_url = ''
        OR (char_length(endpoint_url) BETWEEN 12 AND 500 AND endpoint_url LIKE 'https://%')
    ),
    granted_scopes text[] NOT NULL DEFAULT '{}'::text[],
    subscribed_events text[] NOT NULL DEFAULT '{}'::text[],
    config_public jsonb NOT NULL DEFAULT '{}'::jsonb,
    custom_plugin_id uuid REFERENCES gba.custom_plugins(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'installed' CHECK (
        status IN ('installed', 'paused', 'uninstalled')
    ),
    installed_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    installed_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, plugin_slug)
);

CREATE INDEX marketplace_installations_tenant_status_idx
    ON gba.marketplace_plugin_installations (tenant_id, status, updated_at DESC);

CREATE TABLE gba.marketplace_developer_submissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    plugin_slug text NOT NULL CHECK (plugin_slug ~ '^[a-z0-9][a-z0-9_-]{2,62}$'),
    version text NOT NULL CHECK (char_length(version) BETWEEN 3 AND 32),
    display_name text NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 2 AND 120),
    publisher_name text NOT NULL CHECK (char_length(btrim(publisher_name)) BETWEEN 2 AND 120),
    category text NOT NULL DEFAULT 'Custom Extension' CHECK (
        char_length(category) BETWEEN 2 AND 64
    ),
    protocol text NOT NULL DEFAULT 'https_api' CHECK (
        protocol IN ('https_api', 'mcp_remote', 'webhook_bridge', 'oauth2_custom')
    ),
    naics_codes text[] NOT NULL DEFAULT '{}'::text[],
    manifest_json jsonb NOT NULL,
    validation_status text NOT NULL DEFAULT 'published_private' CHECK (
        validation_status IN ('draft', 'validated', 'submitted_for_review', 'published_private')
    ),
    validation_warnings text[] NOT NULL DEFAULT '{}'::text[],
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, plugin_slug, version)
);

CREATE INDEX marketplace_submissions_tenant_created_idx
    ON gba.marketplace_developer_submissions (tenant_id, created_at DESC);

-- ── ENABLE + FORCE ROW LEVEL SECURITY ON BOTH TABLES ─────────────────────────

ALTER TABLE gba.marketplace_plugin_installations ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.marketplace_plugin_installations FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.marketplace_developer_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.marketplace_developer_submissions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS marketplace_installations_tenant_isolation
    ON gba.marketplace_plugin_installations;
CREATE POLICY marketplace_installations_tenant_isolation
    ON gba.marketplace_plugin_installations
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS marketplace_submissions_tenant_isolation
    ON gba.marketplace_developer_submissions;
CREATE POLICY marketplace_submissions_tenant_isolation
    ON gba.marketplace_developer_submissions
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.marketplace_plugin_installations TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.marketplace_developer_submissions TO gba_runtime;
