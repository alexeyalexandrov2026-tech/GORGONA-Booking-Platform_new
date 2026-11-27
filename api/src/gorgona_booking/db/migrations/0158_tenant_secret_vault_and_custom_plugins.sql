-- 0158_tenant_secret_vault_and_custom_plugins.sql
-- AMARKAL v2.14.0: Per-tenant AES-256-GCM Encrypted Secret Vault (BYOK AI keys, OAuth2 tokens,
-- Custom Plugin credentials) and Open Custom Plugin Manifests.
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY on every table.

CREATE TABLE gba.tenant_connector_secrets (
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    connector_id text NOT NULL CHECK (connector_id ~ '^[a-z0-9_-]{2,80}$'),
    secret_kind text NOT NULL CHECK (
        secret_kind IN ('byok_ai_key', 'oauth_tokens', 'plugin_credential')
    ),
    key_version text NOT NULL DEFAULT 'v1' CHECK (char_length(key_version) BETWEEN 1 AND 32),
    nonce_b64 text NOT NULL CHECK (char_length(nonce_b64) BETWEEN 12 AND 64),
    ciphertext_b64 text NOT NULL CHECK (char_length(ciphertext_b64) BETWEEN 16 AND 16384),
    key_hint text NOT NULL CHECK (char_length(key_hint) BETWEEN 3 AND 32),
    metadata_public jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, connector_id, secret_kind)
);

CREATE INDEX tenant_connector_secrets_tenant_kind_idx
    ON gba.tenant_connector_secrets (tenant_id, secret_kind, updated_at DESC);

CREATE TABLE gba.custom_plugins (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    slug text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{1,62}$'),
    display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 2 AND 120),
    category text NOT NULL DEFAULT 'Custom Integration' CHECK (char_length(category) BETWEEN 2 AND 64),
    protocol text NOT NULL CHECK (
        protocol IN ('https_api', 'mcp_remote', 'webhook_bridge', 'oauth2_custom')
    ),
    endpoint_url text NOT NULL CHECK (
        char_length(endpoint_url) BETWEEN 12 AND 500 AND endpoint_url LIKE 'https://%'
    ),
    auth_header_name text NOT NULL DEFAULT 'Authorization' CHECK (
        char_length(auth_header_name) BETWEEN 2 AND 64
    ),
    auth_scheme text NOT NULL DEFAULT 'Bearer' CHECK (
        auth_scheme IN ('Bearer', 'ApiKey', 'None')
    ),
    scopes text[] NOT NULL DEFAULT '{}'::text[],
    subscribed_events text[] NOT NULL DEFAULT '{}'::text[],
    description text NOT NULL DEFAULT '' CHECK (char_length(description) <= 400),
    has_secret boolean NOT NULL DEFAULT false,
    secret_hint text CHECK (secret_hint IS NULL OR char_length(secret_hint) BETWEEN 3 AND 32),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused')),
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, slug)
);

CREATE INDEX custom_plugins_tenant_status_idx
    ON gba.custom_plugins (tenant_id, status, created_at DESC);

ALTER TABLE gba.tenant_connector_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.tenant_connector_secrets FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.custom_plugins ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.custom_plugins FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_connector_secrets_tenant_isolation ON gba.tenant_connector_secrets;
CREATE POLICY tenant_connector_secrets_tenant_isolation ON gba.tenant_connector_secrets
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS custom_plugins_tenant_isolation ON gba.custom_plugins;
CREATE POLICY custom_plugins_tenant_isolation ON gba.custom_plugins
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.tenant_connector_secrets TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.custom_plugins TO gba_runtime;
