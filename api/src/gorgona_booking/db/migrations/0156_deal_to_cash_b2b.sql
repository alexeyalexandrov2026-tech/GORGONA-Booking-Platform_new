-- 0156_deal_to_cash_b2b.sql
-- AMARKAL v2.10.0: Deal-to-Cash B2B Engine — Commercial Quotes (CPQ),
-- Purchase Orders & 3-Way Match, Approval Policies, and Tokenized B2B Portal
-- (invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, zero SECURITY DEFINER).

CREATE TABLE gba.commercial_quotes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    quote_number text NOT NULL CHECK (char_length(quote_number) BETWEEN 2 AND 48),
    title text NOT NULL CHECK (char_length(title) BETWEEN 2 AND 200),
    counterparty_id uuid,
    counterparty_name text NOT NULL CHECK (char_length(counterparty_name) BETWEEN 1 AND 160),
    counterparty_email text,
    currency text NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    items jsonb NOT NULL DEFAULT '[]'::jsonb,
    subtotal_cents bigint NOT NULL DEFAULT 0 CHECK (subtotal_cents >= 0),
    discount_cents bigint NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    tax_cents bigint NOT NULL DEFAULT 0 CHECK (tax_cents >= 0),
    total_cents bigint NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
    payment_terms text NOT NULL DEFAULT 'Net 30' CHECK (
        payment_terms IN ('Due on receipt', 'Net 15', 'Net 30', 'Net 45', 'Net 60')
    ),
    valid_until date,
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 2000),
    status text NOT NULL DEFAULT 'draft' CHECK (
        status IN (
            'draft',
            'pending_approval',
            'approved',
            'sent',
            'accepted',
            'declined',
            'converted',
            'void'
        )
    ),
    approval_required boolean NOT NULL DEFAULT false,
    approved_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    approved_at timestamptz,
    accepted_by_name text,
    accepted_at timestamptz,
    declined_reason text,
    payment_session_id uuid REFERENCES gba.payment_sessions(id) ON DELETE SET NULL,
    converted_invoice_ref text,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, quote_number)
);

CREATE INDEX commercial_quotes_tenant_created_idx
    ON gba.commercial_quotes (tenant_id, created_at DESC);

CREATE INDEX commercial_quotes_tenant_status_idx
    ON gba.commercial_quotes (tenant_id, status, created_at DESC);

CREATE TABLE gba.purchase_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    po_number text NOT NULL CHECK (char_length(po_number) BETWEEN 2 AND 48),
    title text NOT NULL CHECK (char_length(title) BETWEEN 2 AND 200),
    vendor_counterparty_id uuid,
    vendor_name text NOT NULL CHECK (char_length(vendor_name) BETWEEN 1 AND 160),
    vendor_email text,
    currency text NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    items jsonb NOT NULL DEFAULT '[]'::jsonb,
    total_cents bigint NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
    payment_terms text NOT NULL DEFAULT 'Net 30' CHECK (
        payment_terms IN ('Due on receipt', 'Net 15', 'Net 30', 'Net 45', 'Net 60')
    ),
    expected_delivery_date date,
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 2000),
    status text NOT NULL DEFAULT 'draft' CHECK (
        status IN (
            'draft',
            'pending_approval',
            'approved',
            'issued',
            'acknowledged',
            'partially_received',
            'received',
            'matched',
            'cancelled'
        )
    ),
    received_total_cents bigint NOT NULL DEFAULT 0 CHECK (received_total_cents >= 0),
    vendor_bill_number text,
    vendor_bill_cents bigint CHECK (vendor_bill_cents IS NULL OR vendor_bill_cents >= 0),
    three_way_match_status text NOT NULL DEFAULT 'unmatched' CHECK (
        three_way_match_status IN ('unmatched', 'variance', 'matched')
    ),
    variance_cents bigint NOT NULL DEFAULT 0,
    approval_required boolean NOT NULL DEFAULT false,
    approved_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    approved_at timestamptz,
    vendor_acknowledged_by text,
    vendor_acknowledged_at timestamptz,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, po_number)
);

CREATE INDEX purchase_orders_tenant_created_idx
    ON gba.purchase_orders (tenant_id, created_at DESC);

CREATE INDEX purchase_orders_tenant_status_idx
    ON gba.purchase_orders (tenant_id, status, created_at DESC);

CREATE TABLE gba.approval_policies (
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    entity_kind text NOT NULL CHECK (entity_kind IN ('quote', 'purchase_order')),
    threshold_cents bigint NOT NULL DEFAULT 250000 CHECK (threshold_cents >= 0),
    require_owner_above_threshold boolean NOT NULL DEFAULT true,
    auto_approve_below_threshold boolean NOT NULL DEFAULT true,
    updated_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, entity_kind)
);

CREATE TABLE gba.b2b_portal_links (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    entity_kind text NOT NULL CHECK (entity_kind IN ('quote', 'purchase_order')),
    entity_id uuid NOT NULL,
    token_prefix text NOT NULL CHECK (char_length(token_prefix) BETWEEN 6 AND 20),
    token_hash text NOT NULL UNIQUE CHECK (char_length(token_hash) = 64),
    recipient_name text NOT NULL DEFAULT '' CHECK (char_length(recipient_name) <= 160),
    recipient_email text,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    last_viewed_at timestamptz,
    responded_at timestamptz,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX b2b_portal_links_tenant_entity_idx
    ON gba.b2b_portal_links (tenant_id, entity_kind, entity_id, created_at DESC);

ALTER TABLE gba.commercial_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.commercial_quotes FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.purchase_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.purchase_orders FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.approval_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.approval_policies FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.b2b_portal_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.b2b_portal_links FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS commercial_quotes_tenant_isolation ON gba.commercial_quotes;
CREATE POLICY commercial_quotes_tenant_isolation ON gba.commercial_quotes
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS purchase_orders_tenant_isolation ON gba.purchase_orders;
CREATE POLICY purchase_orders_tenant_isolation ON gba.purchase_orders
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS approval_policies_tenant_isolation ON gba.approval_policies;
CREATE POLICY approval_policies_tenant_isolation ON gba.approval_policies
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

-- External portal lookup resolves strictly one active row by exact SHA-256 token hash.
DROP POLICY IF EXISTS b2b_portal_links_tenant_isolation ON gba.b2b_portal_links;
CREATE POLICY b2b_portal_links_tenant_isolation ON gba.b2b_portal_links
    FOR ALL
    TO gba_runtime
    USING (
        tenant_id = gba.current_tenant_id()
        OR token_hash = nullif(pg_catalog.current_setting('gba.portal_token_hash', true), '')
    )
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE ON TABLE gba.commercial_quotes TO gba_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE gba.purchase_orders TO gba_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE gba.approval_policies TO gba_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE gba.b2b_portal_links TO gba_runtime;
