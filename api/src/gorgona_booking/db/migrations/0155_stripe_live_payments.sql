-- 0155_stripe_live_payments.sql
-- Stripe US Live/Test Checkout sessions & idempotent webhook event ledger (FORCE RLS, USD).

CREATE TABLE gba.payment_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    provider text NOT NULL CHECK (provider IN ('stripe', 'paypal')),
    livemode boolean NOT NULL DEFAULT false,
    provider_session_id text NOT NULL CHECK (char_length(provider_session_id) BETWEEN 4 AND 200),
    provider_payment_intent_id text,
    connected_account_id text,
    reference_kind text NOT NULL CHECK (
        reference_kind IN ('invoice', 'order', 'deposit', 'service', 'custom')
    ),
    reference_id text,
    customer_name text NOT NULL DEFAULT '',
    customer_email text,
    description text NOT NULL CHECK (char_length(description) BETWEEN 1 AND 300),
    amount_cents bigint NOT NULL CHECK (amount_cents BETWEEN 50 AND 99999999),
    currency text NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    status text NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'paid', 'expired', 'failed', 'refunded')
    ),
    checkout_url text NOT NULL CHECK (char_length(checkout_url) BETWEEN 8 AND 2000),
    paid_at timestamptz,
    refunded_at timestamptz,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, provider, provider_session_id)
);

CREATE INDEX payment_sessions_tenant_created_idx
    ON gba.payment_sessions (tenant_id, created_at DESC);

CREATE INDEX payment_sessions_tenant_intent_idx
    ON gba.payment_sessions (tenant_id, provider_payment_intent_id)
    WHERE provider_payment_intent_id IS NOT NULL;

ALTER TABLE gba.payment_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.payment_sessions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS payment_sessions_tenant_isolation ON gba.payment_sessions;
CREATE POLICY payment_sessions_tenant_isolation ON gba.payment_sessions
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE ON TABLE gba.payment_sessions TO gba_runtime;

CREATE TABLE gba.payment_webhook_events (
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    provider text NOT NULL CHECK (provider IN ('stripe', 'paypal')),
    event_id text NOT NULL CHECK (char_length(event_id) BETWEEN 4 AND 200),
    event_type text NOT NULL CHECK (char_length(event_type) BETWEEN 2 AND 120),
    livemode boolean NOT NULL DEFAULT false,
    provider_session_id text,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, provider, event_id)
);

ALTER TABLE gba.payment_webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.payment_webhook_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS payment_webhook_events_tenant_isolation ON gba.payment_webhook_events;
CREATE POLICY payment_webhook_events_tenant_isolation ON gba.payment_webhook_events
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT ON TABLE gba.payment_webhook_events TO gba_runtime;
