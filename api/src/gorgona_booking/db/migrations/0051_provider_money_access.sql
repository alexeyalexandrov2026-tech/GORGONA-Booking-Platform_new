-- K3a (owner decisions 2026-10-17): a finance user applies an observed provider operation to a
-- reserved H settlement (migration 0052). The runtime reads its company's operations and decisions
-- and locks the operation row it applies, so a worker deciding another event of the same operation
-- waits for it. Nothing else changes for the K tables; leases stay the worker's.
grant select on gba.provider_operations,gba.provider_event_decisions to gba_runtime;
-- UPDATE on one column only permits SELECT FOR UPDATE; the immutable trigger refuses every update.
grant update (currency) on gba.provider_operations to gba_runtime;
grant execute on function gba.provider_receipt_operation(jsonb) to gba_runtime;
