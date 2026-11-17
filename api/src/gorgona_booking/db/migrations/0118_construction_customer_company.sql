-- O-09: a project's active customer-company binding is specific to that customer assignment.
alter table gba.construction_projects add column customer_generation bigint not null default 1;

create function gba.track_construction_customer_generation() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        new.customer_generation := 1;
    elsif new.customer_id is distinct from old.customer_id then
        new.customer_generation := old.customer_generation + 1;
    end if;
    return new;
end;
$$;
revoke all on function gba.track_construction_customer_generation() from public;
create trigger construction_projects_customer_generation
    before insert or update of customer_id on gba.construction_projects
    for each row execute function gba.track_construction_customer_generation();

create table gba.construction_customer_companies (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    revision integer not null check (revision > 0),
    customer_id uuid not null,
    customer_generation bigint not null check (customer_generation > 0),
    company_id uuid references gba.tenants(id),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, revision),
    foreign key (tenant_id, project_id) references gba.construction_projects(tenant_id, id),
    foreign key (tenant_id, customer_id) references gba.counterparties(tenant_id, id),
    constraint construction_customer_company_separate check (company_id <> tenant_id)
);

create function gba.guard_construction_customer_company() returns trigger language plpgsql as $$
declare
    active_customer uuid;
    active_generation bigint;
begin
    select customer_id, customer_generation into active_customer, active_generation
    from gba.construction_projects
    where tenant_id = new.tenant_id and id = new.project_id for update;
    if (active_customer, active_generation) is distinct from
       (new.customer_id, new.customer_generation) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_customer_company_current',
            message = 'The customer assignment changed';
    end if;
    if new.revision <> coalesce((
        select max(revision) from gba.construction_customer_companies
        where tenant_id = new.tenant_id and project_id = new.project_id
    ), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_customer_company_revision',
            message = 'The company binding revision changed';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_customer_company() from public;
create trigger construction_customer_company_guard
    before insert on gba.construction_customer_companies
    for each row execute function gba.guard_construction_customer_company();
create trigger construction_customer_company_module_gate
    before insert on gba.construction_customer_companies
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_customer_companies enable row level security;
alter table gba.construction_customer_companies force row level security;
create policy construction_customer_company_tenant on gba.construction_customer_companies
    using (
        tenant_id = gba.current_tenant_id()
        and exists (
            select 1 from gba.construction_projects p
            where p.tenant_id = construction_customer_companies.tenant_id
              and p.id = construction_customer_companies.project_id
        )
    )
    with check (tenant_id = gba.current_tenant_id() and gba.current_location_id() is null);
grant select on gba.construction_customer_companies to gba_runtime;
grant insert (tenant_id, project_id, revision, customer_id, customer_generation, company_id, created_by)
    on gba.construction_customer_companies to gba_runtime;
