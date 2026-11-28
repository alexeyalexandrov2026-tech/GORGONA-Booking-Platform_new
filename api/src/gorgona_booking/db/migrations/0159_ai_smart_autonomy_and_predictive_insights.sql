-- 0159_ai_smart_autonomy_and_predictive_insights.sql
-- AMARKAL v2.15.0: AI Smart Autonomy (Hybrid Trust Policies + Audit Log) and
-- Proactive Predictive Insights Reports.
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY on every table.

CREATE TABLE gba.ai_autonomy_policies (
    tenant_id uuid PRIMARY KEY REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    autonomy_level text NOT NULL DEFAULT 'observe_only' CHECK (
        autonomy_level IN ('observe_only', 'safe_autopilot', 'strict_approval')
    ),
    auto_confirm_open_bookings boolean NOT NULL DEFAULT false,
    auto_send_invoice_reminders boolean NOT NULL DEFAULT false,
    auto_offer_waitlist_slots boolean NOT NULL DEFAULT false,
    auto_send_weekly_brief boolean NOT NULL DEFAULT true,
    weekly_brief_day text NOT NULL DEFAULT 'monday' CHECK (
        weekly_brief_day IN (
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'
        )
    ),
    weekly_brief_email text CHECK (
        weekly_brief_email IS NULL OR char_length(weekly_brief_email) <= 160
    ),
    require_human_approval_over_cents bigint NOT NULL DEFAULT 0 CHECK (
        require_human_approval_over_cents = 0
    ),
    updated_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE gba.ai_autonomy_executions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    action_kind text NOT NULL CHECK (
        action_kind IN (
            'send_invoice_reminder',
            'offer_waitlist_slot',
            'confirm_open_booking',
            'dispatch_weekly_brief',
            'financial_proposal_blocked'
        )
    ),
    execution_mode text NOT NULL CHECK (
        execution_mode IN (
            'autonomous_safe',
            'human_approved',
            'queued_for_approval',
            'blocked_by_policy'
        )
    ),
    target_reference text NOT NULL CHECK (char_length(target_reference) BETWEEN 1 AND 160),
    summary text NOT NULL CHECK (char_length(summary) BETWEEN 2 AND 500),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'completed' CHECK (
        status IN ('completed', 'pending_approval', 'rejected', 'rolled_back', 'failed')
    ),
    triggered_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE INDEX ai_autonomy_executions_tenant_created_idx
    ON gba.ai_autonomy_executions (tenant_id, created_at DESC);

CREATE TABLE gba.predictive_insight_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    period_days integer NOT NULL DEFAULT 30 CHECK (period_days BETWEEN 7 AND 365),
    engine text NOT NULL CHECK (
        engine IN (
            'cloudflare',
            'gemini',
            'byok_anthropic',
            'byok_gemini',
            'byok_openai',
            'grounded'
        )
    ),
    headline text NOT NULL CHECK (char_length(headline) BETWEEN 4 AND 240),
    executive_summary text NOT NULL CHECK (char_length(executive_summary) BETWEEN 4 AND 2000),
    health_score integer NOT NULL CHECK (health_score BETWEEN 0 AND 100),
    signals jsonb NOT NULL DEFAULT '[]'::jsonb,
    metrics_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    emailed_to_masked text CHECK (
        emailed_to_masked IS NULL OR char_length(emailed_to_masked) <= 160
    ),
    generated_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX predictive_insight_reports_tenant_created_idx
    ON gba.predictive_insight_reports (tenant_id, created_at DESC);

ALTER TABLE gba.ai_autonomy_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.ai_autonomy_policies FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.ai_autonomy_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.ai_autonomy_executions FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.predictive_insight_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.predictive_insight_reports FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ai_autonomy_policies_tenant_isolation ON gba.ai_autonomy_policies;
CREATE POLICY ai_autonomy_policies_tenant_isolation ON gba.ai_autonomy_policies
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS ai_autonomy_executions_tenant_isolation ON gba.ai_autonomy_executions;
CREATE POLICY ai_autonomy_executions_tenant_isolation ON gba.ai_autonomy_executions
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS predictive_insight_reports_tenant_isolation ON gba.predictive_insight_reports;
CREATE POLICY predictive_insight_reports_tenant_isolation ON gba.predictive_insight_reports
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.ai_autonomy_policies TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.ai_autonomy_executions TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.predictive_insight_reports TO gba_runtime;
