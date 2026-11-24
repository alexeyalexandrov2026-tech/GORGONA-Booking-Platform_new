-- 0149_audit_events_rls_index: replace non-indexable IS NOT DISTINCT FROM predicate
-- on gba.audit_events RLS policy with an index-friendly equivalent predicate and a
-- partial index for platform-scoped (tenant_id IS NULL) audit events.
--
-- Semantics are strictly identical to 0004_identity.sql:
--   * When gba.current_tenant_id() is set: matches rows where tenant_id = gba.current_tenant_id()
--     using audit_events_tenant_time_idx (Index Scan instead of full-table Seq Scan).
--   * When gba.current_tenant_id() is NULL: matches only platform rows where tenant_id IS NULL
--     using audit_events_platform_time_idx.
-- Invoker-only; FORCE ROW LEVEL SECURITY stays active.

drop policy audit_events_scope on gba.audit_events;

create policy audit_events_scope on gba.audit_events
    using (
        tenant_id = gba.current_tenant_id()
        or (tenant_id is null and gba.current_tenant_id() is null)
    )
    with check (
        tenant_id = gba.current_tenant_id()
        or (tenant_id is null and gba.current_tenant_id() is null)
    );

create index audit_events_platform_time_idx
    on gba.audit_events (occurred_at)
    where tenant_id is null;
