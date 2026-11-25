-- 0153_connectors_app_hub.sql
-- GORGONA App Hub: tenant-isolated Scoped API Keys, Signed Outbound Webhooks,
-- and Connector Installations (invoker-only, FORCE RLS, zero SECURITY DEFINER).

CREATE TABLE gba.api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    name text NOT NULL CHECK (char_length(name) BETWEEN 2 AND 120),
    key_prefix text NOT NULL CHECK (char_length(key_prefix) BETWEEN 8 AND 24),
    key_hash text NOT NULL UNIQUE CHECK (char_length(key_hash) = 64),
    scopes text[] NOT NULL CHECK (cardinality(scopes) >= 1),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    last_used_at timestamptz,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

CREATE INDEX api_keys_tenant_status_idx
    ON gba.api_keys (tenant_id, status, created_at DESC);

CREATE TABLE gba.webhook_endpoints (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    url text NOT NULL CHECK (char_length(url) BETWEEN 12 AND 500 AND url LIKE 'https://%'),
    description text NOT NULL DEFAULT '' CHECK (char_length(description) <= 240),
    events text[] NOT NULL CHECK (cardinality(events) >= 1),
    signing_secret_prefix text NOT NULL CHECK (char_length(signing_secret_prefix) BETWEEN 6 AND 20),
    signing_secret_hash text NOT NULL CHECK (char_length(signing_secret_hash) = 64),
    is_active boolean NOT NULL DEFAULT true,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE INDEX webhook_endpoints_tenant_active_idx
    ON gba.webhook_endpoints (tenant_id, is_active, created_at DESC);

CREATE TABLE gba.webhook_deliveries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    endpoint_id uuid NOT NULL,
    event_type text NOT NULL CHECK (char_length(event_type) BETWEEN 3 AND 100),
    payload jsonb NOT NULL,
    signature_header text NOT NULL CHECK (char_length(signature_header) BETWEEN 16 AND 128),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'delivered', 'failed')),
    http_status integer,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz,
    FOREIGN KEY (tenant_id, endpoint_id)
        REFERENCES gba.webhook_endpoints(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX webhook_deliveries_tenant_endpoint_idx
    ON gba.webhook_deliveries (tenant_id, endpoint_id, created_at DESC);

CREATE TABLE gba.connector_installations (
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    connector_id text NOT NULL CHECK (connector_id ~ '^[a-z0-9_]{2,64}$'),
    display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 2 AND 120),
    category text NOT NULL CHECK (char_length(category) BETWEEN 2 AND 64),
    status text NOT NULL DEFAULT 'installed' CHECK (status IN ('installed', 'paused')),
    config_masked jsonb NOT NULL DEFAULT '{}'::jsonb,
    config_hash text NOT NULL CHECK (char_length(config_hash) = 64),
    installed_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, connector_id)
);

ALTER TABLE gba.api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.api_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.webhook_endpoints FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.webhook_deliveries FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.connector_installations ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.connector_installations FORCE ROW LEVEL SECURITY;

-- api_keys allows tenant-scoped management OR exact SHA-256 bearer lookup for /v1/mcp
DROP POLICY IF EXISTS api_keys_tenant_isolation ON gba.api_keys;
CREATE POLICY api_keys_tenant_isolation ON gba.api_keys
    FOR ALL
    TO gba_runtime
    USING (
        tenant_id = gba.current_tenant_id()
        OR key_hash = nullif(pg_catalog.current_setting('gba.api_key_hash', true), '')
    )
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS webhook_endpoints_tenant_isolation ON gba.webhook_endpoints;
CREATE POLICY webhook_endpoints_tenant_isolation ON gba.webhook_endpoints
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS webhook_deliveries_tenant_isolation ON gba.webhook_deliveries;
CREATE POLICY webhook_deliveries_tenant_isolation ON gba.webhook_deliveries
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS connector_installations_tenant_isolation ON gba.connector_installations;
CREATE POLICY connector_installations_tenant_isolation ON gba.connector_installations
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.api_keys TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.webhook_endpoints TO gba_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE gba.webhook_deliveries TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.connector_installations TO gba_runtime;
