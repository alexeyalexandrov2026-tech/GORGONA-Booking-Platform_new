-- 0157_recurring_billing_and_aging.sql
-- AMARKAL v2.12.0: Recurring B2B Billing / Retainers & Automated Cycle Execution
-- (invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, zero SECURITY DEFINER).

CREATE TABLE gba.recurring_schedules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    schedule_code text NOT NULL CHECK (char_length(schedule_code) BETWEEN 2 AND 48),
    title text NOT NULL CHECK (char_length(title) BETWEEN 2 AND 200),
    counterparty_id uuid,
    counterparty_name text NOT NULL CHECK (char_length(counterparty_name) BETWEEN 1 AND 160),
    counterparty_email text,
    currency text NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    amount_cents bigint NOT NULL CHECK (amount_cents BETWEEN 50 AND 99999999),
    cadence text NOT NULL CHECK (
        cadence IN ('weekly', 'biweekly', 'monthly', 'quarterly', 'annual')
    ),
    payment_terms text NOT NULL DEFAULT 'Net 30' CHECK (
        payment_terms IN ('Due on receipt', 'Net 15', 'Net 30', 'Net 45', 'Net 60')
    ),
    next_run_date date NOT NULL,
    last_run_at timestamptz,
    runs_count integer NOT NULL DEFAULT 0 CHECK (runs_count >= 0),
    auto_email_client boolean NOT NULL DEFAULT true,
    status text NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'paused', 'completed', 'cancelled')
    ),
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 2000),
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, schedule_code)
);

CREATE INDEX recurring_schedules_tenant_next_idx
    ON gba.recurring_schedules (tenant_id, status, next_run_date ASC);

ALTER TABLE gba.recurring_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.recurring_schedules FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS recurring_schedules_tenant_isolation ON gba.recurring_schedules;
CREATE POLICY recurring_schedules_tenant_isolation ON gba.recurring_schedules
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE ON TABLE gba.recurring_schedules TO gba_runtime;
