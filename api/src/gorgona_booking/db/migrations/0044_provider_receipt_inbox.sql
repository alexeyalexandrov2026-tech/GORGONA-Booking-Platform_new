-- K1b: receipt-only storage. No operational admission, public routing, HTTP caller,
-- worker or financial authority. Connections are provisioned only by the owner;
-- runtime may revoke them permanently. No credential or raw provider body is stored.

create function gba.provider_receipt_integer(value jsonb, maximum numeric) returns boolean
language sql immutable parallel safe set search_path=pg_catalog as $$
    select case when jsonb_typeof(value)='number'
        then (value #>> '{}') ~ '^(0|[1-9][0-9]*)$'
             and (value #>> '{}')::numeric between 0 and maximum
        else false end
$$;
revoke all on function gba.provider_receipt_integer(jsonb,numeric) from public;
grant execute on function gba.provider_receipt_integer(jsonb,numeric) to gba_runtime;

create function gba.provider_receipt_facts_valid(f jsonb) returns boolean
language plpgsql immutable parallel safe set search_path=pg_catalog as $$
declare
    r jsonb := f->'resource';
    keys text[] := array['schema_version','provider','format','verification','namespace',
        'account_id','livemode','api_version','event_id','event_type','created','resource'];
    resource_keys text[];
    valid boolean;
begin
    if jsonb_typeof(f) is distinct from 'object'
       or jsonb_typeof(r) is distinct from 'object' then return false; end if;
    valid := f ?& keys and f-keys='{}'::jsonb
        and f->'schema_version'='1'::jsonb
        and f->'provider'='"stripe_connect"'::jsonb
        and f->'format'='"snapshot"'::jsonb
        and f->'verification'='"signature_only"'::jsonb
        and f->'livemode'='false'::jsonb
        and jsonb_typeof(f->'namespace')='string'
        and f->>'namespace' ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$'
        and jsonb_typeof(f->'account_id')='string'
        and f->>'account_id' ~ '^acct_[A-Za-z0-9]{1,100}$'
        and jsonb_typeof(f->'api_version')='string'
        and f->>'api_version' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[a-z][a-z0-9-]{0,39}$'
        and jsonb_typeof(f->'event_id')='string'
        and f->>'event_id' ~ '^evt_[A-Za-z0-9]{1,100}$'
        and gba.provider_receipt_integer(f->'created',253402300799)
        and jsonb_typeof(r->'currency')='string'
        and r->>'currency' ~ '^[a-z]{3}$'
        and gba.provider_receipt_integer(r->'amount_minor',999999999999999999);
    if r->>'object'='payment_intent' then
        resource_keys := array['object','id','amount_minor','amount_received_minor','currency','status'];
        valid := valid and f->>'event_type' in ('payment_intent.succeeded',
            'payment_intent.payment_failed','payment_intent.processing','payment_intent.canceled')
            and jsonb_typeof(r->'id')='string' and r->>'id' ~ '^pi_[A-Za-z0-9]{1,100}$'
            and gba.provider_receipt_integer(r->'amount_received_minor',999999999999999999)
            and r->>'status' in ('requires_payment_method','requires_confirmation','requires_action',
                'processing','requires_capture','canceled','succeeded');
    elsif r->>'object'='charge' then
        resource_keys := array['object','id','payment_intent_id','amount_minor','amount_refunded_minor',
            'currency','status','paid','captured','refunded'];
        valid := valid and f->>'event_type' in ('charge.succeeded','charge.failed','charge.pending','charge.refunded')
            and jsonb_typeof(r->'id')='string' and r->>'id' ~ '^ch_[A-Za-z0-9]{1,100}$'
            and gba.provider_receipt_integer(r->'amount_refunded_minor',999999999999999999)
            and r->>'status' in ('succeeded','pending','failed')
            and jsonb_typeof(r->'paid')='boolean' and jsonb_typeof(r->'captured')='boolean'
            and jsonb_typeof(r->'refunded')='boolean';
    elsif r->>'object'='refund' then
        resource_keys := array['object','id','charge_id','payment_intent_id','amount_minor','currency','status'];
        valid := valid and f->>'event_type' in ('refund.created','refund.updated','refund.failed')
            and jsonb_typeof(r->'id')='string' and r->>'id' ~ '^re_[A-Za-z0-9]{1,100}$'
            and jsonb_typeof(r->'charge_id')='string' and r->>'charge_id' ~ '^ch_[A-Za-z0-9]{1,100}$'
            and r->>'status' in ('pending','requires_action','succeeded','failed','canceled');
    else return false;
    end if;
    if r->>'object' in ('charge','refund') then
        valid := valid and (r->'payment_intent_id'='null'::jsonb or (
            jsonb_typeof(r->'payment_intent_id')='string'
            and r->>'payment_intent_id' ~ '^pi_[A-Za-z0-9]{1,100}$'));
    end if;
    return coalesce(valid and r ?& resource_keys and r-resource_keys='{}'::jsonb,false);
end;
$$;
revoke all on function gba.provider_receipt_facts_valid(jsonb) from public;
grant execute on function gba.provider_receipt_facts_valid(jsonb) to gba_runtime;

create table gba.provider_receipt_connections (
    tenant_id uuid not null,
    id uuid not null,
    book_id uuid not null,
    namespace text not null check (namespace ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$'),
    account_id text not null check (account_id ~ '^acct_[A-Za-z0-9]{1,100}$'),
    api_version text not null check (api_version ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[a-z][a-z0-9-]{0,39}$'),
    admission text not null default 'not_admitted' check (admission='not_admitted'),
    livemode boolean not null default false check (not livemode),
    revoked boolean not null default false,
    created_at timestamptz not null default now(),
    primary key (tenant_id,id),
    unique (namespace,account_id),
    foreign key (tenant_id,book_id) references gba.ledger_books (tenant_id,id)
);

create table gba.provider_event_inbox (
    tenant_id uuid not null,
    id uuid not null,
    connection_id uuid not null,
    facts jsonb not null check (gba.provider_receipt_facts_valid(facts)),
    namespace text generated always as (facts->>'namespace') stored,
    account_id text generated always as (facts->>'account_id') stored,
    provider_event_id text generated always as (facts->>'event_id') stored,
    received_at timestamptz not null default now(),
    primary key (tenant_id,id),
    unique (namespace,account_id,provider_event_id),
    foreign key (tenant_id,connection_id) references gba.provider_receipt_connections (tenant_id,id)
);

create table gba.provider_event_deliveries (
    tenant_id uuid not null,
    event_id uuid not null,
    delivery_sha256 text not null check (delivery_sha256 ~ '^[0-9a-f]{64}$'),
    facts jsonb not null check (gba.provider_receipt_facts_valid(facts)),
    matches_original boolean not null,
    received_at timestamptz not null default now(),
    primary key (tenant_id,event_id,delivery_sha256),
    foreign key (tenant_id,event_id) references gba.provider_event_inbox (tenant_id,id)
);

create function gba.guard_provider_receipt_connection() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    if tg_op='DELETE' or (to_jsonb(new)-'revoked') is distinct from (to_jsonb(old)-'revoked')
       or (old.revoked and not new.revoked) then
        raise exception using errcode='check_violation', message='receipt connection identity and revocation are permanent';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_provider_receipt_connection() from public;

create function gba.check_provider_receipt() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    binding gba.provider_receipt_connections%rowtype;
    original gba.provider_event_inbox%rowtype;
    binding_id uuid;
begin
    if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
        raise exception using errcode='check_violation', message='receipt requires company scope';
    end if;
    if not gba.provider_receipt_facts_valid(new.facts) then
        raise exception using errcode='check_violation', message='receipt facts are invalid';
    end if;
    if tg_table_name='provider_event_inbox' then
        binding_id := new.connection_id;
    else
        select * into original from gba.provider_event_inbox where tenant_id=new.tenant_id and id=new.event_id;
        binding_id := original.connection_id;
    end if;
    select * into binding from gba.provider_receipt_connections
        where tenant_id=new.tenant_id and id=binding_id for share;
    if not found or binding.revoked or binding.namespace<>new.facts->>'namespace'
        or binding.account_id<>new.facts->>'account_id' or binding.api_version<>new.facts->>'api_version' then
        raise exception using errcode='check_violation', message='receipt connection refused';
    end if;
    if tg_table_name='provider_event_deliveries' then
        if original.provider_event_id<>new.facts->>'event_id' then
            raise exception using errcode='check_violation', message='receipt event identity refused';
        end if;
        new.matches_original := original.facts=new.facts;
    end if;
    return new;
end;
$$;
revoke all on function gba.check_provider_receipt() from public;

create function gba.provider_receipt_has_delivery() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    -- Fail closed if transaction context changed before deferred execution (J/H1 precedent).
    if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null
        or not exists (select 1 from gba.provider_event_deliveries d
            where d.tenant_id=new.tenant_id and d.event_id=new.id and d.facts=new.facts and d.matches_original) then
        raise exception using errcode='check_violation', message='event requires its original delivery';
    end if;
    return null;
end;
$$;
revoke all on function gba.provider_receipt_has_delivery() from public;

alter table gba.provider_receipt_connections enable row level security;
alter table gba.provider_receipt_connections force row level security;
alter table gba.provider_event_inbox enable row level security;
alter table gba.provider_event_inbox force row level security;
alter table gba.provider_event_deliveries enable row level security;
alter table gba.provider_event_deliveries force row level security;
create policy provider_receipt_connections_tenant on gba.provider_receipt_connections
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_event_inbox_tenant on gba.provider_event_inbox
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_event_deliveries_tenant on gba.provider_event_deliveries
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_receipt_connections_company on gba.provider_receipt_connections as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_event_inbox_company on gba.provider_event_inbox as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_event_deliveries_company on gba.provider_event_deliveries as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
revoke all on gba.provider_receipt_connections,gba.provider_event_inbox,gba.provider_event_deliveries from public;
grant select on gba.provider_receipt_connections,gba.provider_event_inbox,gba.provider_event_deliveries to gba_runtime;
-- UPDATE on one column also permits SELECT FOR SHARE. The trigger only permits revocation.
grant update (revoked) on gba.provider_receipt_connections to gba_runtime;
grant insert (tenant_id,id,connection_id,facts) on gba.provider_event_inbox to gba_runtime;
grant insert (tenant_id,event_id,delivery_sha256,facts) on gba.provider_event_deliveries to gba_runtime;
create trigger provider_receipt_connections_identity before update or delete on gba.provider_receipt_connections
    for each row execute function gba.guard_provider_receipt_connection();
create trigger provider_event_inbox_immutable before update or delete on gba.provider_event_inbox
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_event_deliveries_immutable before update or delete on gba.provider_event_deliveries
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_event_inbox_check before insert on gba.provider_event_inbox
    for each row execute function gba.check_provider_receipt();
create trigger provider_event_deliveries_check before insert on gba.provider_event_deliveries
    for each row execute function gba.check_provider_receipt();
create constraint trigger provider_event_inbox_complete after insert on gba.provider_event_inbox
    deferrable initially deferred for each row execute function gba.provider_receipt_has_delivery();
