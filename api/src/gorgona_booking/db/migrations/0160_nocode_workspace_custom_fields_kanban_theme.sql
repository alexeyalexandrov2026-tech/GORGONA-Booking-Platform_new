-- 0160_nocode_workspace_custom_fields_kanban_theme.sql
-- AMARKAL v2.16.0: No-Code Workspace Studio — Typed Custom Fields,
-- Drag-and-Drop Kanban Workflow Boards, and Tenant Brand Themes (WCAG AA).
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY on every table.

CREATE TABLE gba.custom_field_definitions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    entity_kind text NOT NULL CHECK (
        entity_kind IN (
            'counterparty',
            'commercial_quote',
            'purchase_order',
            'booking',
            'asset',
            'project_matter'
        )
    ),
    field_key text NOT NULL CHECK (field_key ~ '^[a-z][a-z0-9_]{1,47}$'),
    label text NOT NULL CHECK (char_length(label) BETWEEN 2 AND 80),
    field_type text NOT NULL CHECK (
        field_type IN ('text', 'number', 'currency_usd', 'date', 'select', 'boolean')
    ),
    options text[] NOT NULL DEFAULT '{}'::text[],
    is_required boolean NOT NULL DEFAULT false,
    display_order integer NOT NULL DEFAULT 0 CHECK (display_order BETWEEN 0 AND 1000),
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, entity_kind, field_key)
);

CREATE INDEX custom_field_definitions_tenant_entity_idx
    ON gba.custom_field_definitions (tenant_id, entity_kind, display_order ASC);

CREATE TABLE gba.custom_field_values (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    definition_id uuid NOT NULL REFERENCES gba.custom_field_definitions(id) ON DELETE CASCADE,
    entity_kind text NOT NULL CHECK (
        entity_kind IN (
            'counterparty',
            'commercial_quote',
            'purchase_order',
            'booking',
            'asset',
            'project_matter'
        )
    ),
    entity_id text NOT NULL CHECK (char_length(entity_id) BETWEEN 1 AND 120),
    value_json jsonb NOT NULL,
    updated_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, definition_id, entity_id)
);

CREATE INDEX custom_field_values_tenant_entity_idx
    ON gba.custom_field_values (tenant_id, entity_kind, entity_id);

CREATE TABLE gba.workspace_boards (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    slug text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{1,62}$'),
    title text NOT NULL CHECK (char_length(title) BETWEEN 2 AND 120),
    entity_kind text NOT NULL DEFAULT 'general' CHECK (
        entity_kind IN (
            'general',
            'counterparty',
            'commercial_quote',
            'purchase_order',
            'booking',
            'asset',
            'project_matter'
        )
    ),
    lanes jsonb NOT NULL,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, slug)
);

CREATE INDEX workspace_boards_tenant_created_idx
    ON gba.workspace_boards (tenant_id, created_at DESC);

CREATE TABLE gba.workspace_board_cards (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    board_id uuid NOT NULL REFERENCES gba.workspace_boards(id) ON DELETE CASCADE,
    lane_id text NOT NULL CHECK (char_length(lane_id) BETWEEN 1 AND 64),
    title text NOT NULL CHECK (char_length(title) BETWEEN 2 AND 180),
    description text NOT NULL DEFAULT '' CHECK (char_length(description) <= 1000),
    priority text NOT NULL DEFAULT 'medium' CHECK (
        priority IN ('low', 'medium', 'high', 'urgent')
    ),
    amount_cents bigint CHECK (
        amount_cents IS NULL OR amount_cents BETWEEN 0 AND 999999999
    ),
    due_date date,
    position integer NOT NULL DEFAULT 0 CHECK (position >= 0),
    custom_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX workspace_board_cards_tenant_board_idx
    ON gba.workspace_board_cards (tenant_id, board_id, lane_id, position ASC);

CREATE TABLE gba.tenant_brand_themes (
    tenant_id uuid PRIMARY KEY REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    brand_display_name text CHECK (
        brand_display_name IS NULL OR char_length(brand_display_name) <= 120
    ),
    logo_url text CHECK (
        logo_url IS NULL
        OR (char_length(logo_url) <= 500 AND logo_url LIKE 'https://%')
    ),
    accent_hex text NOT NULL DEFAULT '#111111' CHECK (accent_hex ~ '^#[0-9A-Fa-f]{6}$'),
    surface_preset text NOT NULL DEFAULT 'monolith_light' CHECK (
        surface_preset IN ('monolith_light', 'warm_stone', 'slate_enterprise')
    ),
    dashboard_widgets text[] NOT NULL DEFAULT ARRAY[
        'kpis', 'launchpad', 'unit_economics', 'copilot', 'smart_autonomy', 'schedule'
    ]::text[],
    updated_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE gba.custom_field_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.custom_field_definitions FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.custom_field_values ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.custom_field_values FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.workspace_boards ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.workspace_boards FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.workspace_board_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.workspace_board_cards FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.tenant_brand_themes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.tenant_brand_themes FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS custom_field_definitions_tenant_isolation ON gba.custom_field_definitions;
CREATE POLICY custom_field_definitions_tenant_isolation ON gba.custom_field_definitions
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS custom_field_values_tenant_isolation ON gba.custom_field_values;
CREATE POLICY custom_field_values_tenant_isolation ON gba.custom_field_values
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS workspace_boards_tenant_isolation ON gba.workspace_boards;
CREATE POLICY workspace_boards_tenant_isolation ON gba.workspace_boards
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS workspace_board_cards_tenant_isolation ON gba.workspace_board_cards;
CREATE POLICY workspace_board_cards_tenant_isolation ON gba.workspace_board_cards
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS tenant_brand_themes_tenant_isolation ON gba.tenant_brand_themes;
CREATE POLICY tenant_brand_themes_tenant_isolation ON gba.tenant_brand_themes
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.custom_field_definitions TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.custom_field_values TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.workspace_boards TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.workspace_board_cards TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.tenant_brand_themes TO gba_runtime;
