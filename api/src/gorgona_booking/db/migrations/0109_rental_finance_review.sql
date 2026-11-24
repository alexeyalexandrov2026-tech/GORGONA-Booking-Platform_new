-- RR-05 and RR-06: voids release refund quota; linked financial drafts keep their terms.
create or replace function gba.guard_rental_refund() returns trigger language plpgsql as $$
declare
    settled record;
begin
    select b.class_id, s.total_minor, s.book_id, s.invoice_document_id into settled
    from gba.rental_bookings b
      join gba.rental_settlements s on s.tenant_id = b.tenant_id and s.booking_id = b.id
    where b.tenant_id = new.tenant_id and b.id = new.booking_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = settled.class_id for update;
    if new.number <> 1 + coalesce((select max(r.number) from gba.rental_refunds r
        where r.tenant_id = new.tenant_id and r.booking_id = new.booking_id
          and not gba.credit_voided(r.tenant_id, r.book_id, r.credit_document_id)), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_refunds_sequence_check',
            message = 'refunds are numbered 1, 2, 3 per booking';
    end if;
    if new.amount_minor + coalesce((select sum(r.amount_minor) from gba.rental_refunds r
        where r.tenant_id = new.tenant_id and r.booking_id = new.booking_id
          and not gba.credit_voided(r.tenant_id, r.book_id, r.credit_document_id)), 0)
        > settled.total_minor + coalesce((select sum(c.amount_minor) from gba.rental_damage_charges c
            where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_refunds_ceiling_check',
            message = 'refunds never exceed the settlement total plus the damage charged';
    end if;
    if new.method = 'credit' and not exists (
        select 1 from gba.financial_documents d
          join gba.financial_document_versions v
            on v.tenant_id = d.tenant_id and v.book_id = d.book_id and v.document_id = d.id
          join gba.financial_obligations o
            on o.tenant_id = v.tenant_id and o.book_id = v.book_id and o.id = v.credited_obligation_id
         where d.tenant_id = new.tenant_id and d.book_id = new.book_id
           and d.id = new.credit_document_id and d.kind = 'credit_note'
           and v.revision = (select max(x.revision) from gba.financial_document_versions x
                              where x.tenant_id = d.tenant_id and x.book_id = d.book_id
                                and x.document_id = d.id)
           and v.state in ('draft', 'issued')
           and v.principal_minor = new.amount_minor and o.source_kind = 'invoice'
           and (o.source_id = settled.invoice_document_id and o.book_id = settled.book_id
                or exists (select 1 from gba.rental_damage_charges c
                    where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id
                      and c.book_id = o.book_id and c.invoice_document_id = o.source_id))
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_refunds_document_check',
            message = 'a credit refund names a credit note of an obligation of the booking for its amount';
    end if;
    return new;
end;
$$;

create function gba.guard_rental_financial_draft() returns trigger language plpgsql as $$
begin
    if exists (
        select 1 from gba.rental_settlements s
        where s.tenant_id = new.tenant_id and s.book_id = new.book_id
          and s.invoice_document_id = new.document_id
    ) or exists (
        select 1 from gba.rental_damage_charges c
        where c.tenant_id = new.tenant_id and c.book_id = new.book_id
          and c.invoice_document_id = new.document_id
    ) or exists (
        select 1 from gba.rental_refunds r
        where r.tenant_id = new.tenant_id and r.book_id = new.book_id
          and r.credit_document_id = new.document_id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_financial_draft_linked_check',
            message = 'a linked rental draft keeps its original terms';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_financial_draft() from public;
create trigger rental_financial_draft_linked
    before insert on gba.financial_document_versions
    for each row when (new.state = 'draft' and new.revision > 1)
    execute function gba.guard_rental_financial_draft();
