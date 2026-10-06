-- Documents, immutable files and links to counterparties (ADR-0020 E2, ADR-0021 profile).
-- A file is stored once, unchanged, with a hash and size the database itself checks.
-- Document content is append-only; links to counterparties are an event log. Nothing is
-- updated or deleted. Every insert needs the documents module enabled by a published
-- configuration; a link also needs the counterparties module. Reads, history and
-- downloads continue when a module is turned off.

create table gba.document_files (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes integer not null check (size_bytes between 1 and 10485760),
    media_type text not null
        check (media_type in ('application/pdf', 'image/png', 'image/jpeg')),
    file_name text not null check (
        length(file_name) between 5 and 120
        and file_name !~ '[[:cntrl:]]'
        and translate(file_name, '<>:"/\|?*', '') = file_name
    ),
    validator_version text not null check (validator_version ~ '^[a-z0-9][a-z0-9.-]{0,63}$'),
    content bytea not null,
    uploaded_by uuid not null references gba.users (id),
    uploaded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint document_files_extension check (
        right(file_name, 4) = case media_type
            when 'application/pdf' then '.pdf' when 'image/png' then '.png' else '.jpg' end
    ),
    constraint document_files_content_size check (octet_length(content) = size_bytes),
    constraint document_files_content_hash
        check (pg_catalog.encode(pg_catalog.sha256(content), 'hex') = sha256)
);
-- Validated PDF/PNG/JPEG bytes are already compressed; keep them out of line uncompressed.
alter table gba.document_files alter column content set storage external;

create table gba.documents (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id)
);

create table gba.document_versions (
    tenant_id uuid not null,
    document_id uuid not null,
    revision integer not null check (revision > 0),
    title text not null check (
        length(btrim(title, E' \t\r\n')) between 1 and 200 and title !~ '[[:cntrl:]]'
    ),
    category text not null
        check (category in ('agreement', 'certificate', 'invoice', 'report', 'other')),
    valid_from date,
    valid_until date,
    archived boolean not null,
    file_id uuid,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, document_id, revision),
    foreign key (tenant_id, document_id) references gba.documents (tenant_id, id),
    constraint document_versions_file_fk foreign key (tenant_id, file_id)
        references gba.document_files (tenant_id, id),
    constraint document_versions_validity check (
        valid_from is null or valid_until is null or valid_until >= valid_from
    )
);
create index document_versions_file on gba.document_versions (tenant_id, file_id)
    where file_id is not null;

-- Links between a document and a counterparty, per pair:
-- linked -> unlinked -> linked ... Nothing is rewritten.
create table gba.document_counterparty_links (
    tenant_id uuid not null,
    id uuid not null default uuidv7(),
    document_id uuid not null,
    counterparty_id uuid not null,
    sequence integer not null check (sequence > 0),
    action text not null check (action in ('linked', 'unlinked')),
    decided_by uuid not null references gba.users (id),
    decided_at timestamptz not null default now(),
    primary key (tenant_id, document_id, counterparty_id, sequence),
    unique (tenant_id, id),
    constraint document_counterparty_links_document_fk foreign key (tenant_id, document_id)
        references gba.documents (tenant_id, id),
    constraint document_counterparty_links_counterparty_fk foreign key
        (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id)
);
create index document_counterparty_links_counterparty
    on gba.document_counterparty_links (tenant_id, counterparty_id, id);
create index document_counterparty_links_document
    on gba.document_counterparty_links (tenant_id, document_id, id);

alter table gba.document_files enable row level security;
alter table gba.document_files force row level security;
alter table gba.documents enable row level security;
alter table gba.documents force row level security;
alter table gba.document_versions enable row level security;
alter table gba.document_versions force row level security;
alter table gba.document_counterparty_links enable row level security;
alter table gba.document_counterparty_links force row level security;

create policy document_files_tenant_isolation on gba.document_files
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.document_files to gba_runtime;
grant insert (tenant_id, id, sha256, size_bytes, media_type, file_name, validator_version,
              content, uploaded_by)
    on gba.document_files to gba_runtime;

create policy documents_tenant_isolation on gba.documents
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.documents to gba_runtime;
grant insert (tenant_id, id, created_by) on gba.documents to gba_runtime;

create policy document_versions_tenant_isolation on gba.document_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.document_versions to gba_runtime;
grant insert (tenant_id, document_id, revision, title, category, valid_from, valid_until,
              archived, file_id, created_by)
    on gba.document_versions to gba_runtime;

create policy document_counterparty_links_tenant_isolation
    on gba.document_counterparty_links
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.document_counterparty_links to gba_runtime;
grant insert (tenant_id, document_id, counterparty_id, sequence, action, decided_by)
    on gba.document_counterparty_links to gba_runtime;

create function gba.reject_document_mutation() returns trigger language plpgsql as $$
begin
    raise exception using errcode = 'check_violation',
        message = 'document files, records and versions are kept unchanged';
end;
$$;
revoke all on function gba.reject_document_mutation() from public;
create trigger document_files_immutable before update or delete on gba.document_files
    for each row execute function gba.reject_document_mutation();
create trigger documents_immutable before update or delete on gba.documents
    for each row execute function gba.reject_document_mutation();
create trigger document_versions_immutable before update or delete on gba.document_versions
    for each row execute function gba.reject_document_mutation();

-- Revisions are contiguous: the next version is the latest plus one.
create function gba.enforce_document_version() returns trigger
    language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:documents:' || new.tenant_id::text, 0));
    if new.revision <> coalesce((
        select max(v.revision) from gba.document_versions v
        where v.tenant_id = new.tenant_id and v.document_id = new.document_id
    ), 0) + 1 then
        raise exception using errcode = 'check_violation',
            message = 'a document version follows the latest revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_document_version() from public;
create trigger document_versions_next_revision before insert on gba.document_versions
    for each row execute function gba.enforce_document_version();

-- Per document and counterparty: links alternate and the sequence advances by one.
-- A new link needs a current (not archived) document and an active counterparty card;
-- the shared counterparty lock orders it against merges and archiving.
create function gba.enforce_document_counterparty_link() returns trigger
    language plpgsql as $$
declare
    last_sequence integer;
    last_action text;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = 'check_violation',
            message = 'document link history is kept';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:documents:' || new.tenant_id::text, 0));
    perform pg_catalog.pg_advisory_xact_lock_shared(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    select l.sequence, l.action into last_sequence, last_action
      from gba.document_counterparty_links l
     where l.tenant_id = new.tenant_id and l.document_id = new.document_id
       and l.counterparty_id = new.counterparty_id
     order by l.sequence desc limit 1;
    if new.sequence <> coalesce(last_sequence, 0) + 1
       or (new.action = 'linked' and last_action = 'linked')
       or (new.action = 'unlinked' and last_action is distinct from 'linked') then
        raise exception using errcode = 'check_violation',
            message = 'invalid document link change';
    end if;
    if new.action = 'linked' and (
        not exists (
            select 1 from gba.document_versions v
            where v.tenant_id = new.tenant_id and v.document_id = new.document_id
              and not v.archived
              and v.revision = (select max(x.revision) from gba.document_versions x
                  where x.tenant_id = v.tenant_id and x.document_id = v.document_id))
        or not exists (
            select 1 from gba.counterparty_versions v
            where v.tenant_id = new.tenant_id and v.counterparty_id = new.counterparty_id
              and v.state = 'active'
              and v.revision = (select max(x.revision) from gba.counterparty_versions x
                  where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id))
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a document link requires a current document and an active card';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_document_counterparty_link() from public;
create trigger document_counterparty_links_enforce_change
    before insert or update or delete on gba.document_counterparty_links
    for each row execute function gba.enforce_document_counterparty_link();

create trigger document_files_require_module before insert on gba.document_files
    for each row execute function gba.require_enabled_module('documents');
create trigger documents_require_module before insert on gba.documents
    for each row execute function gba.require_enabled_module('documents');
create trigger document_versions_require_module before insert on gba.document_versions
    for each row execute function gba.require_enabled_module('documents');
create trigger document_counterparty_links_require_module before insert
    on gba.document_counterparty_links
    for each row execute function gba.require_enabled_module('documents');
create trigger document_counterparty_links_require_counterparties before insert
    on gba.document_counterparty_links
    for each row execute function gba.require_enabled_module('counterparties');

-- Document branch scope: reusable separately when restoring a damaged boundary in tests.
create policy document_files_unrestricted_scope on gba.document_files
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy documents_unrestricted_scope on gba.documents
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy document_versions_unrestricted_scope on gba.document_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy document_counterparty_links_unrestricted_scope
    on gba.document_counterparty_links as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
