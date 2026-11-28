-- 0162_mrp2_bom_reservations_and_predictive_eam.sql
-- AMARKAL v2.18.0: Enterprise MRP II (BOM Recipes, Multi-Level Explosion,
-- Atomic Raw-Material Reservations & Draft PO Generation) + Predictive EAM
-- (Equipment Assets, IoT Sensor Telemetry Webhook, Predictive Rules & Auto Work Orders).
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, zero SECURITY DEFINER.

CREATE TABLE gba.mrp_materials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    sku text NOT NULL CHECK (char_length(btrim(sku)) BETWEEN 2 AND 48),
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 2 AND 160),
    material_kind text NOT NULL DEFAULT 'raw' CHECK (
        material_kind IN ('raw', 'subassembly', 'finished')
    ),
    unit text NOT NULL DEFAULT 'ton' CHECK (
        unit IN ('ton', 'kg', 'lb', 'liter', 'gallon', 'meter', 'unit', 'box')
    ),
    on_hand_milli bigint NOT NULL DEFAULT 0 CHECK (on_hand_milli >= 0),
    reserved_milli bigint NOT NULL DEFAULT 0 CHECK (
        reserved_milli >= 0 AND reserved_milli <= on_hand_milli
    ),
    reorder_point_milli bigint NOT NULL DEFAULT 0 CHECK (reorder_point_milli >= 0),
    unit_cost_cents bigint NOT NULL DEFAULT 0 CHECK (unit_cost_cents >= 0),
    preferred_vendor_name text NOT NULL DEFAULT '' CHECK (char_length(preferred_vendor_name) <= 160),
    preferred_vendor_email text CHECK (
        preferred_vendor_email IS NULL OR char_length(preferred_vendor_email) <= 160
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, sku),
    UNIQUE (tenant_id, id)
);

CREATE INDEX mrp_materials_tenant_kind_idx
    ON gba.mrp_materials (tenant_id, material_kind, sku);

CREATE TABLE gba.mrp_recipes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    code text NOT NULL CHECK (char_length(btrim(code)) BETWEEN 2 AND 48),
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 2 AND 160),
    output_material_id uuid NOT NULL,
    output_qty_milli bigint NOT NULL DEFAULT 1000 CHECK (output_qty_milli >= 1),
    lead_time_days integer NOT NULL DEFAULT 1 CHECK (lead_time_days BETWEEN 0 AND 365),
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 1000),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, output_material_id)
        REFERENCES gba.mrp_materials(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX mrp_recipes_tenant_output_idx
    ON gba.mrp_recipes (tenant_id, output_material_id, is_active);

CREATE TABLE gba.mrp_recipe_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    recipe_id uuid NOT NULL,
    component_material_id uuid NOT NULL,
    qty_per_batch_milli bigint NOT NULL CHECK (qty_per_batch_milli >= 1),
    scrap_bps integer NOT NULL DEFAULT 0 CHECK (scrap_bps BETWEEN 0 AND 5000),
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 300),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, recipe_id, component_material_id),
    FOREIGN KEY (tenant_id, recipe_id)
        REFERENCES gba.mrp_recipes(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, component_material_id)
        REFERENCES gba.mrp_materials(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX mrp_recipe_lines_tenant_recipe_idx
    ON gba.mrp_recipe_lines (tenant_id, recipe_id);

CREATE TABLE gba.mrp_production_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    run_number text NOT NULL CHECK (char_length(btrim(run_number)) BETWEEN 2 AND 48),
    recipe_id uuid NOT NULL,
    target_qty_milli bigint NOT NULL CHECK (target_qty_milli >= 1),
    status text NOT NULL DEFAULT 'planned' CHECK (
        status IN ('planned', 'reserved', 'in_progress', 'completed', 'cancelled')
    ),
    scheduled_date date,
    estimated_material_cost_cents bigint NOT NULL DEFAULT 0 CHECK (
        estimated_material_cost_cents >= 0
    ),
    shortage_count integer NOT NULL DEFAULT 0 CHECK (shortage_count >= 0),
    draft_po_id uuid REFERENCES gba.purchase_orders(id) ON DELETE SET NULL,
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 1000),
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, run_number),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, recipe_id)
        REFERENCES gba.mrp_recipes(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX mrp_production_runs_tenant_created_idx
    ON gba.mrp_production_runs (tenant_id, created_at DESC);

CREATE TABLE gba.mrp_material_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    run_id uuid NOT NULL,
    material_id uuid NOT NULL,
    required_milli bigint NOT NULL CHECK (required_milli >= 1),
    reserved_milli bigint NOT NULL DEFAULT 0 CHECK (reserved_milli >= 0),
    shortage_milli bigint NOT NULL DEFAULT 0 CHECK (shortage_milli >= 0),
    unit_cost_cents bigint NOT NULL DEFAULT 0 CHECK (unit_cost_cents >= 0),
    status text NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'consumed', 'released')
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, run_id, material_id),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES gba.mrp_production_runs(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, material_id)
        REFERENCES gba.mrp_materials(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX mrp_material_reservations_tenant_run_idx
    ON gba.mrp_material_reservations (tenant_id, run_id, status);

-- ── Predictive EAM & Industrial IoT Telemetry ───────────────────────────────

CREATE TABLE gba.eam_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    asset_tag text NOT NULL CHECK (char_length(btrim(asset_tag)) BETWEEN 2 AND 48),
    name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 2 AND 160),
    category text NOT NULL DEFAULT 'fleet_vehicle' CHECK (
        category IN (
            'fleet_vehicle',
            'heavy_machinery',
            'cnc_industrial',
            'hvac_facility',
            'power_generator',
            'iot_sensor_node'
        )
    ),
    serial_number text NOT NULL DEFAULT '' CHECK (char_length(serial_number) <= 120),
    location_label text NOT NULL DEFAULT '' CHECK (char_length(location_label) <= 160),
    status text NOT NULL DEFAULT 'operational' CHECK (
        status IN ('operational', 'warning', 'maintenance_due', 'out_of_service')
    ),
    engine_hours_milli bigint NOT NULL DEFAULT 0 CHECK (engine_hours_milli >= 0),
    odometer_miles_milli bigint NOT NULL DEFAULT 0 CHECK (odometer_miles_milli >= 0),
    health_score integer NOT NULL DEFAULT 100 CHECK (health_score BETWEEN 0 AND 100),
    iot_token_prefix text CHECK (
        iot_token_prefix IS NULL OR char_length(iot_token_prefix) BETWEEN 6 AND 20
    ),
    iot_token_hash text UNIQUE CHECK (
        iot_token_hash IS NULL OR char_length(iot_token_hash) = 64
    ),
    last_telemetry_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, asset_tag),
    UNIQUE (tenant_id, id)
);

CREATE INDEX eam_assets_tenant_status_idx
    ON gba.eam_assets (tenant_id, status, asset_tag);

CREATE TABLE gba.eam_maintenance_rules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    asset_id uuid NOT NULL,
    rule_name text NOT NULL CHECK (char_length(btrim(rule_name)) BETWEEN 2 AND 160),
    metric_key text NOT NULL CHECK (
        metric_key IN (
            'engine_hours',
            'odometer_miles',
            'temperature_c',
            'vibration_mm_s',
            'oil_pressure_psi',
            'battery_voltage',
            'fuel_mpg'
        )
    ),
    operator text NOT NULL CHECK (operator IN ('gte', 'lte', 'interval_every')),
    threshold_milli bigint NOT NULL CHECK (threshold_milli >= 1),
    warning_lead_pct integer NOT NULL DEFAULT 90 CHECK (warning_lead_pct BETWEEN 50 AND 100),
    priority text NOT NULL DEFAULT 'high' CHECK (
        priority IN ('low', 'normal', 'high', 'critical')
    ),
    wo_title_template text NOT NULL CHECK (char_length(btrim(wo_title_template)) BETWEEN 2 AND 240),
    wo_checklist text NOT NULL DEFAULT '' CHECK (char_length(wo_checklist) <= 1000),
    auto_create_wo boolean NOT NULL DEFAULT true,
    last_triggered_milli bigint NOT NULL DEFAULT 0 CHECK (last_triggered_milli >= 0),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, asset_id)
        REFERENCES gba.eam_assets(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX eam_maintenance_rules_asset_metric_idx
    ON gba.eam_maintenance_rules (tenant_id, asset_id, metric_key, is_active);

CREATE TABLE gba.eam_telemetry_readings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    asset_id uuid NOT NULL,
    metric_key text NOT NULL CHECK (
        metric_key IN (
            'engine_hours',
            'odometer_miles',
            'temperature_c',
            'vibration_mm_s',
            'oil_pressure_psi',
            'battery_voltage',
            'fuel_mpg'
        )
    ),
    value_milli bigint NOT NULL,
    unit text NOT NULL DEFAULT '' CHECK (char_length(unit) <= 32),
    source text NOT NULL DEFAULT 'iot_webhook' CHECK (
        source IN ('iot_webhook', 'manual', 'telematics')
    ),
    anomaly_flagged boolean NOT NULL DEFAULT false,
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 500),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, asset_id)
        REFERENCES gba.eam_assets(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX eam_telemetry_readings_asset_time_idx
    ON gba.eam_telemetry_readings (tenant_id, asset_id, recorded_at DESC);

CREATE TABLE gba.eam_predictive_work_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    wo_number text NOT NULL CHECK (char_length(btrim(wo_number)) BETWEEN 2 AND 48),
    asset_id uuid NOT NULL,
    rule_id uuid,
    trigger_reading_id uuid,
    trigger_kind text NOT NULL DEFAULT 'predictive_iot' CHECK (
        trigger_kind IN ('predictive_iot', 'preventive_interval', 'manual')
    ),
    priority text NOT NULL DEFAULT 'high' CHECK (
        priority IN ('low', 'normal', 'high', 'critical')
    ),
    status text NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'scheduled', 'in_progress', 'completed', 'cancelled')
    ),
    title text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 2 AND 240),
    diagnostic_summary text NOT NULL DEFAULT '' CHECK (char_length(diagnostic_summary) <= 2000),
    estimated_cost_cents bigint NOT NULL DEFAULT 0 CHECK (estimated_cost_cents >= 0),
    due_at timestamptz,
    completed_at timestamptz,
    completion_notes text NOT NULL DEFAULT '' CHECK (char_length(completion_notes) <= 2000),
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, wo_number),
    FOREIGN KEY (tenant_id, asset_id)
        REFERENCES gba.eam_assets(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, rule_id)
        REFERENCES gba.eam_maintenance_rules(tenant_id, id) ON DELETE SET NULL,
    FOREIGN KEY (tenant_id, trigger_reading_id)
        REFERENCES gba.eam_telemetry_readings(tenant_id, id) ON DELETE SET NULL
);

CREATE INDEX eam_predictive_work_orders_tenant_status_idx
    ON gba.eam_predictive_work_orders (tenant_id, status, created_at DESC);

-- ── ENABLE + FORCE ROW LEVEL SECURITY ON ALL 9 TABLES ───────────────────────

ALTER TABLE gba.mrp_materials ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.mrp_materials FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.mrp_recipes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.mrp_recipes FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.mrp_recipe_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.mrp_recipe_lines FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.mrp_production_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.mrp_production_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.mrp_material_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.mrp_material_reservations FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.eam_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.eam_assets FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.eam_maintenance_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.eam_maintenance_rules FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.eam_telemetry_readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.eam_telemetry_readings FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.eam_predictive_work_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.eam_predictive_work_orders FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mrp_materials_tenant_isolation ON gba.mrp_materials;
CREATE POLICY mrp_materials_tenant_isolation ON gba.mrp_materials
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS mrp_recipes_tenant_isolation ON gba.mrp_recipes;
CREATE POLICY mrp_recipes_tenant_isolation ON gba.mrp_recipes
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS mrp_recipe_lines_tenant_isolation ON gba.mrp_recipe_lines;
CREATE POLICY mrp_recipe_lines_tenant_isolation ON gba.mrp_recipe_lines
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS mrp_production_runs_tenant_isolation ON gba.mrp_production_runs;
CREATE POLICY mrp_production_runs_tenant_isolation ON gba.mrp_production_runs
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS mrp_material_reservations_tenant_isolation ON gba.mrp_material_reservations;
CREATE POLICY mrp_material_reservations_tenant_isolation ON gba.mrp_material_reservations
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

-- eam_assets allows tenant-scoped management OR exact IoT SHA-256 token lookup on /v1/public/iot/telemetry
DROP POLICY IF EXISTS eam_assets_tenant_isolation ON gba.eam_assets;
CREATE POLICY eam_assets_tenant_isolation ON gba.eam_assets
    FOR ALL TO gba_runtime
    USING (
        tenant_id = gba.current_tenant_id()
        OR iot_token_hash = nullif(pg_catalog.current_setting('gba.iot_token_hash', true), '')
    )
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS eam_maintenance_rules_tenant_isolation ON gba.eam_maintenance_rules;
CREATE POLICY eam_maintenance_rules_tenant_isolation ON gba.eam_maintenance_rules
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS eam_telemetry_readings_tenant_isolation ON gba.eam_telemetry_readings;
CREATE POLICY eam_telemetry_readings_tenant_isolation ON gba.eam_telemetry_readings
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS eam_predictive_work_orders_tenant_isolation ON gba.eam_predictive_work_orders;
CREATE POLICY eam_predictive_work_orders_tenant_isolation ON gba.eam_predictive_work_orders
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.mrp_materials TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.mrp_recipes TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.mrp_recipe_lines TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.mrp_production_runs TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.mrp_material_reservations TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.eam_assets TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.eam_maintenance_rules TO gba_runtime;
GRANT SELECT, INSERT, DELETE ON TABLE gba.eam_telemetry_readings TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.eam_predictive_work_orders TO gba_runtime;
