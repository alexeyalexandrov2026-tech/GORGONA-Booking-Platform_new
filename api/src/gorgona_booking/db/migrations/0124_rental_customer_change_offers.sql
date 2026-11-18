-- RENT-01 R-09: issued, versioned customer change offers and their accepted agreement versions.
create table gba.rental_customer_change_offers (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    revision integer not null check (revision > 0),
    agreement_id uuid not null,
    agreement_version integer not null check (agreement_version > 0),
    binding_revision integer not null check (binding_revision > 0),
    company_id uuid not null references gba.tenants(id),
    quote jsonb not null check (jsonb_typeof(quote) = 'object'),
    reason text not null check (length(btrim(reason)) between 1 and 500),
    review_hash text not null check (review_hash ~ '^[0-9a-f]{64}$'),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, booking_id, revision),
    unique (tenant_id, agreement_id, revision),
    foreign key (tenant_id, booking_id) references gba.rental_bookings(tenant_id, id),
    foreign key (tenant_id, agreement_id, agreement_version)
        references gba.rental_agreement_versions(tenant_id, agreement_id, version),
    foreign key (tenant_id, booking_id, binding_revision)
        references gba.rental_customer_companies(tenant_id, booking_id, revision)
);

create function gba.guard_rental_customer_change_offer() returns trigger
language plpgsql set search_path = pg_catalog as $$
begin
    perform gba.lock_rental_booking_class(new.tenant_id, new.booking_id);
    if new.created_by is distinct from gba.current_user_id()
        or new.revision <> coalesce((
            select max(o.revision) from gba.rental_customer_change_offers o
            where (o.tenant_id, o.booking_id) = (new.tenant_id, new.booking_id)
        ), 0) + 1
        or not exists (
            select 1 from gba.rental_agreements a
            where (a.tenant_id, a.booking_id, a.id)
                = (new.tenant_id, new.booking_id, new.agreement_id)
            and new.agreement_version = (
                select max(v.version) from gba.rental_agreement_versions v
                where (v.tenant_id, v.agreement_id) = (a.tenant_id, a.id)
            )
        )
        or not exists (
            select 1 from (
                select c.revision, c.company_id from gba.rental_customer_companies c
                where (c.tenant_id, c.booking_id) = (new.tenant_id, new.booking_id)
                order by c.revision desc limit 1
            ) binding
            where (binding.revision, binding.company_id) = (new.binding_revision, new.company_id)
        )
        or exists (
            select 1 from gba.rental_settlements s
            where (s.tenant_id, s.booking_id) = (new.tenant_id, new.booking_id)
        )
        or exists (
            select 1 from gba.rental_booking_cancellations c
            where (c.tenant_id, c.booking_id) = (new.tenant_id, new.booking_id)
        )
    then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_customer_change_offer_current',
            message = 'A change offer requires the current agreement and customer binding';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_customer_change_offer() from public;
create trigger rental_customer_change_offer_guard
    before insert on gba.rental_customer_change_offers
    for each row execute function gba.guard_rental_customer_change_offer();
create trigger rental_customer_change_offer_module_gate
    before insert on gba.rental_customer_change_offers
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_customer_change_offers enable row level security;
alter table gba.rental_customer_change_offers force row level security;
create policy rental_customer_change_offers_tenant on gba.rental_customer_change_offers
    using (tenant_id = gba.current_tenant_id() and exists (
        select 1 from gba.rental_bookings b
        where (b.tenant_id, b.id) = (
            rental_customer_change_offers.tenant_id, rental_customer_change_offers.booking_id)
    ))
    with check (tenant_id = gba.current_tenant_id() and gba.current_location_id() is null);

grant select on gba.rental_customer_change_offers to gba_runtime;
grant insert (tenant_id, booking_id, revision, agreement_id, agreement_version,
    binding_revision, company_id, quote, reason, review_hash, created_by)
    on gba.rental_customer_change_offers to gba_runtime;

alter table gba.rental_agreement_versions
    add column customer_change_offer_revision integer,
    add foreign key (tenant_id, agreement_id, customer_change_offer_revision)
        references gba.rental_customer_change_offers(tenant_id, agreement_id, revision),
    drop constraint rental_agreement_customer_proof;
alter table gba.rental_agreement_versions
    add constraint rental_agreement_customer_proof check (
        (source = 'platform' and customer_company_id is not null
            and customer_grant_id is not null and customer_binding_revision > 0
            and customer_binding_revision is not null and customer_review_hash is not null
            and customer_review_hash ~ '^[0-9a-f]{64}$'
            and (
                (version = 1 and customer_change_offer_revision is null)
                or (version > 1 and customer_change_offer_revision is not null
                    and customer_change_offer_revision > 0)
            ))
        or
        (source <> 'platform' and customer_company_id is null and customer_grant_id is null
            and customer_binding_revision is null and customer_review_hash is null
            and customer_change_offer_revision is null)
    ) not valid;
create unique index rental_agreement_single_acceptance_per_offer
    on gba.rental_agreement_versions(tenant_id, agreement_id, customer_change_offer_revision)
    where customer_change_offer_revision is not null;

-- The existing customer-proof and agreement guards acquire the grant then class locks.
create function gba.guard_rental_agreement_change_offer() returns trigger
language plpgsql set search_path = pg_catalog as $$
declare
    offer record;
begin
    select o.* into offer
    from gba.rental_agreements a
    join lateral (
        select q.* from gba.rental_customer_change_offers q
        where (q.tenant_id, q.booking_id) = (a.tenant_id, a.booking_id)
        order by q.revision desc limit 1
    ) o on true
    where (a.tenant_id, a.id) = (new.tenant_id, new.agreement_id);
    if not found
        or (offer.revision, offer.agreement_id, offer.agreement_version,
            offer.binding_revision, offer.company_id, offer.reason, offer.review_hash) is distinct from
           (new.customer_change_offer_revision, new.agreement_id, new.version - 1,
            new.customer_binding_revision, new.customer_company_id, new.reason, new.customer_review_hash)
        or (offer.quote->>'rate_card_id')::uuid is distinct from new.rate_card_id
        or (offer.quote->>'starts_at')::timestamptz is distinct from new.starts_at
        or (offer.quote->>'ends_at')::timestamptz is distinct from new.ends_at
        or (offer.quote->>'total')::bigint is distinct from new.total
        or (offer.quote->>'rental')::bigint is distinct from new.rental_amount
        or (offer.quote->>'rental_days')::integer is distinct from new.rental_days
        or (offer.quote#>>'{counts,month}')::integer is distinct from new.month_count
        or (offer.quote#>>'{counts,week}')::integer is distinct from new.week_count
        or (offer.quote#>>'{counts,day}')::integer is distinct from new.day_count
        or (offer.quote#>>'{counts,hour}')::integer is distinct from new.hour_count
    then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_change_offer_scope',
            message = 'The accepted version must match the current issued rental change';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_agreement_change_offer() from public;
create trigger rental_agreement_versions_offer_guard
    before insert on gba.rental_agreement_versions for each row
    when (new.customer_change_offer_revision is not null)
    execute function gba.guard_rental_agreement_change_offer();

create function gba.verify_rental_change_offer_extras() returns trigger
language plpgsql set search_path = pg_catalog as $$
declare
    offered jsonb;
    recorded jsonb;
begin
    select coalesce(jsonb_agg(line.value order by line.value->>'code'), '[]'::jsonb)
        into offered
    from gba.rental_agreements a
    join gba.rental_customer_change_offers o on (o.tenant_id, o.booking_id, o.revision)
        = (a.tenant_id, a.booking_id, new.customer_change_offer_revision)
    cross join lateral jsonb_array_elements(o.quote->'extras') line(value)
    where (a.tenant_id, a.id) = (new.tenant_id, new.agreement_id);

    select coalesce(jsonb_agg(
        jsonb_build_object('code', e.code, 'quantity', e.quantity, 'amount', e.amount)
        order by e.code
    ), '[]'::jsonb) into recorded
    from gba.rental_agreement_version_extras e
    where (e.tenant_id, e.agreement_id, e.version)
        = (new.tenant_id, new.agreement_id, new.version);

    if offered is distinct from recorded then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_change_offer_extras_match',
            message = 'The agreement version must keep the quoted extras';
    end if;
    return new;
end;
$$;
revoke all on function gba.verify_rental_change_offer_extras() from public;
create constraint trigger rental_change_offer_extras_match
    after insert on gba.rental_agreement_versions deferrable initially deferred for each row
    when (new.customer_change_offer_revision is not null)
    execute function gba.verify_rental_change_offer_extras();
