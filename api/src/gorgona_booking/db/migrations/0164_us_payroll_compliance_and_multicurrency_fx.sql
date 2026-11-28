-- 0164_us_payroll_compliance_and_multicurrency_fx.sql
-- AMARKAL v2.20.0: US Payroll Prep & FLSA/CA/Union Compliance +
-- Next-Gen Multi-Currency FX Ledger (Live Unrealized/Realized FX Gain/Loss) +
-- International Tax Profiles (EU/UK VAT, Reverse Charge, GST/HST, IVA) & Local Payment Rails.
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, zero SECURITY DEFINER.

CREATE TABLE gba.payroll_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    employee_code text NOT NULL CHECK (char_length(btrim(employee_code)) BETWEEN 2 AND 48),
    full_name text NOT NULL CHECK (char_length(btrim(full_name)) BETWEEN 2 AND 160),
    email text CHECK (email IS NULL OR char_length(email) <= 160),
    work_state text NOT NULL DEFAULT 'IL' CHECK (work_state ~ '^[A-Z]{2}$'),
    pay_type text NOT NULL DEFAULT 'hourly' CHECK (pay_type IN ('hourly', 'salaried')),
    base_rate_cents bigint NOT NULL CHECK (base_rate_cents >= 0),
    overtime_rule text NOT NULL DEFAULT 'flsa_weekly_40' CHECK (
        overtime_rule IN ('flsa_weekly_40', 'california_daily_8_12', 'union_cba_custom')
    ),
    union_local_code text NOT NULL DEFAULT '' CHECK (char_length(union_local_code) <= 80),
    union_dues_cents bigint NOT NULL DEFAULT 0 CHECK (union_dues_cents >= 0),
    union_ot_multiplier_bps integer NOT NULL DEFAULT 15000 CHECK (
        union_ot_multiplier_bps BETWEEN 10000 AND 30000
    ),
    union_doubletime_bps integer NOT NULL DEFAULT 20000 CHECK (
        union_doubletime_bps BETWEEN 15000 AND 40000
    ),
    health_insurance_pretax_cents bigint NOT NULL DEFAULT 0 CHECK (
        health_insurance_pretax_cents >= 0
    ),
    retirement_401k_bps integer NOT NULL DEFAULT 0 CHECK (
        retirement_401k_bps BETWEEN 0 AND 5000
    ),
    filing_status text NOT NULL DEFAULT 'single' CHECK (
        filing_status IN ('single', 'married_joint', 'head_of_household')
    ),
    state_tax_override_bps integer CHECK (
        state_tax_override_bps IS NULL OR state_tax_override_bps BETWEEN 0 AND 2000
    ),
    external_payroll_provider text NOT NULL DEFAULT 'none' CHECK (
        external_payroll_provider IN ('none', 'gusto', 'check_embedded', 'adp', 'rippling')
    ),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, employee_code),
    UNIQUE (tenant_id, id)
);

CREATE INDEX payroll_profiles_tenant_state_idx
    ON gba.payroll_profiles (tenant_id, work_state, employee_code);

CREATE TABLE gba.payroll_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    run_number text NOT NULL CHECK (char_length(btrim(run_number)) BETWEEN 2 AND 48),
    period_start date NOT NULL,
    period_end date NOT NULL,
    pay_date date NOT NULL,
    status text NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'approved', 'exported_to_provider', 'void')
    ),
    total_gross_cents bigint NOT NULL DEFAULT 0 CHECK (total_gross_cents >= 0),
    total_employee_taxes_cents bigint NOT NULL DEFAULT 0 CHECK (total_employee_taxes_cents >= 0),
    total_employer_taxes_cents bigint NOT NULL DEFAULT 0 CHECK (total_employer_taxes_cents >= 0),
    total_deductions_cents bigint NOT NULL DEFAULT 0 CHECK (total_deductions_cents >= 0),
    total_net_cents bigint NOT NULL DEFAULT 0 CHECK (total_net_cents >= 0),
    export_provider text NOT NULL DEFAULT 'csv_adp_gusto' CHECK (
        export_provider IN ('csv_adp_gusto', 'gusto_api', 'check_embedded')
    ),
    approved_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    approved_at timestamptz,
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 1000),
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (period_end >= period_start),
    UNIQUE (tenant_id, run_number),
    UNIQUE (tenant_id, id)
);

CREATE INDEX payroll_runs_tenant_created_idx
    ON gba.payroll_runs (tenant_id, created_at DESC);

CREATE TABLE gba.payroll_run_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    run_id uuid NOT NULL,
    profile_id uuid NOT NULL,
    employee_name text NOT NULL CHECK (char_length(btrim(employee_name)) BETWEEN 1 AND 160),
    work_state text NOT NULL CHECK (work_state ~ '^[A-Z]{2}$'),
    regular_hours_milli bigint NOT NULL DEFAULT 0 CHECK (regular_hours_milli >= 0),
    overtime_hours_milli bigint NOT NULL DEFAULT 0 CHECK (overtime_hours_milli >= 0),
    doubletime_hours_milli bigint NOT NULL DEFAULT 0 CHECK (doubletime_hours_milli >= 0),
    bonus_cents bigint NOT NULL DEFAULT 0 CHECK (bonus_cents >= 0),
    regular_pay_cents bigint NOT NULL DEFAULT 0 CHECK (regular_pay_cents >= 0),
    overtime_pay_cents bigint NOT NULL DEFAULT 0 CHECK (overtime_pay_cents >= 0),
    doubletime_pay_cents bigint NOT NULL DEFAULT 0 CHECK (doubletime_pay_cents >= 0),
    gross_pay_cents bigint NOT NULL DEFAULT 0 CHECK (gross_pay_cents >= 0),
    pretax_health_cents bigint NOT NULL DEFAULT 0 CHECK (pretax_health_cents >= 0),
    pretax_401k_cents bigint NOT NULL DEFAULT 0 CHECK (pretax_401k_cents >= 0),
    federal_income_tax_cents bigint NOT NULL DEFAULT 0 CHECK (federal_income_tax_cents >= 0),
    state_income_tax_cents bigint NOT NULL DEFAULT 0 CHECK (state_income_tax_cents >= 0),
    social_security_cents bigint NOT NULL DEFAULT 0 CHECK (social_security_cents >= 0),
    medicare_cents bigint NOT NULL DEFAULT 0 CHECK (medicare_cents >= 0),
    union_dues_cents bigint NOT NULL DEFAULT 0 CHECK (union_dues_cents >= 0),
    net_pay_cents bigint NOT NULL DEFAULT 0 CHECK (net_pay_cents >= 0),
    employer_fica_cents bigint NOT NULL DEFAULT 0 CHECK (employer_fica_cents >= 0),
    employer_futa_suta_cents bigint NOT NULL DEFAULT 0 CHECK (employer_futa_suta_cents >= 0),
    compliance_notes text NOT NULL DEFAULT '' CHECK (char_length(compliance_notes) <= 500),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, run_id, profile_id),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES gba.payroll_runs(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, profile_id)
        REFERENCES gba.payroll_profiles(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX payroll_run_lines_tenant_run_idx
    ON gba.payroll_run_lines (tenant_id, run_id);

-- ── Multi-Currency FX Rates & FX Ledger ──────────────────────────────────────

CREATE TABLE gba.fx_rates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    base_currency text NOT NULL CHECK (
        base_currency IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'CHF', 'AUD', 'JPY')
    ),
    quote_currency text NOT NULL DEFAULT 'USD' CHECK (quote_currency = 'USD'),
    rate_micros bigint NOT NULL CHECK (rate_micros >= 1),
    source text NOT NULL DEFAULT 'manual' CHECK (
        source IN ('manual', 'ecb_feed', 'fed_h10', 'treasury')
    ),
    effective_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, base_currency, quote_currency)
);

CREATE TABLE gba.fx_ledger_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    entry_number text NOT NULL CHECK (char_length(btrim(entry_number)) BETWEEN 2 AND 48),
    entry_date date NOT NULL DEFAULT CURRENT_DATE,
    description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 2 AND 240),
    counterparty_name text NOT NULL DEFAULT '' CHECK (char_length(counterparty_name) <= 160),
    currency text NOT NULL CHECK (
        currency IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'CHF', 'AUD', 'JPY')
    ),
    amount_minor bigint NOT NULL CHECK (amount_minor >= 1),
    entry_kind text NOT NULL DEFAULT 'receivable' CHECK (
        entry_kind IN ('receivable', 'payable', 'cash_balance')
    ),
    booking_rate_micros bigint NOT NULL CHECK (booking_rate_micros >= 1),
    booked_usd_cents bigint NOT NULL CHECK (booked_usd_cents >= 0),
    current_rate_micros bigint NOT NULL CHECK (current_rate_micros >= 1),
    revalued_usd_cents bigint NOT NULL CHECK (revalued_usd_cents >= 0),
    fx_gain_loss_cents bigint NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'settled')),
    settled_rate_micros bigint CHECK (settled_rate_micros IS NULL OR settled_rate_micros >= 1),
    realized_fx_gain_loss_cents bigint NOT NULL DEFAULT 0,
    settled_at timestamptz,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, entry_number)
);

CREATE INDEX fx_ledger_entries_tenant_status_idx
    ON gba.fx_ledger_entries (tenant_id, status, entry_date DESC);

-- ── International Tax Profiles & Local Payment Rails ─────────────────────────

CREATE TABLE gba.international_tax_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    country_code text NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
    region_label text NOT NULL CHECK (char_length(btrim(region_label)) BETWEEN 2 AND 120),
    tax_regime text NOT NULL CHECK (
        tax_regime IN (
            'us_sales_tax',
            'eu_vat',
            'uk_vat',
            'ca_gst_hst',
            'mx_iva',
            'ch_mwst',
            'au_gst'
        )
    ),
    tax_name text NOT NULL CHECK (char_length(btrim(tax_name)) BETWEEN 2 AND 80),
    standard_rate_bps integer NOT NULL CHECK (standard_rate_bps BETWEEN 0 AND 4000),
    reduced_rate_bps integer NOT NULL DEFAULT 0 CHECK (reduced_rate_bps BETWEEN 0 AND 4000),
    reverse_charge_b2b boolean NOT NULL DEFAULT false,
    tax_registration_id text NOT NULL DEFAULT '' CHECK (char_length(tax_registration_id) <= 64),
    default_currency text NOT NULL DEFAULT 'USD' CHECK (
        default_currency IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'CHF', 'AUD', 'JPY')
    ),
    reporting_standard text NOT NULL DEFAULT 'US_GAAP' CHECK (
        reporting_standard IN ('US_GAAP', 'IFRS_EU', 'UK_FRS102', 'ASPE_CA', 'NIF_MX')
    ),
    is_default boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, country_code, tax_regime)
);

CREATE TABLE gba.local_payment_rails (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    rail_code text NOT NULL CHECK (
        rail_code IN (
            'stripe_us_ach_card',
            'sepa_instant_eu',
            'uk_faster_payments',
            'ca_interac_eft',
            'mx_spei',
            'ch_qr_bill',
            'au_payid_becs',
            'swift_wire'
        )
    ),
    display_name text NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 2 AND 120),
    country_code text NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
    currency text NOT NULL CHECK (
        currency IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'CHF', 'AUD', 'JPY')
    ),
    settlement_instructions text NOT NULL DEFAULT '' CHECK (
        char_length(settlement_instructions) <= 1000
    ),
    iban_or_routing_masked text NOT NULL DEFAULT '' CHECK (
        char_length(iban_or_routing_masked) <= 64
    ),
    is_enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, rail_code)
);

-- ── ENABLE + FORCE ROW LEVEL SECURITY ON ALL 7 TABLES ───────────────────────

ALTER TABLE gba.payroll_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.payroll_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.payroll_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.payroll_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.payroll_run_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.payroll_run_lines FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.fx_rates ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.fx_rates FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.fx_ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.fx_ledger_entries FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.international_tax_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.international_tax_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.local_payment_rails ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.local_payment_rails FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS payroll_profiles_tenant_isolation ON gba.payroll_profiles;
CREATE POLICY payroll_profiles_tenant_isolation ON gba.payroll_profiles
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS payroll_runs_tenant_isolation ON gba.payroll_runs;
CREATE POLICY payroll_runs_tenant_isolation ON gba.payroll_runs
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS payroll_run_lines_tenant_isolation ON gba.payroll_run_lines;
CREATE POLICY payroll_run_lines_tenant_isolation ON gba.payroll_run_lines
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS fx_rates_tenant_isolation ON gba.fx_rates;
CREATE POLICY fx_rates_tenant_isolation ON gba.fx_rates
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS fx_ledger_entries_tenant_isolation ON gba.fx_ledger_entries;
CREATE POLICY fx_ledger_entries_tenant_isolation ON gba.fx_ledger_entries
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS international_tax_profiles_tenant_isolation ON gba.international_tax_profiles;
CREATE POLICY international_tax_profiles_tenant_isolation ON gba.international_tax_profiles
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS local_payment_rails_tenant_isolation ON gba.local_payment_rails;
CREATE POLICY local_payment_rails_tenant_isolation ON gba.local_payment_rails
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.payroll_profiles TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.payroll_runs TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.payroll_run_lines TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.fx_rates TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.fx_ledger_entries TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.international_tax_profiles TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.local_payment_rails TO gba_runtime;
