-- M4 (package M, TMS-02 and the dispatcher part of CORE-03): a carrier may grant an independent
-- dispatcher transport work by action (ADR-0031), through the cross-company delegation of
-- ADR-0017. Grant terms may now name the transport rights; fleet registration (transport.manage)
-- is never delegable. Existing grants keep their terms.
alter table gba.delegation_grants drop constraint delegation_grants_permissions_check;
alter table gba.delegation_grants add constraint delegation_grants_permissions_check check (
    cardinality(permissions) between 1 and 8
    and permissions <@ array['booking.read', 'booking.write', 'catalog.read', 'staff.read',
                             'transport.read', 'transport.plan', 'transport.assign',
                             'transport.events']
);
