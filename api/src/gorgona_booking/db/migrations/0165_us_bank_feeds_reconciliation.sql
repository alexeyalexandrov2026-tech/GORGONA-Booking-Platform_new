-- 0165_us_bank_feeds_reconciliation.sql
-- AMARKAL v2.26.0: US Direct Bank Feeds (OFX/QFX/QBO/CSV Statement Importer,
-- Human-in-the-Loop Auto-Reconciliation Engine, and Plaid BYOK Connector).
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, zero SECURITY DEFINER.

CREATE TABLE gba.bank_feed_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    institution_name text NOT NULL CHECK (char_length(btrim(institution_name)) BETWEEN 2 AND 120),
    account_name text NOT NULL CHECK (char_length(btrim(account_name)) BETWEEN 2 AND 120),
    account_mask text NOT NULL DEFAULT '0000' CHECK (account_mask ~ '^[0-9A-Za-z]{2,8}$'),
    account_type text NOT NULL DEFAULT 'checking' CHECK (
        account_type IN ('checking', 'savings', 'credit_card', 'treasury')
    ),
    currency text NOT NULL DEFAULT 'USD' CHECK (
        currency IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'CHF', 'AUD', 'JPY')
    ),
    connection_mode text NOT NULL DEFAULT 'statement_upload' CHECK (
        connection_mode IN ('statement_upload', 'plaid_sandbox', 'plaid_production')
    ),
    plaid_item_id text CHECK (plaid_item_id IS NULL OR char_length(plaid_item_id) <= 120),
    plaid_account_id text CHECK (plaid_account_id IS NULL OR char_length(plaid_account_id) <= 120),
    current_balance_cents bigint NOT NULL DEFAULT 0,
    last_synced_at timestamptz,
    is_active boolean NOT NULL DEFAULT true,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE INDEX bank_feed_accounts_tenant_created_idx
    ON gba.bank_feed_accounts (tenant_id, is_active, created_at DESC);

CREATE TABLE gba.bank_feed_transactions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    bank_account_id uuid NOT NULL,
    external_tx_id text NOT NULL CHECK (char_length(btrim(external_tx_id)) BETWEEN 2 AND 128),
    posted_date date NOT NULL,
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 1 AND 300),
    merchant_name text NOT NULL DEFAULT '' CHECK (char_length(merchant_name) <= 160),
    direction text NOT NULL CHECK (direction IN ('credit', 'debit')),
    amount_cents bigint NOT NULL CHECK (amount_cents >= 1),
    currency text NOT NULL DEFAULT 'USD' CHECK (
        currency IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'CHF', 'AUD', 'JPY')
    ),
    category_hint text NOT NULL DEFAULT 'uncategorized' CHECK (char_length(category_hint) <= 80),
    source_format text NOT NULL DEFAULT 'csv' CHECK (
        source_format IN ('ofx', 'qfx', 'qbo', 'csv', 'plaid', 'manual')
    ),
    reconciliation_status text NOT NULL DEFAULT 'unmatched' CHECK (
        reconciliation_status IN ('unmatched', 'suggested', 'reconciled', 'excluded')
    ),
    matched_entity_kind text CHECK (
        matched_entity_kind IS NULL
        OR matched_entity_kind IN (
            'invoice',
            'purchase_order',
            'payment_session',
            'payroll_run',
            'fx_entry',
            'manual_category'
        )
    ),
    matched_entity_id text CHECK (
        matched_entity_id IS NULL OR char_length(matched_entity_id) <= 120
    ),
    matched_entity_label text NOT NULL DEFAULT '' CHECK (
        char_length(matched_entity_label) <= 200
    ),
    match_confidence integer NOT NULL DEFAULT 0 CHECK (match_confidence BETWEEN 0 AND 100),
    reconciled_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    reconciled_at timestamptz,
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 500),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bank_account_id, external_tx_id),
    FOREIGN KEY (tenant_id, bank_account_id)
        REFERENCES gba.bank_feed_accounts(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX bank_feed_transactions_tenant_status_idx
    ON gba.bank_feed_transactions (tenant_id, reconciliation_status, posted_date DESC);

CREATE INDEX bank_feed_transactions_tenant_account_date_idx
    ON gba.bank_feed_transactions (tenant_id, bank_account_id, posted_date DESC);

-- ── ENABLE + FORCE ROW LEVEL SECURITY ON BOTH TABLES ─────────────────────────

ALTER TABLE gba.bank_feed_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.bank_feed_accounts FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.bank_feed_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.bank_feed_transactions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS bank_feed_accounts_tenant_isolation ON gba.bank_feed_accounts;
CREATE POLICY bank_feed_accounts_tenant_isolation ON gba.bank_feed_accounts
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS bank_feed_transactions_tenant_isolation ON gba.bank_feed_transactions;
CREATE POLICY bank_feed_transactions_tenant_isolation ON gba.bank_feed_transactions
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.bank_feed_accounts TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.bank_feed_transactions TO gba_runtime;
