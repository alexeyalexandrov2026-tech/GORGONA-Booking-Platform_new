-- 0168_abac_matrix_access_control.sql
-- AMARKAL v2.31.0: Matrix RBAC / ABAC Policy Engine, Field-Level PII Masking,
-- Regional Scope Filtering & Time-Window Write Access Control.
-- Strictly additive restrictive overlay over ADR-0008 ROLE_PERMISSIONS (PERMISSIONS_VERSION = 25).
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, zero SECURITY DEFINER.

CREATE TABLE gba.abac_policies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    policy_code text NOT NULL CHECK (policy_code ~ '^[a-z0-9][a-z0-9_-]{2,62}$'),
    display_name text NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 2 AND 120),
    description text NOT NULL DEFAULT '' CHECK (char_length(description) <= 500),
    base_role text NOT NULL DEFAULT 'manager' CHECK (
        base_role IN ('artist', 'front_desk', 'manager', 'owner')
    ),
    is_active boolean NOT NULL DEFAULT true,
    denied_permissions text[] NOT NULL DEFAULT '{}'::text[],
    allowed_regions text[] NOT NULL DEFAULT '{}'::text[],
    masked_fields text[] NOT NULL DEFAULT '{}'::text[],
    write_window_enabled boolean NOT NULL DEFAULT false,
    write_window_timezone text NOT NULL DEFAULT 'America/Chicago' CHECK (
        char_length(btrim(write_window_timezone)) BETWEEN 3 AND 64
    ),
    write_window_start_minute integer NOT NULL DEFAULT 540 CHECK (
        write_window_start_minute BETWEEN 0 AND 1439
    ),
    write_window_end_minute integer NOT NULL DEFAULT 1080 CHECK (
        write_window_end_minute BETWEEN 1 AND 1440
    ),
    write_window_days integer[] NOT NULL DEFAULT '{1,2,3,4,5}'::integer[],
    write_window_permissions text[] NOT NULL DEFAULT '{}'::text[],
    max_financial_amount_cents bigint CHECK (
        max_financial_amount_cents IS NULL OR max_financial_amount_cents >= 0
    ),
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (write_window_end_minute > write_window_start_minute),
    UNIQUE (tenant_id, policy_code)
);

CREATE INDEX abac_policies_tenant_active_idx
    ON gba.abac_policies (tenant_id, is_active, updated_at DESC);

CREATE TABLE gba.abac_user_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    policy_id uuid NOT NULL REFERENCES gba.abac_policies(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES gba.users(id) ON DELETE CASCADE,
    assigned_regions_override text[] NOT NULL DEFAULT '{}'::text[],
    is_active boolean NOT NULL DEFAULT true,
    assigned_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, policy_id, user_id)
);

CREATE INDEX abac_user_assignments_tenant_user_idx
    ON gba.abac_user_assignments (tenant_id, user_id, is_active);

-- ── ENABLE + FORCE ROW LEVEL SECURITY ON BOTH TABLES ─────────────────────────

ALTER TABLE gba.abac_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.abac_policies FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.abac_user_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.abac_user_assignments FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS abac_policies_tenant_isolation ON gba.abac_policies;
CREATE POLICY abac_policies_tenant_isolation
    ON gba.abac_policies
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS abac_user_assignments_tenant_isolation ON gba.abac_user_assignments;
CREATE POLICY abac_user_assignments_tenant_isolation
    ON gba.abac_user_assignments
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.abac_policies TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.abac_user_assignments TO gba_runtime;
