-- K5b, K5a review findings 6 and 9 (ADR-0027): the inbox of one connection and its writers.
--
-- 6: the operation list, the state reads and the link check look up the events of one
-- connection; an index on (tenant_id, connection_id) replaces the scan of every event of the
-- company. 9 (IR-03): only the receipt writer records events and deliveries; the runtime keeps
-- reading them. No row is changed.

create index provider_event_inbox_connection on gba.provider_event_inbox (tenant_id, connection_id);

revoke insert (tenant_id,id,connection_id,facts) on gba.provider_event_inbox from gba_runtime;
revoke insert (tenant_id,event_id,delivery_sha256,facts) on gba.provider_event_deliveries from gba_runtime;
