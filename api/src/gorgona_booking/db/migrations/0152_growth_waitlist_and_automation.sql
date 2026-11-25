-- 0152_growth_waitlist_and_automation.sql
-- Universal growth automation settings and smart waitlist (invoker-only, FORCE RLS).

CREATE TABLE gba.growth_settings (
    tenant_id uuid PRIMARY KEY REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    google_review_url text CHECK (
        google_review_url IS NULL
        OR (char_length(google_review_url) BETWEEN 12 AND 500 AND google_review_url LIKE 'https://%')
    ),
    reminder_hours_before integer NOT NULL DEFAULT 24 CHECK (reminder_hours_before BETWEEN 1 AND 168),
    review_delay_hours integer NOT NULL DEFAULT 2 CHECK (review_delay_hours BETWEEN 0 AND 168),
    rebooking_days_after integer NOT NULL DEFAULT 28 CHECK (rebooking_days_after BETWEEN 7 AND 365),
    waitlist_auto_offer boolean NOT NULL DEFAULT true,
    ai_concierge_enabled boolean NOT NULL DEFAULT true,
    ai_concierge_tone text NOT NULL DEFAULT 'warm_professional' CHECK (
        ai_concierge_tone IN ('warm_professional', 'concise_direct', 'luxury_concierge')
    ),
    updated_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE gba.waitlist_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    location_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    preferred_resource_id uuid,
    preferred_day date NOT NULL,
    preferred_window text NOT NULL DEFAULT 'any' CHECK (
        preferred_window IN ('any', 'morning', 'afternoon', 'evening')
    ),
    customer_name text NOT NULL CHECK (char_length(customer_name) BETWEEN 1 AND 160),
    contact_channel text NOT NULL CHECK (contact_channel IN ('email', 'sms')),
    contact_masked text NOT NULL CHECK (char_length(contact_masked) BETWEEN 3 AND 160),
    contact_hash text NOT NULL CHECK (char_length(contact_hash) = 64),
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 400),
    status text NOT NULL DEFAULT 'waiting' CHECK (
        status IN ('waiting', 'offered', 'booked', 'expired', 'cancelled')
    ),
    offered_at timestamptz,
    offer_notification_id uuid REFERENCES gba.notification_outbox(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, location_id) REFERENCES gba.locations(tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, variant_id) REFERENCES gba.service_variants(tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, preferred_resource_id) REFERENCES gba.resources(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX waitlist_entries_tenant_status_day_idx
    ON gba.waitlist_entries (tenant_id, status, preferred_day, created_at);

ALTER TABLE gba.growth_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.growth_settings FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.waitlist_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.waitlist_entries FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS growth_settings_tenant_isolation ON gba.growth_settings;
CREATE POLICY growth_settings_tenant_isolation ON gba.growth_settings
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS waitlist_entries_tenant_isolation ON gba.waitlist_entries;
CREATE POLICY waitlist_entries_tenant_isolation ON gba.waitlist_entries
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE ON TABLE gba.growth_settings TO gba_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE gba.waitlist_entries TO gba_runtime;
