-- 0166_holding_multi_entity_intercompany.sql
-- AMARKAL v2.27.0: Holding Multi-Entity & Intercompany Consolidation
-- (Subsidiary Registry, Multi-Currency Period Trial Snapshots, Mirrored
-- Due To / Due From Intercompany Ledger, Automatic Elimination & NCI).
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, zero SECURITY DEFINER.

CREATE TABLE gba.holding_subsidiaries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    linked_legal_entity_id uuid,
    entity_code text NOT NULL CHECK (entity_code ~ '^[A-Z0-9][A-Z0-9_-]{1,31}$'),
    legal_name text NOT NULL CHECK (char_length(btrim(legal_name)) BETWEEN 2 AND 200),
    entity_role text NOT NULL DEFAULT 'operating_subsidiary' CHECK (
        entity_role IN ('parent_holding', 'operating_subsidiary', 'spv', 'regional_branch')
    ),
    jurisdiction_country text NOT NULL DEFAULT 'US' CHECK (
        jurisdiction_country ~ '^[A-Z]{2}$'
    ),
    jurisdiction_state text NOT NULL DEFAULT '' CHECK (char_length(jurisdiction_state) <= 40),
    functional_currency text NOT NULL DEFAULT 'USD' CHECK (
        functional_currency IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'CHF', 'AUD', 'JPY')
    ),
    ownership_bps integer NOT NULL DEFAULT 10000 CHECK (ownership_bps BETWEEN 0 AND 10000),
    tax_id_masked text NOT NULL DEFAULT '' CHECK (char_length(tax_id_masked) <= 48),
    is_active boolean NOT NULL DEFAULT true,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, entity_code),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, linked_legal_entity_id)
        REFERENCES gba.legal_entities(tenant_id, id) ON DELETE SET NULL
);

CREATE INDEX holding_subsidiaries_tenant_role_idx
    ON gba.holding_subsidiaries (tenant_id, entity_role, entity_code);

CREATE TABLE gba.holding_entity_trial_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    subsidiary_id uuid NOT NULL,
    period_key text NOT NULL CHECK (period_key ~ '^[0-9]{4}-[0-9]{2}$'),
    revenue_minor bigint NOT NULL DEFAULT 0 CHECK (revenue_minor >= 0),
    cogs_minor bigint NOT NULL DEFAULT 0 CHECK (cogs_minor >= 0),
    opex_minor bigint NOT NULL DEFAULT 0 CHECK (opex_minor >= 0),
    cash_minor bigint NOT NULL DEFAULT 0,
    ar_minor bigint NOT NULL DEFAULT 0 CHECK (ar_minor >= 0),
    ap_minor bigint NOT NULL DEFAULT 0 CHECK (ap_minor >= 0),
    inventory_minor bigint NOT NULL DEFAULT 0 CHECK (inventory_minor >= 0),
    fixed_assets_minor bigint NOT NULL DEFAULT 0 CHECK (fixed_assets_minor >= 0),
    debt_minor bigint NOT NULL DEFAULT 0 CHECK (debt_minor >= 0),
    equity_minor bigint NOT NULL DEFAULT 0,
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 500),
    updated_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, subsidiary_id, period_key),
    FOREIGN KEY (tenant_id, subsidiary_id)
        REFERENCES gba.holding_subsidiaries(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX holding_snapshots_tenant_period_idx
    ON gba.holding_entity_trial_snapshots (tenant_id, period_key, subsidiary_id);

CREATE TABLE gba.intercompany_transactions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    tx_number text NOT NULL CHECK (char_length(btrim(tx_number)) BETWEEN 2 AND 48),
    period_key text NOT NULL CHECK (period_key ~ '^[0-9]{4}-[0-9]{2}$'),
    tx_date date NOT NULL DEFAULT CURRENT_DATE,
    source_subsidiary_id uuid NOT NULL,
    target_subsidiary_id uuid NOT NULL,
    tx_kind text NOT NULL DEFAULT 'intercompany_service' CHECK (
        tx_kind IN (
            'intercompany_service',
            'inventory_transfer',
            'management_fee',
            'intercompany_loan',
            'cost_allocation',
            'dividend'
        )
    ),
    currency text NOT NULL DEFAULT 'USD' CHECK (
        currency IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'CHF', 'AUD', 'JPY')
    ),
    amount_minor bigint NOT NULL CHECK (amount_minor >= 1),
    fx_rate_micros bigint NOT NULL DEFAULT 1000000 CHECK (fx_rate_micros >= 1),
    usd_equivalent_cents bigint NOT NULL CHECK (usd_equivalent_cents >= 1),
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 2 AND 240),
    source_entry_label text NOT NULL CHECK (char_length(btrim(source_entry_label)) BETWEEN 2 AND 200),
    target_entry_label text NOT NULL CHECK (char_length(btrim(target_entry_label)) BETWEEN 2 AND 200),
    status text NOT NULL DEFAULT 'eliminated' CHECK (
        status IN ('posted', 'eliminated', 'void')
    ),
    eliminated_at timestamptz,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source_subsidiary_id <> target_subsidiary_id),
    UNIQUE (tenant_id, tx_number),
    FOREIGN KEY (tenant_id, source_subsidiary_id)
        REFERENCES gba.holding_subsidiaries(tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, target_subsidiary_id)
        REFERENCES gba.holding_subsidiaries(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX intercompany_tx_tenant_period_idx
    ON gba.intercompany_transactions (tenant_id, period_key, status, tx_date DESC);

-- ── ENABLE + FORCE ROW LEVEL SECURITY ON ALL 3 TABLES ────────────────────────

ALTER TABLE gba.holding_subsidiaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.holding_subsidiaries FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.holding_entity_trial_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.holding_entity_trial_snapshots FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.intercompany_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.intercompany_transactions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS holding_subsidiaries_tenant_isolation ON gba.holding_subsidiaries;
CREATE POLICY holding_subsidiaries_tenant_isolation ON gba.holding_subsidiaries
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS holding_snapshots_tenant_isolation ON gba.holding_entity_trial_snapshots;
CREATE POLICY holding_snapshots_tenant_isolation ON gba.holding_entity_trial_snapshots
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS intercompany_tx_tenant_isolation ON gba.intercompany_transactions;
CREATE POLICY intercompany_tx_tenant_isolation ON gba.intercompany_transactions
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.holding_subsidiaries TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.holding_entity_trial_snapshots TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.intercompany_transactions TO gba_runtime;
