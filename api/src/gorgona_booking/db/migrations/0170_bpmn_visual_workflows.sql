-- 0170_bpmn_visual_workflows.sql
-- AMARKAL v2.33.0: Low-Code / No-Code Visual BPMN Workflow & Approval Chain Engine.
-- Safe deterministic DAG execution, human approval gates ($0.00 HITL guardrail),
-- read-only AI compliance checks, and OMG BPMN 2.0 XML export.
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY, no elevated definer functions.

CREATE TABLE gba.bpmn_workflows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    workflow_code text NOT NULL CHECK (workflow_code ~ '^[a-z0-9][a-z0-9_-]{2,62}$'),
    display_name text NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 2 AND 120),
    description text NOT NULL DEFAULT '' CHECK (char_length(description) <= 500),
    trigger_entity text NOT NULL DEFAULT 'contract' CHECK (
        trigger_entity IN (
            'contract',
            'purchase_order',
            'quote',
            'invoice',
            'payroll_run',
            'intercompany_trade',
            'work_order'
        )
    ),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    status text NOT NULL DEFAULT 'active' CHECK (
        status IN ('draft', 'active', 'paused', 'archived')
    ),
    nodes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    edges_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, workflow_code)
);

CREATE INDEX bpmn_workflows_tenant_status_idx
    ON gba.bpmn_workflows (tenant_id, status, updated_at DESC);

CREATE TABLE gba.bpmn_workflow_instances (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    workflow_id uuid NOT NULL REFERENCES gba.bpmn_workflows(id) ON DELETE CASCADE,
    reference_code text NOT NULL CHECK (char_length(btrim(reference_code)) BETWEEN 2 AND 80),
    entity_title text NOT NULL CHECK (char_length(btrim(entity_title)) BETWEEN 2 AND 200),
    amount_cents bigint NOT NULL DEFAULT 0 CHECK (amount_cents >= 0),
    context_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    current_node_id text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'awaiting_approval' CHECK (
        status IN ('running', 'awaiting_approval', 'approved', 'rejected', 'cancelled')
    ),
    trace_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    started_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX bpmn_workflow_instances_tenant_status_idx
    ON gba.bpmn_workflow_instances (tenant_id, status, updated_at DESC);

-- ── ENABLE + FORCE ROW LEVEL SECURITY ON BOTH TABLES ─────────────────────────

ALTER TABLE gba.bpmn_workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.bpmn_workflows FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.bpmn_workflow_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.bpmn_workflow_instances FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS bpmn_workflows_tenant_isolation ON gba.bpmn_workflows;
CREATE POLICY bpmn_workflows_tenant_isolation
    ON gba.bpmn_workflows
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS bpmn_workflow_instances_tenant_isolation ON gba.bpmn_workflow_instances;
CREATE POLICY bpmn_workflow_instances_tenant_isolation
    ON gba.bpmn_workflow_instances
    FOR ALL TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.bpmn_workflows TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.bpmn_workflow_instances TO gba_runtime;
