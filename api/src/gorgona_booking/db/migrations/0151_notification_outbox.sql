-- 0151_notification_outbox.sql
-- Tenant-scoped transactional Email & SMS notification outbox (invoker-only, FORCE RLS).

CREATE TABLE gba.notification_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    channel text NOT NULL CHECK (channel IN ('email', 'sms')),
    template_code text NOT NULL CHECK (char_length(template_code) BETWEEN 2 AND 80),
    recipient_masked text NOT NULL CHECK (char_length(recipient_masked) BETWEEN 3 AND 160),
    recipient_hash text NOT NULL CHECK (char_length(recipient_hash) = 64),
    subject text NOT NULL DEFAULT '' CHECK (char_length(subject) <= 240),
    body_preview text NOT NULL CHECK (char_length(body_preview) BETWEEN 1 AND 2000),
    idempotency_key text NOT NULL CHECK (char_length(idempotency_key) BETWEEN 4 AND 128),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'failed', 'dead_lettered')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    provider_name text NOT NULL DEFAULT '',
    provider_message_id text,
    last_error text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,
    UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX notification_outbox_tenant_status_idx
    ON gba.notification_outbox (tenant_id, status, next_attempt_at);

ALTER TABLE gba.notification_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.notification_outbox FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS notification_outbox_tenant_isolation ON gba.notification_outbox;
CREATE POLICY notification_outbox_tenant_isolation ON gba.notification_outbox
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE ON TABLE gba.notification_outbox TO gba_runtime;
