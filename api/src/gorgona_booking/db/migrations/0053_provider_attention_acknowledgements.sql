-- K4b / ADR-0027, owner decisions of 2026-10-18. Forward only; no existing row is changed.
--
-- A finance user marks a decision that has no provider operation (unkeyed facts, a refund without
-- its payment) as handled, with a required note. The record is permanent and changes no money and
-- no decision; an event of an operation, or one not decided yet, takes none.

create table gba.provider_event_acknowledgements (
    tenant_id uuid not null,
    event_id uuid not null,
    note text not null check (length(btrim(note)) between 1 and 500 and note !~ '[[:cntrl:]]'),
    created_by uuid not null,
    created_at timestamptz not null default now(),
    primary key (tenant_id,event_id),
    foreign key (tenant_id,event_id) references gba.provider_event_decisions (tenant_id,event_id),
    foreign key (created_by) references gba.users (id)
);

create function gba.check_provider_acknowledgement() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    if not exists (select 1 from gba.provider_event_decisions d
        where d.tenant_id=new.tenant_id and d.event_id=new.event_id and d.operation_id is null) then
        raise exception using errcode='check_violation',
            message='only a decision without a provider operation takes an acknowledgement';
    end if;
    return new;
end;
$$;
revoke all on function gba.check_provider_acknowledgement() from public;

alter table gba.provider_event_acknowledgements enable row level security;
alter table gba.provider_event_acknowledgements force row level security;
create policy provider_event_acknowledgements_tenant on gba.provider_event_acknowledgements
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_event_acknowledgements_company on gba.provider_event_acknowledgements as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

revoke all on gba.provider_event_acknowledgements from public;
grant select on gba.provider_event_acknowledgements to gba_runtime;
grant insert (tenant_id,event_id,note,created_by) on gba.provider_event_acknowledgements
    to gba_runtime;

create trigger provider_event_acknowledgements_check before insert on gba.provider_event_acknowledgements
    for each row execute function gba.check_provider_acknowledgement();
create trigger provider_event_acknowledgements_immutable before update or delete on gba.provider_event_acknowledgements
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_event_acknowledgements_no_truncate before truncate on gba.provider_event_acknowledgements
    for each statement execute function gba.reject_provider_receipt_truncate();
