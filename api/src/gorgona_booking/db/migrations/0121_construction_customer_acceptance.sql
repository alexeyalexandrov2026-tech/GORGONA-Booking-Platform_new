-- O-09: customer work acceptance retains the grant and the reviewed scope fingerprint.
alter table gba.construction_acceptances
    add column customer_company_id uuid references gba.tenants(id),
    add column customer_grant_id uuid,
    add column customer_review_hash text,
    add foreign key (tenant_id, customer_grant_id, customer_company_id)
        references gba.delegation_grants(owner_tenant_id, id, servicer_tenant_id),
    add constraint construction_acceptance_customer_proof check (
        (source = 'platform' and customer_company_id is not null and customer_grant_id is not null
            and customer_review_hash is not null and customer_review_hash ~ '^[0-9a-f]{64}$')
        or
        (source <> 'platform' and customer_company_id is null and customer_grant_id is null
            and customer_review_hash is null)
    ) not valid;

create function gba.guard_construction_acceptance_customer_proof() returns trigger
language plpgsql as $$
begin
    -- The ordinary acceptance guard locks the project before checking completion,
    -- quality and billing. The API locks the active grant before the project.
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
            constraint = 'construction_acceptance_customer_scope',
            message = 'Customer grant does not authorize this project';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_acceptance_customer_proof() from public;
create trigger construction_acceptances_proof_guard
    before insert on gba.construction_acceptances
    for each row execute function gba.guard_construction_acceptance_customer_proof();
