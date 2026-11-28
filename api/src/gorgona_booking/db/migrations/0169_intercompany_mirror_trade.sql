-- 0169_intercompany_mirror_trade.sql
-- AMARKAL v2.32.0: Automated Intercompany Mirror Trade (Sales Order <-> Mirror Purchase Order),
-- OECD Transfer Pricing, Unrealized Profit in Ending Inventory (UPII) & Auto-Elimination.
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, no elevated definer functions.

CREATE TABLE gba.intercompany_trade_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    sales_order_number text NOT NULL CHECK (char_length(btrim(sales_order_number)) BETWEEN 4 AND 48),
    mirror_po_number text NOT NULL CHECK (char_length(btrim(mirror_po_number)) BETWEEN 4 AND 48),
    period_key text NOT NULL CHECK (period_key ~ '^[0-9]{4}-[0-9]{2}$'),
    order_date date NOT NULL DEFAULT CURRENT_DATE,
    seller_subsidiary_id uuid NOT NULL,
    buyer_subsidiary_id uuid NOT NULL,
    trade_kind text NOT NULL DEFAULT 'raw_materials' CHECK (
        trade_kind IN ('raw_materials', 'finished_goods', 'intercompany_service', 'equipment_transfer')
    ),
    transfer_pricing_method text NOT NULL DEFAULT 'cost_plus' CHECK (
        transfer_pricing_method IN ('cup_market', 'cost_plus', 'resale_minus', 'agreed_contract')
    ),
    item_sku text NOT NULL DEFAULT '' CHECK (char_length(item_sku) <= 64),
    item_description text NOT NULL CHECK (char_length(btrim(item_description)) BETWEEN 2 AND 240),
    quantity_milli bigint NOT NULL DEFAULT 1000 CHECK (quantity_milli >= 1),
    currency text NOT NULL DEFAULT 'USD' CHECK (
        currency IN ('USD', 'EUR', 'GBP', 'CAD', 'MXN', 'CHF', 'AUD', 'JPY')
    ),
    unit_transfer_price_minor bigint NOT NULL CHECK (unit_transfer_price_minor >= 1),
    seller_unit_cost_minor bigint NOT NULL DEFAULT 0 CHECK (seller_unit_cost_minor >= 0),
    total_transfer_minor bigint NOT NULL CHECK (total_transfer_minor >= 1),
    total_seller_cost_minor bigint NOT NULL DEFAULT 0 CHECK (total_seller_cost_minor >= 0),
    intercompany_profit_minor bigint NOT NULL DEFAULT 0,
    buyer_unsold_inventory_bps integer NOT NULL DEFAULT 0 CHECK (
        buyer_unsold_inventory_bps BETWEEN 0 AND 10000
    ),
    fx_rate_micros bigint NOT NULL DEFAULT 1000000 CHECK (fx_rate_micros >= 1),
    transfer_usd_cents bigint NOT NULL CHECK (transfer_usd_cents >= 1),
    upii_usd_cents bigint NOT NULL DEFAULT 0 CHECK (upii_usd_cents >= 0),
    status text NOT NULL DEFAULT 'mirrored_open' CHECK (
        status IN ('mirrored_open', 'shipped_received', 'invoiced_eliminated', 'void')
    ),
    linked_intercompany_tx_id uuid REFERENCES gba.intercompany_transactions(id) ON DELETE SET NULL,
    notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 500),
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (seller_subsidiary_id <> buyer_subsidiary_id),
    UNIQUE (tenant_id, sales_order_number),
    UNIQUE (tenant_id, mirror_po_number),
    FOREIGN KEY (tenant_id, seller_subsidiary_id)
        REFERENCES gba.holding_subsidiaries(tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, buyer_subsidiary_id)
        REFERENCES gba.holding_subsidiaries(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX intercompany_trade_orders_tenant_period_idx
    ON gba.intercompany_trade_orders (tenant_id, period_key, status, order_date DESC);

-- ── ENABLE + FORCE ROW LEVEL SECURITY ────────────────────────────────────────

ALTER TABLE gba.intercompany_trade_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.intercompany_trade_orders FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS intercompany_trade_orders_tenant_isolation ON gba.intercompany_trade_orders;
CREATE POLICY intercompany_trade_orders_tenant_isolation
    ON gba.intercompany_trade_orders
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.intercompany_trade_orders TO gba_runtime;
