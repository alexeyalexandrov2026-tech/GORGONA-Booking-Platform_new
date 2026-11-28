-- 0163_omnichannel_unified_inbox.sql
-- AMARKAL v2.19.0: Omnichannel Unified Client Inbox (Built-in Email Client,
-- Virtual PBX / Call & Voicemail Logs, SMS / WhatsApp / Web-Chat Messenger Aggregator).
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, zero SECURITY DEFINER.

CREATE TABLE gba.omnichannel_channels (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    channel_type text NOT NULL CHECK (
        channel_type IN ('email', 'voice_pbx', 'sms', 'whatsapp', 'web_chat')
    ),
    display_name text NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 2 AND 120),
    address_or_number text NOT NULL DEFAULT '' CHECK (char_length(address_or_number) <= 160),
    mode text NOT NULL DEFAULT 'built_in' CHECK (mode IN ('built_in', 'optional_byok')),
    provider_label text NOT NULL DEFAULT 'AMARKAL Built-In' CHECK (
        char_length(provider_label) <= 120
    ),
    is_enabled boolean NOT NULL DEFAULT true,
    auto_greeting text NOT NULL DEFAULT '' CHECK (char_length(auto_greeting) <= 500),
    webhook_token_prefix text CHECK (
        webhook_token_prefix IS NULL OR char_length(webhook_token_prefix) BETWEEN 6 AND 20
    ),
    webhook_token_hash text UNIQUE CHECK (
        webhook_token_hash IS NULL OR char_length(webhook_token_hash) = 64
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, channel_type)
);

CREATE INDEX omnichannel_channels_tenant_idx
    ON gba.omnichannel_channels (tenant_id, channel_type);

CREATE TABLE gba.omnichannel_threads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    contact_name text NOT NULL CHECK (char_length(btrim(contact_name)) BETWEEN 1 AND 160),
    contact_email text CHECK (contact_email IS NULL OR char_length(contact_email) <= 160),
    contact_phone text CHECK (contact_phone IS NULL OR char_length(contact_phone) <= 40),
    counterparty_id uuid,
    linked_entity_kind text CHECK (
        linked_entity_kind IS NULL
        OR linked_entity_kind IN ('quote', 'purchase_order', 'booking', 'work_order')
    ),
    linked_entity_ref text CHECK (
        linked_entity_ref IS NULL OR char_length(linked_entity_ref) <= 80
    ),
    primary_channel text NOT NULL DEFAULT 'email' CHECK (
        primary_channel IN ('email', 'voice_pbx', 'sms', 'whatsapp', 'web_chat')
    ),
    subject text NOT NULL DEFAULT '' CHECK (char_length(subject) <= 240),
    status text NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'pending', 'snoozed', 'resolved')
    ),
    priority text NOT NULL DEFAULT 'normal' CHECK (
        priority IN ('low', 'normal', 'high', 'urgent')
    ),
    unread_count integer NOT NULL DEFAULT 0 CHECK (unread_count >= 0),
    assigned_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    last_message_preview text NOT NULL DEFAULT '' CHECK (char_length(last_message_preview) <= 300),
    last_message_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE INDEX omnichannel_threads_tenant_recent_idx
    ON gba.omnichannel_threads (tenant_id, status, last_message_at DESC);

CREATE INDEX omnichannel_threads_tenant_email_idx
    ON gba.omnichannel_threads (tenant_id, lower(contact_email))
    WHERE contact_email IS NOT NULL;

CREATE TABLE gba.omnichannel_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    thread_id uuid NOT NULL,
    channel_type text NOT NULL CHECK (
        channel_type IN ('email', 'voice_pbx', 'sms', 'whatsapp', 'web_chat', 'internal_note')
    ),
    direction text NOT NULL CHECK (direction IN ('inbound', 'outbound', 'internal')),
    sender_name text NOT NULL DEFAULT '' CHECK (char_length(sender_name) <= 160),
    sender_address text NOT NULL DEFAULT '' CHECK (char_length(sender_address) <= 160),
    recipient_address text NOT NULL DEFAULT '' CHECK (char_length(recipient_address) <= 160),
    subject text NOT NULL DEFAULT '' CHECK (char_length(subject) <= 240),
    body text NOT NULL CHECK (char_length(btrim(body)) BETWEEN 1 AND 8000),
    delivery_status text NOT NULL DEFAULT 'sent' CHECK (
        delivery_status IN ('received', 'queued', 'sent', 'delivered', 'failed', 'logged')
    ),
    provider_message_id text CHECK (
        provider_message_id IS NULL OR char_length(provider_message_id) <= 160
    ),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES gba.omnichannel_threads(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX omnichannel_messages_thread_time_idx
    ON gba.omnichannel_messages (tenant_id, thread_id, created_at ASC);

CREATE TABLE gba.omnichannel_call_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    thread_id uuid,
    direction text NOT NULL CHECK (direction IN ('inbound', 'outbound', 'missed')),
    caller_number text NOT NULL DEFAULT '' CHECK (char_length(caller_number) <= 40),
    callee_number text NOT NULL DEFAULT '' CHECK (char_length(callee_number) <= 40),
    contact_name text NOT NULL DEFAULT '' CHECK (char_length(contact_name) <= 160),
    call_status text NOT NULL DEFAULT 'completed' CHECK (
        call_status IN ('ringing', 'completed', 'missed', 'voicemail', 'failed')
    ),
    duration_seconds integer NOT NULL DEFAULT 0 CHECK (duration_seconds >= 0),
    extension_or_queue text NOT NULL DEFAULT 'Main Desk · Ext 100' CHECK (
        char_length(extension_or_queue) <= 120
    ),
    recording_url text CHECK (recording_url IS NULL OR char_length(recording_url) <= 500),
    transcript_summary text NOT NULL DEFAULT '' CHECK (char_length(transcript_summary) <= 4000),
    disposition text NOT NULL DEFAULT 'resolved' CHECK (
        disposition IN (
            'resolved',
            'follow_up',
            'quote_requested',
            'support_ticket',
            'voicemail_left'
        )
    ),
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, thread_id)
        REFERENCES gba.omnichannel_threads(tenant_id, id) ON DELETE SET NULL
);

CREATE INDEX omnichannel_call_logs_tenant_time_idx
    ON gba.omnichannel_call_logs (tenant_id, started_at DESC);

-- ── ENABLE + FORCE ROW LEVEL SECURITY ON ALL 4 TABLES ───────────────────────

ALTER TABLE gba.omnichannel_channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.omnichannel_channels FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.omnichannel_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.omnichannel_threads FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.omnichannel_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.omnichannel_messages FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.omnichannel_call_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.omnichannel_call_logs FORCE ROW LEVEL SECURITY;

-- Allows tenant management OR exact SHA-256 inbound webhook lookup without SECURITY DEFINER
DROP POLICY IF EXISTS omnichannel_channels_tenant_isolation ON gba.omnichannel_channels;
CREATE POLICY omnichannel_channels_tenant_isolation ON gba.omnichannel_channels
    FOR ALL TO gba_runtime
    USING (
        tenant_id = gba.current_tenant_id()
        OR webhook_token_hash = nullif(pg_catalog.current_setting('gba.inbox_webhook_hash', true), '')
    )
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS omnichannel_threads_tenant_isolation ON gba.omnichannel_threads;
CREATE POLICY omnichannel_threads_tenant_isolation ON gba.omnichannel_threads
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS omnichannel_messages_tenant_isolation ON gba.omnichannel_messages;
CREATE POLICY omnichannel_messages_tenant_isolation ON gba.omnichannel_messages
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS omnichannel_call_logs_tenant_isolation ON gba.omnichannel_call_logs;
CREATE POLICY omnichannel_call_logs_tenant_isolation ON gba.omnichannel_call_logs
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.omnichannel_channels TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.omnichannel_threads TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.omnichannel_messages TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.omnichannel_call_logs TO gba_runtime;
