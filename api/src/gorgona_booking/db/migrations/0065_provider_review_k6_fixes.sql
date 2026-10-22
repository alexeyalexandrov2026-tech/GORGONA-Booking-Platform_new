-- K6r / ADR-0027: fixes of the independent K6 review (2026-10-22). Forward only; no row changes.
--
-- R3: the receipt worker needs only the keys of a release (company, event, round) to skip parked
-- events and to count rounds; the finance user's note and name stay out of its reach.

revoke select on gba.provider_event_releases from gba_receipt_worker;
grant select (tenant_id,event_id,round) on gba.provider_event_releases to gba_receipt_worker;
