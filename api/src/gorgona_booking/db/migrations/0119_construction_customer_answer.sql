-- O-09: a customer acceptance keeps the company and grant that authorized it.
alter table gba.delegation_grants drop constraint delegation_grants_permissions_check;
alter table gba.delegation_grants add constraint delegation_grants_permissions_check check (
    cardinality(permissions) between 1 and 9
    and permissions <@ array['booking.read','booking.write','catalog.read','staff.read',
                             'transport.read','transport.plan','transport.assign',
                             'transport.events','transport.tender','construction.customer_answer']
);

alter table gba.delegation_grants add constraint delegation_grant_company_identity
    unique (owner_tenant_id, id, servicer_tenant_id);

alter table gba.construction_contracts
    add column customer_company_id uuid references gba.tenants(id),
    add column customer_grant_id uuid,
    add foreign key (tenant_id, customer_grant_id, customer_company_id)
        references gba.delegation_grants(owner_tenant_id, id, servicer_tenant_id),
    add constraint construction_contracts_customer_proof check (
        (source = 'platform' and customer_company_id is not null and customer_grant_id is not null)
        or
        (source <> 'platform' and customer_company_id is null and customer_grant_id is null)
    ) not valid;

-- Authorization locks the active grant before applying its location scope. The foreign
-- key ties that grant to its recipient; this trigger checks the current project binding.
create function gba.guard_construction_customer_proof() returns trigger language plpgsql as $$
begin
    if new.source = 'platform' and (
        new.recorded_by is distinct from gba.current_user_id()
        or not exists (
            select 1
            from gba.construction_projects p
            join lateral (
                select b.customer_id, b.customer_generation, b.company_id
                from gba.construction_customer_companies b
                where (b.tenant_id, b.project_id) = (p.tenant_id, p.id)
                order by b.revision desc limit 1
            ) binding on (binding.customer_id, binding.customer_generation) =
                         (p.customer_id, p.customer_generation)
            where (p.tenant_id, p.id) = (new.tenant_id, new.project_id)
                and binding.company_id = new.customer_company_id
        )
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_customer_proof_scope',
            message = 'Customer grant does not authorize this project';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_customer_proof() from public;
create trigger construction_contracts_customer_proof_guard
    before insert on gba.construction_contracts
    for each row execute function gba.guard_construction_customer_proof();
