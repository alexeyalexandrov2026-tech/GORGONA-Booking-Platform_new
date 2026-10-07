-- Corrections to the H3 settlement guards after their own review (0025 is published
-- in draft PR17 and stays unchanged). Forward only; both functions keep their names,
-- signatures and grants.
-- F1 Invisible characters are removed before NFKC, not after: between a letter and its
--    combining mark a zero-width character blocks composition, so removing it later
--    left a decomposed form that never matched the precomposed reference.
-- F3 "Today" for a business with locations in several zones is the latest local date
--    among them, not UTC: no location's legitimate today is refused, and a date after
--    every location's today still is.

-- The comparison form of a source account alias or an external reference: invisible
-- (default-ignorable) code points removed, then NFKC, Unicode lowercase and NFKC again
-- (lowercasing may leave a composable pair), ends trimmed. No visible code point
-- normalizes to an invisible one, so one removal is enough. Interior whitespace still
-- follows the source's rule and 'preserve' is still the only rule.
create or replace function gba.external_identity_key(value text, whitespace_rule text) returns text
    language plpgsql as $$
begin
    if whitespace_rule is distinct from 'preserve' then
        raise exception using errcode = 'invalid_parameter_value',
            message = 'unknown external identity whitespace rule';
    end if;
    return btrim(normalize(lower(normalize(regexp_replace(value,
        '[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u202a-\u202e'
        '\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufff8'
        '\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0000-\U000e0fff]', '', 'g'),
        NFKC) collate "pg_c_utf8"), NFKC));
end;
$$;

-- The IANA time zone that decides "today" for a business: of the zones of its
-- locations (each validated and governed by the confirmed timezone fact), the one whose
-- local date is the latest, ties by name. A ledger book has no zone of its own and an
-- attestation has no provider zone. A session that sees fewer locations (location
-- scope) can only get an earlier or equal date, never a later one. With no location no
-- zone is authoritative and UTC is the documented fallback.
create or replace function gba.business_timezone(tenant uuid) returns text language plpgsql as $$
declare zone text;
begin
    select l.timezone into zone from gba.locations l
        where l.tenant_id = tenant
        order by (pg_catalog.now() at time zone l.timezone)::date desc, l.timezone
        limit 1;
    return coalesce(zone, 'UTC');
end;
$$;
