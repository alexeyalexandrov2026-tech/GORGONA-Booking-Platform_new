-- H4: an insert-only registry of manually declared admission requests.
-- No gateway, credential, network, journal, approval or operational capability.
-- All existing financial facts and published migration checksums remain intact.
do $$
begin
    if not exists (select 1 from public.gba_schema_migrations where version=30
        and checksum='e68611d3ef292f84257b0ed4b9c323cb33284c8f8786838d3ffe928b08a6cf4e')
       or pg_catalog.to_regprocedure('gba.lock_ledger(uuid)') is null
       or pg_catalog.to_regprocedure('gba.reject_ledger_mutation()') is null
       or not exists (select 1 from pg_catalog.pg_class
            where oid=pg_catalog.to_regclass('gba.ledger_books') and relkind='r'
              and relrowsecurity and relforcerowsecurity)
       or not exists (select 1 from pg_catalog.pg_class
            where oid=pg_catalog.to_regclass('gba.ledger_book_versions') and relkind='r'
              and relrowsecurity and relforcerowsecurity) then
        raise exception using errcode='check_violation',
            message='0031 preflight: the approved 0030 ledger baseline is required';
    end if;
end;
$$;

create function gba.admission_safe_text(value text, maximum integer) returns boolean
    language sql immutable parallel safe as $$
select value is null or (
    length(value) between 1 and maximum and value=btrim(value)
    and value !~ '[[:cntrl:]]'
    -- Match Python Unicode whitespace even under a PostgreSQL C locale.
    and value !~* '((^|[^A-Za-z0-9_])((sk|pk|rk)_|whsec_)|Bearer[[:space:]\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|-----BEGIN[ -]|(password|secret|token|api[_ -]?key|authorization)[[:space:]\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*[:=]|://[^/@[:space:]\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+:[^/@[:space:]\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+@)'
)
$$;
revoke all on function gba.admission_safe_text(text,integer) from public;
grant execute on function gba.admission_safe_text(text,integer) to gba_runtime;

create table gba.provider_admission_requests (
    tenant_id uuid not null,
    book_id uuid not null,
    id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id,book_id,id),
    foreign key (tenant_id,book_id) references gba.ledger_books(tenant_id,id)
);
create table gba.provider_admission_versions (
    tenant_id uuid not null,
    book_id uuid not null,
    request_id uuid not null,
    revision integer not null constraint provider_admission_versions_revision_check check (revision>0),
    state text not null constraint provider_admission_versions_state_check check (state in ('draft','submitted','withdrawn')),
    provider text not null constraint provider_admission_versions_provider_check check (provider='stripe_connect'),
    country text not null constraint provider_admission_versions_country_check check (country ~ '^[A-Z]{2}$'),
    business_activity text not null constraint provider_admission_versions_activity_check check (gba.admission_safe_text(business_activity,500)),
    requested_operation text not null constraint provider_admission_versions_operation_check check (requested_operation in ('charge','refund','transfer','payout')),
    assessment text not null constraint provider_admission_versions_assessment_check check (assessment in ('not_checked','suspended','unsupported')),
    account_reference text constraint provider_admission_versions_account_check check (gba.admission_safe_text(account_reference,160)),
    notes text constraint provider_admission_versions_notes_check check (gba.admission_safe_text(notes,2000)),
    evidence_count smallint not null constraint provider_admission_versions_evidence_count_check check (evidence_count between 0 and 8),
    evidence_status text not null default 'manually_provided_unverified' constraint provider_admission_versions_evidence_status_check check (evidence_status='manually_provided_unverified'),
    charge_enabled boolean not null default false constraint provider_admission_versions_charge_check check (not charge_enabled),
    refund_enabled boolean not null default false constraint provider_admission_versions_refund_check check (not refund_enabled),
    transfer_enabled boolean not null default false constraint provider_admission_versions_transfer_check check (not transfer_enabled),
    payout_enabled boolean not null default false constraint provider_admission_versions_payout_check check (not payout_enabled),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    constraint provider_admission_versions_account_format_check check (account_reference ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$'),
    primary key (tenant_id,book_id,request_id,revision),
    foreign key (tenant_id,book_id,request_id) references gba.provider_admission_requests(tenant_id,book_id,id)
);
create table gba.provider_admission_evidence (
    tenant_id uuid not null,
    book_id uuid not null,
    request_id uuid not null,
    revision integer not null,
    reference_no smallint not null constraint provider_admission_evidence_number_check check (reference_no between 1 and 8),
    reference text not null constraint provider_admission_evidence_reference_check check (gba.admission_safe_text(reference,256)),
    primary key (tenant_id,book_id,request_id,revision,reference_no),
    unique (tenant_id,book_id,request_id,revision,reference),
    foreign key (tenant_id,book_id,request_id,revision) references gba.provider_admission_versions(tenant_id,book_id,request_id,revision)
);
create table gba.provider_admission_receipts (
    tenant_id uuid not null,
    actor_key text not null,
    operation text not null constraint provider_admission_receipts_operation_check check (operation in ('admission_draft','admission_submit','admission_withdraw')),
    idempotency_key text not null constraint provider_admission_receipts_key_check check (idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'),
    request_hash text not null constraint provider_admission_receipts_hash_check check (request_hash ~ '^[0-9a-f]{64}$'),
    book_id uuid not null,
    request_id uuid not null,
    revision integer not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    constraint provider_admission_receipts_actor_check check (actor_key='user:'||created_by::text),
    primary key (tenant_id,actor_key,operation,idempotency_key),
    foreign key (tenant_id,book_id,request_id,revision) references gba.provider_admission_versions(tenant_id,book_id,request_id,revision)
);
create table gba.provider_admission_cancellations (
    tenant_id uuid not null,
    actor_key text not null,
    operation text not null constraint provider_admission_cancellations_operation_check check (operation in ('admission_draft','admission_submit','admission_withdraw')),
    idempotency_key text not null constraint provider_admission_cancellations_key_check check (idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'),
    book_id uuid not null,
    request_id uuid not null,
    revision integer not null constraint provider_admission_cancellations_revision_check check (revision>=1 and (operation='admission_draft' or revision>=2)),
    cancelled_by uuid not null references gba.users(id),
    cancelled_at timestamptz not null default now(),
    constraint provider_admission_cancellations_actor_check check (actor_key='user:'||cancelled_by::text),
    primary key (tenant_id,actor_key,operation,idempotency_key),
    foreign key (tenant_id,book_id) references gba.ledger_books(tenant_id,id)
);

create function gba.lock_admission_record() returns trigger language plpgsql as $$
begin
    perform gba.lock_ledger(new.tenant_id);
    return new;
end;
$$;
revoke all on function gba.lock_admission_record() from public;

-- The shared optional-module guard is attached directly with its finance argument
-- below; no duplicate module function or new enableable module is introduced.

create function gba.enforce_admission_version() returns trigger language plpgsql as $$
declare
    parent gba.provider_admission_requests%rowtype;
    previous gba.provider_admission_versions%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into parent from gba.provider_admission_requests
      where tenant_id=new.tenant_id and book_id=new.book_id and id=new.request_id;
    if not found then
        raise exception using errcode='foreign_key_violation', message='admission request belongs to this company and book';
    end if;
    if new.created_transaction<>pg_catalog.pg_current_xact_id() or new.created_at<>pg_catalog.now() then
        raise exception using errcode='check_violation', message='admission versions are recorded in the current transaction';
    end if;
    select * into previous from gba.provider_admission_versions
      where tenant_id=new.tenant_id and book_id=new.book_id and request_id=new.request_id
      order by revision desc limit 1;
    if not found then
        if new.revision<>1 or new.state<>'draft'
           or parent.created_transaction<>pg_catalog.pg_current_xact_id() then
            raise exception using errcode='check_violation', message='a new admission request starts with its own draft';
        end if;
    else
        if new.revision<>previous.revision+1 or previous.state='withdrawn'
           or (new.state='draft' and previous.state<>'draft')
           or (new.state='submitted' and previous.state<>'draft') then
            raise exception using errcode='check_violation', message='invalid admission revision or transition';
        end if;
        if new.state<>'draft' and (new.provider,new.country,new.business_activity,new.requested_operation,
             new.assessment,new.account_reference,new.notes,new.evidence_count)
            is distinct from (previous.provider,previous.country,previous.business_activity,previous.requested_operation,
             previous.assessment,previous.account_reference,previous.notes,previous.evidence_count) then
            raise exception using errcode='check_violation', message='an admission transition preserves its declared metadata';
        end if;
    end if;
    if new.state='submitted' and new.evidence_count=0 then
        raise exception using errcode='check_violation', message='submission needs manually supplied unverified evidence references';
    end if;
    if new.state<>'withdrawn' then
        perform pg_catalog.pg_advisory_xact_lock_shared(pg_catalog.hashtextextended(
            'gba:business-configuration:'||new.tenant_id::text,0));
        if not exists (select 1 from gba.business_module_states s
            where s.tenant_id=new.tenant_id and s.module_id='finance' and s.enabled) then
            raise exception using errcode='GBM01', message='the finance module is disabled for this business';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_admission_version() from public;

create function gba.enforce_admission_evidence() returns trigger language plpgsql as $$
declare
    parent gba.provider_admission_versions%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into parent from gba.provider_admission_versions
      where tenant_id=new.tenant_id and book_id=new.book_id and request_id=new.request_id and revision=new.revision;
    if not found then
        raise exception using errcode='foreign_key_violation', message='evidence belongs to this admission version';
    end if;
    if parent.created_transaction<>pg_catalog.pg_current_xact_id()
       or new.reference_no>parent.evidence_count then
        raise exception using errcode='check_violation', message='evidence is inserted only with its version';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_admission_evidence() from public;

create function gba.assert_admission_consistent(target_tenant uuid,target_book uuid,target_request uuid) returns void
    language plpgsql as $$
declare
    version gba.provider_admission_versions%rowtype;
    actual_count integer;
    last_reference integer;
begin
    if not exists (select 1 from gba.provider_admission_versions
        where tenant_id=target_tenant and book_id=target_book and request_id=target_request and revision=1) then
        raise exception using errcode='check_violation', message='an admission request requires its first draft';
    end if;
    for version in select * from gba.provider_admission_versions
        where tenant_id=target_tenant and book_id=target_book and request_id=target_request order by revision loop
        select count(*),coalesce(max(reference_no),0) into actual_count,last_reference
          from gba.provider_admission_evidence
         where tenant_id=target_tenant and book_id=target_book and request_id=target_request and revision=version.revision;
        if actual_count<>version.evidence_count or last_reference<>version.evidence_count then
            raise exception using errcode='check_violation', message='admission evidence references are complete and contiguous';
        end if;
        if version.state<>'draft' and exists (
            (select reference_no,reference from gba.provider_admission_evidence
              where tenant_id=target_tenant and book_id=target_book and request_id=target_request and revision=version.revision
             except all
             select reference_no,reference from gba.provider_admission_evidence
              where tenant_id=target_tenant and book_id=target_book and request_id=target_request and revision=version.revision-1)
            union all
            (select reference_no,reference from gba.provider_admission_evidence
              where tenant_id=target_tenant and book_id=target_book and request_id=target_request and revision=version.revision-1
             except all
             select reference_no,reference from gba.provider_admission_evidence
              where tenant_id=target_tenant and book_id=target_book and request_id=target_request and revision=version.revision)
        ) then
            raise exception using errcode='check_violation', message='an admission transition preserves all evidence references';
        end if;
    end loop;
end;
$$;
revoke all on function gba.assert_admission_consistent(uuid,uuid,uuid) from public;
grant execute on function gba.assert_admission_consistent(uuid,uuid,uuid) to gba_runtime;

create function gba.check_admission_integrity() returns trigger language plpgsql as $$
begin
    if tg_table_name='provider_admission_requests' then
        perform gba.assert_admission_consistent(new.tenant_id,new.book_id,new.id);
    else
        perform gba.assert_admission_consistent(new.tenant_id,new.book_id,new.request_id);
    end if;
    return null;
end;
$$;
revoke all on function gba.check_admission_integrity() from public;

create function gba.enforce_admission_command() returns trigger language plpgsql as $$
declare
    version gba.provider_admission_versions%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    if tg_table_name='provider_admission_receipts' then
        if exists (select 1 from gba.provider_admission_cancellations c
            where c.tenant_id=new.tenant_id and c.actor_key=new.actor_key and c.operation=new.operation and c.idempotency_key=new.idempotency_key) then
            raise exception using errcode='check_violation', message='this admission command was permanently cancelled';
        end if;
        select * into version from gba.provider_admission_versions
         where tenant_id=new.tenant_id and book_id=new.book_id and request_id=new.request_id and revision=new.revision;
        if not found or version.created_transaction<>pg_catalog.pg_current_xact_id()
           or version.created_by<>new.created_by
           or version.state<>(case new.operation when 'admission_draft' then 'draft' when 'admission_submit' then 'submitted' else 'withdrawn' end) then
            raise exception using errcode='check_violation', message='an admission receipt names the version created by its command';
        end if;
    elsif exists (select 1 from gba.provider_admission_receipts r
        where r.tenant_id=new.tenant_id and r.actor_key=new.actor_key and r.operation=new.operation and r.idempotency_key=new.idempotency_key) then
        raise exception using errcode='check_violation', message='a committed admission command cannot be cancelled';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_admission_command() from public;

alter table gba.provider_admission_requests enable row level security;
alter table gba.provider_admission_requests force row level security;
alter table gba.provider_admission_versions enable row level security;
alter table gba.provider_admission_versions force row level security;
alter table gba.provider_admission_evidence enable row level security;
alter table gba.provider_admission_evidence force row level security;
alter table gba.provider_admission_receipts enable row level security;
alter table gba.provider_admission_receipts force row level security;
alter table gba.provider_admission_cancellations enable row level security;
alter table gba.provider_admission_cancellations force row level security;

create policy provider_admission_requests_tenant_isolation on gba.provider_admission_requests
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_admission_versions_tenant_isolation on gba.provider_admission_versions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_admission_evidence_tenant_isolation on gba.provider_admission_evidence
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_admission_receipts_tenant_isolation on gba.provider_admission_receipts
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_admission_cancellations_tenant_isolation on gba.provider_admission_cancellations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_admission_requests_unrestricted_scope on gba.provider_admission_requests as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_admission_versions_unrestricted_scope on gba.provider_admission_versions as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_admission_evidence_unrestricted_scope on gba.provider_admission_evidence as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_admission_receipts_unrestricted_scope on gba.provider_admission_receipts as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_admission_cancellations_unrestricted_scope on gba.provider_admission_cancellations as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

revoke all on gba.provider_admission_requests,gba.provider_admission_versions,gba.provider_admission_evidence,gba.provider_admission_receipts,gba.provider_admission_cancellations from public;
grant select on gba.provider_admission_requests,gba.provider_admission_versions,gba.provider_admission_evidence,gba.provider_admission_receipts,gba.provider_admission_cancellations to gba_runtime;
grant insert (tenant_id,book_id,id,created_by) on gba.provider_admission_requests to gba_runtime;
grant insert (tenant_id,book_id,request_id,revision,state,provider,country,business_activity,requested_operation,assessment,account_reference,notes,evidence_count,created_by) on gba.provider_admission_versions to gba_runtime;
grant insert (tenant_id,book_id,request_id,revision,reference_no,reference) on gba.provider_admission_evidence to gba_runtime;
grant insert (tenant_id,actor_key,operation,idempotency_key,request_hash,book_id,request_id,revision,created_by) on gba.provider_admission_receipts to gba_runtime;
grant insert (tenant_id,actor_key,operation,idempotency_key,book_id,request_id,revision,cancelled_by) on gba.provider_admission_cancellations to gba_runtime;

create trigger provider_admission_requests_immutable before update or delete on gba.provider_admission_requests for each row execute function gba.reject_ledger_mutation();
create trigger provider_admission_versions_immutable before update or delete on gba.provider_admission_versions for each row execute function gba.reject_ledger_mutation();
create trigger provider_admission_evidence_immutable before update or delete on gba.provider_admission_evidence for each row execute function gba.reject_ledger_mutation();
create trigger provider_admission_receipts_immutable before update or delete on gba.provider_admission_receipts for each row execute function gba.reject_ledger_mutation();
create trigger provider_admission_cancellations_immutable before update or delete on gba.provider_admission_cancellations for each row execute function gba.reject_ledger_mutation();
create trigger provider_admission_requests_lock before insert on gba.provider_admission_requests for each row execute function gba.lock_admission_record();
create trigger provider_admission_requests_require_module before insert on gba.provider_admission_requests for each row execute function gba.require_enabled_module('finance');
create trigger provider_admission_versions_next before insert on gba.provider_admission_versions for each row execute function gba.enforce_admission_version();
create trigger provider_admission_evidence_check before insert on gba.provider_admission_evidence for each row execute function gba.enforce_admission_evidence();
create trigger provider_admission_receipts_check before insert on gba.provider_admission_receipts for each row execute function gba.enforce_admission_command();
create trigger provider_admission_cancellations_check before insert on gba.provider_admission_cancellations for each row execute function gba.enforce_admission_command();
create constraint trigger provider_admission_requests_consistent after insert on gba.provider_admission_requests deferrable initially deferred for each row execute function gba.check_admission_integrity();
create constraint trigger provider_admission_versions_consistent after insert on gba.provider_admission_versions deferrable initially deferred for each row execute function gba.check_admission_integrity();
create constraint trigger provider_admission_evidence_consistent after insert on gba.provider_admission_evidence deferrable initially deferred for each row execute function gba.check_admission_integrity();
