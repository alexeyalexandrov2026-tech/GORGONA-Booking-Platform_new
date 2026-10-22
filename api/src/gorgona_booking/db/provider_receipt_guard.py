"""Packaged K1b-K5b integrity approvals, checked before each internal receipt write."""

import re
from importlib import resources

from gorgona_booking.db.ledger_guard import LEDGER_IMMUTABLE_SOURCE
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError

_SQL = "".join(
    (resources.files("gorgona_booking.db") / "migrations" / name).read_text(encoding="utf-8")
    for name in (
        "0044_provider_receipt_inbox.sql",
        "0045_provider_receipt_attestations.sql",
        "0046_provider_receipt_routing.sql",
        "0048_provider_revocation_record.sql",
        "0049_provider_receipt_truncate_guard.sql",
        "0050_provider_receipt_decisions.sql",
        "0051_provider_money_access.sql",
        "0053_provider_attention_acknowledgements.sql",
        # K5a-fix: refund failures conflict with success; revocations take the ledger lock.
        "0055_provider_review_fixes.sql",
        # K0b: the owner's admissions and the gates of attestations and decisions.
        "0057_provider_connection_admissions.sql",
        # K5b: the inbox index by connection; only the writer records events (IR-03).
        "0059_provider_receipt_review_fixes.sql",
        # K5r: the operation-key index; a suspension is final.
        "0061_provider_review_final_fixes.sql",
        # K6a: failures and releases of events; a parked event takes no lease.
        "0063_provider_event_failures.sql",
        # K6b: retrieved events are attested as stripe_api_v1; reconciliation runs are recorded.
        "0064_provider_event_backfill.sql",
        # K6r (review R3): the worker reads only the keys of a release.
        "0065_provider_review_k6_fixes.sql",
    )
)
# A later `create or replace` (0048) supersedes the earlier body of the same function.
_FUNCTIONS = list(
    dict(
        re.findall(
            r"create (?:or replace )?function gba\.(\w+)\([^;]*?as \$\$(.*?)\$\$;", _SQL, re.DOTALL
        )
    ).items()
)
_FUNCTIONS.append(("reject_ledger_mutation", LEDGER_IMMUTABLE_SOURCE))
_ROUTES = "provider_receipt_routes"
# Receipt tables of K1b-K1d, readable by the runtime and the writer.
_RECEIPTS = (
    "provider_receipt_connections",
    "provider_event_inbox",
    "provider_event_deliveries",
    "provider_event_attestations",
    "provider_verification_configs",
)
# K2a: the worker's tables. K3a (0051): the runtime also reads operations and decisions.
_DECISIONS = ("provider_operations", "provider_event_leases", "provider_event_decisions")
# K4b (0053): a finance user's acknowledgement of a decision without an operation.
_ACKNOWLEDGEMENTS = "provider_event_acknowledgements"
# K0b (0057): the owner's admissions of receipt connections, read by every group.
_ADMISSIONS = "provider_connection_admissions"
# K6a (0063): the worker's failed decisions and a finance user's releases of parked events.
_FAILURES = "provider_event_failures"
_RELEASES = "provider_event_releases"
# K6b (0064): one permanent record per reconciliation run, written by the receipt writer.
_RUNS = "provider_reconciliation_runs"
# Company-scoped tables: tenant and company policies.
_SCOPED = (
    *_RECEIPTS,
    *_DECISIONS,
    _ACKNOWLEDGEMENTS,
    _ADMISSIONS,
    _FAILURES,
    _RELEASES,
    _RUNS,
)
_TABLES = (*_SCOPED, _ROUTES)
_GROUPS = ("gba_runtime", "gba_receipt_writer", "gba_receipt_worker")
# Tables each group may read; a role running the guard is checked against its own group.
_READS = {
    "gba_runtime": {
        *_RECEIPTS,
        "provider_operations",
        "provider_event_decisions",
        _ACKNOWLEDGEMENTS,
        _ADMISSIONS,
        _FAILURES,
        _RELEASES,
        _RUNS,
    },
    "gba_receipt_writer": {*_RECEIPTS, _ROUTES, _ADMISSIONS, _RUNS},
    "gba_receipt_worker": {
        "provider_event_inbox",
        "provider_event_deliveries",
        "provider_event_attestations",
        *_DECISIONS,
        _ADMISSIONS,
        _FAILURES,
    },
}
# K6r (review R3, 0065): columns the worker reads of a table it cannot read whole.
_WORKER_COLUMN_READS = {(_RELEASES, column) for column in ("tenant_id", "event_id", "round")}
# Every K policy depends on these context functions (migrations 0001 and 0009).
_TENANT_SOURCE = "select nullif(pg_catalog.current_setting('gba.tenant_id', true), '')::uuid"
_LOCATION_SOURCE = "select nullif(pg_catalog.current_setting('gba.location_id', true), '')::uuid"


def _column(table: str, name: str, kind: str, tail: str) -> list[object]:
    return [
        table,
        name,
        "timestamp with time zone" if kind == "timestamptz" else kind,
        "not null" in tail
        or "primary key" in tail
        or name in ("tenant_id", "id", "event_id", "delivery_sha256"),
        "s" if "generated always" in tail else "",
        f"(facts ->> '{name if name != 'provider_event_id' else 'event_id'}'::text)"
        if "generated always" in tail
        else "'" + re.findall(r"default '([^']+)'", tail)[0] + "'::text"
        if re.search(r"default '[^']+'", tail)
        else "CURRENT_USER"
        if "default current_user" in tail
        else "SESSION_USER"
        if "default session_user" in tail
        else "gen_random_uuid()"
        if "default gen_random_uuid()" in tail
        else re.findall(r"default ([0-9]+)", tail)[0]
        if re.search(r"default [0-9]+", tail)
        else "false"
        if "default false" in tail
        else "now()"
        if "default now()" in tail
        else None,
        False,  # No PUBLIC column grants, even when the table ACL stays unchanged.
    ]


_KIND = r"(uuid|text|boolean|jsonb|timestamptz|integer|bigint)\b([^\n]*)"
_COLUMNS = [
    _column(table, name, kind, tail)
    for table, block in re.findall(r"create table gba\.(\w+) \((.*?)\n\);", _SQL, re.DOTALL)
    for name, kind, tail in re.findall(r"^    (\w+) " + _KIND, block, re.MULTILINE)
] + [
    # Columns that a later migration adds (0048).
    _column(table, name, kind, tail)
    for table, block in re.findall(r"alter table gba\.(\w+)\n((?:    add column [^\n]*\n)+)", _SQL)
    for name, kind, tail in re.findall(r"^    add column (\w+) " + _KIND, block, re.MULTILINE)
]
# K5r (0061): the stored operation key of each event, decoded by the K2a rules.
for _approved in _COLUMNS:
    if _approved[:2] in (
        ["provider_event_inbox", "operation_kind"],
        ["provider_event_inbox", "operation_object_id"],
    ):
        _approved[5] = f"(gba.provider_receipt_operation(facts)).{str(_approved[1])[10:]}"
# Defaults that a later migration sets (0049).
for _table, _name, _default in re.findall(
    r"alter table gba\.(\w+) alter column (\w+) set default ([^;]+);", _SQL
):
    for _approved in _COLUMNS:
        if _approved[:2] == [_table, _name]:
            _approved[5] = _default
_TRIGGERS = (
    (
        "provider_receipt_connections",
        "provider_receipt_connections_identity",
        27,
        "guard_provider_receipt_connection",
        False,
    ),
    ("provider_event_inbox", "provider_event_inbox_immutable", 27, "reject_ledger_mutation", False),
    (
        "provider_event_deliveries",
        "provider_event_deliveries_immutable",
        27,
        "reject_ledger_mutation",
        False,
    ),
    ("provider_event_inbox", "provider_event_inbox_check", 7, "check_provider_receipt", False),
    (
        "provider_event_deliveries",
        "provider_event_deliveries_check",
        7,
        "check_provider_receipt",
        False,
    ),
    (
        "provider_event_inbox",
        "provider_event_inbox_complete",
        5,
        "provider_receipt_has_delivery",
        True,
    ),
    (
        "provider_event_attestations",
        "provider_event_attestations_check",
        7,
        "check_provider_receipt_attestation",
        False,
    ),
    (
        "provider_event_attestations",
        "provider_event_attestations_immutable",
        27,
        "reject_ledger_mutation",
        False,
    ),
    (
        "provider_event_attestations",
        "provider_event_attestations_config",
        7,
        "check_provider_attestation_config",
        False,
    ),
    (
        "provider_verification_configs",
        "provider_verification_configs_guard",
        31,
        "guard_provider_verification_config",
        False,
    ),
    (_ROUTES, "provider_receipt_routes_immutable", 27, "reject_ledger_mutation", False),
    # 0050: the worker's operations, leases and decisions.
    ("provider_operations", "provider_operations_check", 7, "guard_provider_operation", False),
    ("provider_operations", "provider_operations_immutable", 27, "reject_ledger_mutation", False),
    (
        "provider_event_leases",
        "provider_event_leases_guard",
        31,
        "guard_provider_event_lease",
        False,
    ),
    (
        "provider_event_decisions",
        "provider_event_decisions_decide",
        7,
        "decide_provider_event",
        False,
    ),
    (
        "provider_event_decisions",
        "provider_event_decisions_immutable",
        27,
        "reject_ledger_mutation",
        False,
    ),
    # 0053: acknowledgements of decisions without an operation.
    (
        _ACKNOWLEDGEMENTS,
        "provider_event_acknowledgements_check",
        7,
        "check_provider_acknowledgement",
        False,
    ),
    (
        _ACKNOWLEDGEMENTS,
        "provider_event_acknowledgements_immutable",
        27,
        "reject_ledger_mutation",
        False,
    ),
    # 0057: the admission record and the gates of attestations and decisions.
    (
        _ADMISSIONS,
        "provider_connection_admissions_guard",
        31,
        "guard_provider_connection_admission",
        False,
    ),
    *(
        (table, f"{table}_admission", 7, "require_provider_receipt_admission", False)
        for table in ("provider_event_attestations", "provider_event_decisions")
    ),
    # 0063: failures under a lease and releases of parked events; both permanent.
    (_FAILURES, "provider_event_failures_check", 7, "record_provider_event_failure", False),
    (_FAILURES, "provider_event_failures_immutable", 27, "reject_ledger_mutation", False),
    (_RELEASES, "provider_event_releases_check", 7, "check_provider_event_release", False),
    (_RELEASES, "provider_event_releases_immutable", 27, "reject_ledger_mutation", False),
    # 0064: reconciliation runs, recorded once by the writer.
    (_RUNS, "provider_reconciliation_runs_check", 7, "check_provider_reconciliation_run", False),
    (_RUNS, "provider_reconciliation_runs_immutable", 27, "reject_ledger_mutation", False),
    # 0049: BEFORE TRUNCATE FOR EACH STATEMENT on every receipt table.
    *(
        (table, f"{table}_no_truncate", 34, "reject_provider_receipt_truncate", False)
        for table in _TABLES
    ),
)
_CHECKS = (
    ("provider_receipt_connections", "(namespace ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$'::text)"),
    ("provider_receipt_connections", "(account_id ~ '^acct_[A-Za-z0-9]{1,100}$'::text)"),
    (
        "provider_receipt_connections",
        "(api_version ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}\\.[a-z][a-z0-9-]{0,39}$'::text)",
    ),
    ("provider_receipt_connections", "(admission = 'not_admitted'::text)"),
    ("provider_receipt_connections", "(NOT livemode)"),
    ("provider_event_inbox", "gba.provider_receipt_facts_valid(facts)"),
    ("provider_event_deliveries", "(delivery_sha256 ~ '^[0-9a-f]{64}$'::text)"),
    ("provider_event_deliveries", "gba.provider_receipt_facts_valid(facts)"),
    ("provider_event_attestations", "(delivery_sha256 ~ '^[0-9a-f]{64}$'::text)"),
    # K6b (0064): a signed webhook or an event retrieved from the provider's API.
    (
        "provider_event_attestations",
        "(verifier = ANY (ARRAY['stripe_snapshot_v1'::text, 'stripe_api_v1'::text]))",
    ),
    ("provider_verification_configs", "(version > 0)"),
    (
        "provider_verification_configs",
        "((secret_ref ~ '^[a-z][a-z0-9-]{0,30}:[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$'::text) "
        "AND (secret_ref !~* '(^|[^A-Za-z0-9])(whsec|sk|rk|pk)_'::text))",
    ),
    *(
        (
            table,
            "(((revoked_reason IS NULL) = (revoked_at IS NULL)) "
            "AND ((revoked_at IS NULL) = (revoked_by IS NULL)) "
            "AND (revoked OR (revoked_at IS NULL)) "
            f"AND ((revoked_reason IS NULL) OR (revoked_reason = ANY (ARRAY[{reasons}]))))",
        )
        for table, reasons in (
            ("provider_receipt_connections", "'compromise'::text, 'retired'::text"),
            (
                "provider_verification_configs",
                "'rotation'::text, 'compromise'::text, 'retired'::text",
            ),
        )
    ),
    ("provider_operations", "(kind = ANY (ARRAY['payment'::text, 'refund'::text]))"),
    (
        "provider_operations",
        "(provider_object_id ~ '^(pi|re)_[A-Za-z0-9]{1,100}$'::text)",
    ),
    ("provider_operations", "(parent_object_id ~ '^pi_[A-Za-z0-9]{1,100}$'::text)"),
    ("provider_operations", "(currency ~ '^[a-z]{3}$'::text)"),
    (
        "provider_operations",
        "(((kind = 'payment'::text) AND (provider_object_id ~ '^pi_'::text) "
        "AND (parent_object_id IS NULL)) OR ((kind = 'refund'::text) "
        "AND (provider_object_id ~ '^re_'::text) AND (parent_object_id IS NOT NULL)))",
    ),
    ("provider_event_leases", "(generation > 0)"),
    ("provider_event_decisions", "(rules_version = 1)"),
    (
        "provider_event_decisions",
        "(outcome = ANY (ARRAY['observed'::text, 'needs_review'::text]))",
    ),
    (
        "provider_event_decisions",
        "(reason = ANY (ARRAY['success'::text, 'not_final'::text, 'conflicting_facts'::text, "
        "'unkeyed_operation'::text, 'refund_without_payment'::text]))",
    ),
    (
        "provider_event_decisions",
        "((outcome = 'observed'::text) = (reason = ANY (ARRAY['success'::text, "
        "'not_final'::text])))",
    ),
    (
        "provider_event_decisions",
        "((operation_id IS NULL) = (reason = ANY (ARRAY['unkeyed_operation'::text, "
        "'refund_without_payment'::text])))",
    ),
    (
        _ACKNOWLEDGEMENTS,
        "(((length(btrim(note)) >= 1) AND (length(btrim(note)) <= 500)) "
        "AND (note !~ '[[:cntrl:]]'::text))",
    ),
    (_ADMISSIONS, "(revision > 0)"),
    (_ADMISSIONS, "(state = ANY (ARRAY['test_access'::text, 'suspended'::text]))"),
    (_ADMISSIONS, "(environment = 'test'::text)"),
    (_ADMISSIONS, "(currency = 'USD'::text)"),
    (_ADMISSIONS, "(account_id ~ '^acct_[A-Za-z0-9]{1,100}$'::text)"),
    (
        _ADMISSIONS,
        "(((length(btrim(evidence)) >= 1) AND (length(btrim(evidence)) <= 500)) "
        "AND (evidence !~ '[[:cntrl:]]'::text))",
    ),
    (_ADMISSIONS, "((state = 'suspended'::text) OR charge_allowed OR refund_allowed)"),
    (_FAILURES, "(error_class ~ '^[A-Za-z][A-Za-z0-9_]{0,63}$'::text)"),
    *(
        (_RUNS, f"({name} >= 0)")
        for name in ("pages", "seen", "recorded", "duplicates", "conflicts", "refused")
    ),
    (_RUNS, "(outcome = ANY (ARRAY['completed'::text, 'failed'::text]))"),
    (_RUNS, "(error_class ~ '^[A-Za-z][A-Za-z0-9_]{0,63}$'::text)"),
    (_RUNS, "(window_start < window_end)"),
    (_RUNS, "(seen = (((recorded + duplicates) + conflicts) + refused))"),
    (_RUNS, "((outcome = 'failed'::text) = (error_class IS NOT NULL))"),
    (
        _RELEASES,
        "(((length(btrim(note)) >= 1) AND (length(btrim(note)) <= 500)) "
        "AND (note !~ '[[:cntrl:]]'::text))",
    ),
)
_KEYS = (
    ("provider_receipt_connections", "p", ["tenant_id", "id"], None, None),
    ("provider_receipt_connections", "u", ["namespace", "account_id"], None, None),
    (
        "provider_receipt_connections",
        "f",
        ["tenant_id", "book_id"],
        "ledger_books",
        ["tenant_id", "id"],
    ),
    ("provider_event_inbox", "p", ["tenant_id", "id"], None, None),
    ("provider_event_inbox", "u", ["namespace", "account_id", "provider_event_id"], None, None),
    (
        "provider_event_inbox",
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
    ("provider_event_deliveries", "p", ["tenant_id", "event_id", "delivery_sha256"], None, None),
    (
        "provider_event_deliveries",
        "f",
        ["tenant_id", "event_id"],
        "provider_event_inbox",
        ["tenant_id", "id"],
    ),
    ("provider_event_attestations", "p", ["tenant_id", "event_id", "delivery_sha256"], None, None),
    (
        "provider_event_attestations",
        "f",
        ["tenant_id", "event_id", "delivery_sha256"],
        "provider_event_deliveries",
        ["tenant_id", "event_id", "delivery_sha256"],
    ),
    (
        "provider_event_attestations",
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
    (
        "provider_event_attestations",
        "f",
        ["tenant_id", "book_id"],
        "ledger_books",
        ["tenant_id", "id"],
    ),
    (
        "provider_event_attestations",
        "f",
        ["tenant_id", "connection_id", "verification_config_id"],
        "provider_verification_configs",
        ["tenant_id", "connection_id", "id"],
    ),
    ("provider_verification_configs", "p", ["tenant_id", "id"], None, None),
    ("provider_verification_configs", "u", ["tenant_id", "connection_id", "version"], None, None),
    ("provider_verification_configs", "u", ["tenant_id", "connection_id", "id"], None, None),
    (
        "provider_verification_configs",
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
    (_ROUTES, "p", ["ingress_id"], None, None),
    (_ROUTES, "u", ["tenant_id", "connection_id"], None, None),
    (
        _ROUTES,
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
    ("provider_operations", "p", ["tenant_id", "id"], None, None),
    (
        "provider_operations",
        "u",
        ["tenant_id", "connection_id", "kind", "provider_object_id"],
        None,
        None,
    ),
    (
        "provider_operations",
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
    (
        "provider_operations",
        "f",
        ["tenant_id", "first_event_id"],
        "provider_event_inbox",
        ["tenant_id", "id"],
    ),
    ("provider_event_leases", "p", ["tenant_id", "event_id"], None, None),
    (
        "provider_event_leases",
        "f",
        ["tenant_id", "event_id"],
        "provider_event_inbox",
        ["tenant_id", "id"],
    ),
    ("provider_event_decisions", "p", ["tenant_id", "event_id"], None, None),
    (
        "provider_event_decisions",
        "f",
        ["tenant_id", "event_id"],
        "provider_event_leases",
        ["tenant_id", "event_id"],
    ),
    (
        "provider_event_decisions",
        "f",
        ["tenant_id", "operation_id"],
        "provider_operations",
        ["tenant_id", "id"],
    ),
    (_ACKNOWLEDGEMENTS, "p", ["tenant_id", "event_id"], None, None),
    (
        _ACKNOWLEDGEMENTS,
        "f",
        ["tenant_id", "event_id"],
        "provider_event_decisions",
        ["tenant_id", "event_id"],
    ),
    (_ACKNOWLEDGEMENTS, "f", ["created_by"], "users", ["id"]),
    (_ADMISSIONS, "p", ["tenant_id", "connection_id", "revision"], None, None),
    (
        _ADMISSIONS,
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
    (_FAILURES, "p", ["tenant_id", "event_id", "generation"], None, None),
    (
        _FAILURES,
        "f",
        ["tenant_id", "event_id"],
        "provider_event_leases",
        ["tenant_id", "event_id"],
    ),
    (_RELEASES, "p", ["tenant_id", "event_id", "round"], None, None),
    (
        _RELEASES,
        "f",
        ["tenant_id", "event_id"],
        "provider_event_leases",
        ["tenant_id", "event_id"],
    ),
    (_RELEASES, "f", ["released_by"], "users", ["id"]),
    (_RUNS, "p", ["tenant_id", "id"], None, None),
    (
        _RUNS,
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
)
_INDEXES = (
    (
        "provider_verification_configs",
        "provider_verification_configs_active",
        "CREATE UNIQUE INDEX provider_verification_configs_active "
        "ON gba.provider_verification_configs USING btree (tenant_id, connection_id) "
        "WHERE (NOT revoked)",
    ),
    # K5b (0059): the events of one connection, for the operation list and the link check.
    (
        "provider_event_inbox",
        "provider_event_inbox_connection",
        "CREATE INDEX provider_event_inbox_connection "
        "ON gba.provider_event_inbox USING btree (tenant_id, connection_id)",
    ),
    # K5r (0061): the events of one operation, by the key their facts decode to.
    (
        "provider_event_inbox",
        "provider_event_inbox_operation",
        "CREATE INDEX provider_event_inbox_operation ON gba.provider_event_inbox "
        "USING btree (tenant_id, connection_id, operation_object_id)",
    ),
)
_TENANT = "(tenant_id = gba.current_tenant_id())"
_COMPANY = "(gba.current_location_id() IS NULL)"
_POLICIES: list[tuple[str, str, bool, str, list[str], str, str]] = [
    *(
        (table, table + suffix, permissive, "*", ["public"], predicate, predicate)
        for table in _SCOPED
        for suffix, permissive, predicate in (
            ("_tenant", True, _TENANT),
            ("_company", False, _COMPANY),
        )
    ),
    (_ROUTES, _ROUTES + "_resolve", True, "r", ["gba_receipt_writer"], "true", ""),
    (_ROUTES, _ROUTES + "_provision", True, "a", ["public"], "", _TENANT),
    (_ROUTES, _ROUTES + "_company", False, "a", ["public"], "", _COMPANY),
    # 0050: discovery without a company context, for the worker group only.
    *(
        (table, table + "_discover", True, "r", ["gba_receipt_worker"], "true", "")
        for table in (
            "provider_event_attestations",
            "provider_event_decisions",
            _ADMISSIONS,
            # 0063: discovery skips parked and waiting events.
            _FAILURES,
            _RELEASES,
        )
    ),
]
# Column privileges per group; any role running the guard is checked against its own group.
_INBOX_INSERTS = {
    ("provider_event_inbox", column) for column in ("tenant_id", "id", "connection_id", "facts")
} | {
    ("provider_event_deliveries", column)
    for column in ("tenant_id", "event_id", "delivery_sha256", "facts")
}
# 0053: the runtime records an acknowledgement; its time is the database's. K5b (0059): only
# the receipt writer records events and deliveries (IR-03).
_RUNTIME_INSERTS = {
    (_ACKNOWLEDGEMENTS, column) for column in ("tenant_id", "event_id", "note", "created_by")
} | {
    # 0063: a finance user releases a parked event; the round and time are the database's.
    (_RELEASES, column)
    for column in ("tenant_id", "event_id", "note", "released_by")
}
_WRITER_INSERTS = (
    _INBOX_INSERTS
    | {
        ("provider_event_attestations", column)
        # K6b (0064): the writer names how the event arrived.
        for column in (
            "tenant_id",
            "event_id",
            "delivery_sha256",
            "verification_config_id",
            "verifier",
        )
    }
    | {
        (_RUNS, column)
        for column in (
            "tenant_id",
            "connection_id",
            "window_start",
            "window_end",
            "started_at",
            "pages",
            "seen",
            "recorded",
            "duplicates",
            "conflicts",
            "refused",
            "outcome",
            "error_class",
        )
    }
)
_WORKER_INSERTS = (
    {
        ("provider_operations", column)
        for column in (
            "tenant_id",
            "connection_id",
            "kind",
            "provider_object_id",
            "parent_object_id",
            "currency",
            "first_event_id",
        )
    }
    | {
        ("provider_event_leases", column)
        for column in ("tenant_id", "event_id", "generation", "holder", "expires_at")
    }
    | {
        ("provider_event_decisions", column)
        for column in ("tenant_id", "event_id", "generation", "holder")
    }
    | {
        (_FAILURES, column)
        for column in ("tenant_id", "event_id", "generation", "holder", "error_class")
    }
)
_INSERTS = {
    "gba_runtime": _RUNTIME_INSERTS,
    "gba_receipt_writer": _WRITER_INSERTS,
    "gba_receipt_worker": _WORKER_INSERTS,
}
_REVOCATIONS = {
    (table, column)
    for table in ("provider_receipt_connections", "provider_verification_configs")
    for column in ("revoked", "revoked_reason")
}
_UPDATES = {
    # 0051: the runtime locks the operation it applies (the trigger refuses the update itself).
    "gba_runtime": _REVOCATIONS | {("provider_operations", "currency")},
    "gba_receipt_writer": _REVOCATIONS,
    # UPDATE on one operation column only permits SELECT FOR UPDATE (the trigger refuses it).
    "gba_receipt_worker": {
        ("provider_operations", "currency"),
        *(("provider_event_leases", column) for column in ("generation", "holder", "expires_at")),
    },
}


# Pure helpers over facts; every other K function is a volatile trigger or check.
_IMMUTABLE = (
    "provider_receipt_integer",
    "provider_receipt_facts_valid",
    "provider_receipt_operation",
)


def _compact(source: str) -> str:
    return re.sub(r"\s+", "", source)


async def assert_provider_receipt_ready(conn: RuntimeConnection) -> None:
    tables = list(_TABLES)
    # One catalog round trip. Expected source is packaged, never learned from the target DB.
    row = await (
        await conn.execute(
            """
select
 (select jsonb_agg(jsonb_build_array(c.relname,c.relrowsecurity,c.relforcerowsecurity,
     has_table_privilege(current_user,c.oid,'SELECT'),
     has_table_privilege(current_user,c.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
     exists(select 1 from aclexplode(c.relacl) a where a.grantee=0),
     has_table_privilege('gba_runtime',c.oid,'SELECT'),
     has_table_privilege('gba_runtime',c.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
     has_table_privilege('gba_receipt_writer',c.oid,'SELECT'),
     has_table_privilege('gba_receipt_writer',c.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
     has_table_privilege('gba_receipt_worker',c.oid,'SELECT'),
     has_table_privilege('gba_receipt_worker',c.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')))
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s)),
 (select jsonb_agg(jsonb_build_array(c.relname,p.polname,p.polpermissive,p.polcmd,
     array(select case when r=0 then 'public' else pg_get_userbyid(r)::text end
       from unnest(p.polroles) r order by 1),
     pg_get_expr(p.polqual,p.polrelid),pg_get_expr(p.polwithcheck,p.polrelid)))
  from pg_policy p join pg_class c on c.oid=p.polrelid
  join pg_namespace n on n.oid=c.relnamespace where n.nspname='gba' and c.relname=any(%s)),
 (select jsonb_agg(jsonb_build_array(c.relname,t.tgname,t.tgtype,p.proname,t.tgdeferrable,
     t.tginitdeferred,t.tgenabled,
     t.tgfoid=to_regprocedure('gba.'||p.proname||'()') and t.tgqual is null
       and t.tgnargs=0 and t.tgattr=''::int2vector and octet_length(t.tgargs)=0
       and (t.tgconstraint<>0)=t.tgdeferrable and t.tgparentid=0
       and t.tgoldtable is null and t.tgnewtable is null))
  from pg_trigger t join pg_class c on c.oid=t.tgrelid
  join pg_namespace n on n.oid=c.relnamespace join pg_proc p on p.oid=t.tgfoid
  where n.nspname='gba' and c.relname=any(%s) and not t.tgisinternal),
 (select jsonb_agg(jsonb_build_array(p.proname,p.prosrc,p.prosecdef,p.proconfig,p.provolatile,
     p.proparallel,exists(select 1 from aclexplode(p.proacl) a where a.grantee=0),
     l.lanname,p.oid=to_regprocedure('gba.'||p.proname||case p.proname
       when 'provider_receipt_integer' then '(jsonb,numeric)'
       when 'provider_receipt_facts_valid' then '(jsonb)'
       when 'provider_receipt_operation' then '(jsonb)' else '()' end)))
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  join pg_language l on l.oid=p.prolang
  where n.nspname='gba' and p.proname=any(%s)),
 (select jsonb_agg(jsonb_build_array(c.relname,pg_get_expr(k.conbin,k.conrelid),k.convalidated))
  from pg_constraint k join pg_class c on c.oid=k.conrelid
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s) and k.contype='c'),
 (select jsonb_agg(jsonb_build_array(c.relname,k.contype,
     array(select a.attname from unnest(k.conkey) with ordinality x(num,ord)
       join pg_attribute a on a.attrelid=c.oid and a.attnum=x.num order by x.ord),
     parent_ns.nspname||'.'||parent.relname,case when k.contype='f' then
       array(select a.attname from unnest(k.confkey) with ordinality x(num,ord)
       join pg_attribute a on a.attrelid=parent.oid and a.attnum=x.num order by x.ord) end,
     k.convalidated,k.condeferrable,k.confdeltype))
  from pg_constraint k join pg_class c on c.oid=k.conrelid
  join pg_namespace n on n.oid=c.relnamespace left join pg_class parent on parent.oid=k.confrelid
  left join pg_namespace parent_ns on parent_ns.oid=parent.relnamespace
  where n.nspname='gba' and c.relname=any(%s) and k.contype in ('p','u','f')),
 (select jsonb_agg(jsonb_build_array(c.relname,a.attname,
     has_column_privilege(current_user,c.oid,a.attnum,'INSERT'),
     has_column_privilege(current_user,c.oid,a.attnum,'UPDATE'),
     has_column_privilege('gba_runtime',c.oid,a.attnum,'INSERT'),
     has_column_privilege('gba_runtime',c.oid,a.attnum,'UPDATE'),
     has_column_privilege('gba_receipt_writer',c.oid,a.attnum,'INSERT'),
     has_column_privilege('gba_receipt_writer',c.oid,a.attnum,'UPDATE'),
     has_column_privilege('gba_receipt_worker',c.oid,a.attnum,'INSERT'),
     has_column_privilege('gba_receipt_worker',c.oid,a.attnum,'UPDATE'),
     has_column_privilege('gba_receipt_worker',c.oid,a.attnum,'SELECT')))
  from pg_attribute a join pg_class c on c.oid=a.attrelid
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s) and a.attnum>0 and not a.attisdropped),
 (select jsonb_agg(jsonb_build_array(c.relname,a.attname,format_type(a.atttypid,a.atttypmod),
     a.attnotnull,a.attgenerated,pg_get_expr(d.adbin,d.adrelid),
     exists(select 1 from aclexplode(a.attacl) acl where acl.grantee=0)))
  from pg_attribute a join pg_class c on c.oid=a.attrelid
  join pg_namespace n on n.oid=c.relnamespace
  left join pg_attrdef d on d.adrelid=c.oid and d.adnum=a.attnum
  where n.nspname='gba' and c.relname=any(%s) and a.attnum>0 and not a.attisdropped),
 (select jsonb_agg(jsonb_build_array(c.relname,i.relname,pg_get_indexdef(x.indexrelid),
     x.indisvalid and x.indisready))
  from pg_index x join pg_class i on i.oid=x.indexrelid join pg_class c on c.oid=x.indrelid
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s) and not exists (
     select 1 from pg_constraint k where k.conindid=x.indexrelid and k.conrelid=x.indrelid
       and k.contype in ('p','u','x'))),
 case when pg_catalog.pg_has_role(current_user,'gba_receipt_writer','USAGE')
   then 'gba_receipt_writer'
   when pg_catalog.pg_has_role(current_user,'gba_receipt_worker','USAGE')
   then 'gba_receipt_worker' else 'gba_runtime' end,
 (with recursive members(grp,member) as (
     select g.rolname,m.member from pg_auth_members m join pg_roles g on g.oid=m.roleid
     where g.rolname in ('gba_runtime','gba_receipt_writer','gba_receipt_worker')
     union select s.grp,m.member from members s join pg_auth_members m on m.roleid=s.member)
  select (select count(*)=3 and bool_and(not (rolcanlogin or rolsuper or rolbypassrls
          or rolcreaterole or rolcreatedb or rolreplication))
        from pg_roles where rolname in ('gba_runtime','gba_receipt_writer','gba_receipt_worker'))
    and not exists (select 1 from pg_auth_members m join pg_roles g on g.oid=m.member
        where g.rolname in ('gba_runtime','gba_receipt_writer','gba_receipt_worker'))
    and not exists (select member from members group by member having count(distinct grp)>1)
    and not exists (select 1 from members s join pg_roles r on r.oid=s.member
        where r.rolsuper or r.rolbypassrls)),
 (select count(*)=cardinality(%s::text[]) and bool_and(c.relkind='r' and c.relpersistence='p'
     and not exists (select 1 from pg_rewrite w where w.ev_class=c.oid)
     and not exists (select 1 from aclexplode(c.relacl) a where a.grantee<>c.relowner
       and (a.is_grantable or a.grantee not in
         (to_regrole('gba_runtime')::oid,to_regrole('gba_receipt_writer')::oid,
           to_regrole('gba_receipt_worker')::oid)))
     and not exists (select 1 from pg_attribute t cross join lateral aclexplode(t.attacl) a
       where t.attrelid=c.oid and t.attnum>0 and (a.is_grantable or a.grantee not in
         (to_regrole('gba_runtime')::oid,to_regrole('gba_receipt_writer')::oid,
           to_regrole('gba_receipt_worker')::oid))))
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s)),
 (select bool_and(not exists (select 1 from aclexplode(p.proacl) a where a.grantee<>p.proowner
     and (a.is_grantable or a.grantee not in
       (to_regrole('gba_runtime')::oid,to_regrole('gba_receipt_writer')::oid,
           to_regrole('gba_receipt_worker')::oid))))
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='gba' and p.proname=any(%s)),
 (select count(*)=2 and bool_and(l.lanname='sql' and p.provolatile='s' and p.proparallel='s'
     and not p.prosecdef and p.proconfig is null and p.pronargs=0 and p.prokind='f'
     and p.prorettype='uuid'::regtype and p.proacl is not null
     and btrim(p.prosrc,E' \\t\\r\\n')=case p.proname when 'current_tenant_id' then %s else %s end
     and not exists (select 1 from aclexplode(p.proacl) a where a.grantee<>p.proowner
       and (a.is_grantable or a.grantee not in
         (to_regrole('gba_runtime')::oid,to_regrole('gba_receipt_writer')::oid,
           to_regrole('gba_receipt_worker')::oid))))
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  join pg_language l on l.oid=p.prolang
  where n.nspname='gba' and p.proname in ('current_tenant_id','current_location_id'))
""",
            (
                tables,
                tables,
                tables,
                [name for name, _ in _FUNCTIONS],
                tables,
                tables,
                tables,
                tables,
                tables,
                tables,
                tables,
                [name for name, _ in _FUNCTIONS],
                _TENANT_SOURCE,
                _LOCATION_SOURCE,
            ),
        )
    ).fetchone()
    valid = row is not None
    if row is not None:
        (
            boundary,
            policies,
            triggers,
            functions,
            checks,
            keys,
            privileges,
            columns,
            indexes,
            group,
            roles_safe,
            tables_safe,
            function_acls_safe,
            context_safe,
        ) = row
        # K1g (IR-05): group membership, table shape and ACLs, and the RLS context functions.
        valid = all(
            check is True for check in (roles_safe, tables_safe, function_acls_safe, context_safe)
        )
        valid &= group in _GROUPS
        reads = _READS.get(group, set())
        valid &= sorted(boundary or []) == sorted(
            [
                t,
                True,
                True,
                t in reads,
                False,
                False,
                *(value for other in _GROUPS for value in (t in _READS[other], False)),
            ]
            for t in tables
        )
        actual_policies = [
            [*p[:5], _compact(p[5] or ""), _compact(p[6] or "")] for p in policies or []
        ]
        valid &= sorted(actual_policies) == sorted(
            [*p[:5], _compact(p[5]), _compact(p[6])] for p in _POLICIES
        )
        valid &= sorted(triggers or []) == sorted([[*list(t), t[4], "O", True] for t in _TRIGGERS])
        expected_functions = [
            [
                name,
                _compact(body),
                False,
                None if name == "reject_ledger_mutation" else ["search_path=pg_catalog"],
                "i" if name in _IMMUTABLE else "v",
                "s" if name in _IMMUTABLE else "u",
                False,
                "sql" if name == "provider_receipt_integer" else "plpgsql",
                True,
            ]
            for name, body in _FUNCTIONS
        ]
        actual_functions = [[*f[:1], _compact(f[1]), *f[2:]] for f in functions or []]
        valid &= sorted(actual_functions) == sorted(expected_functions)
        valid &= sorted([c[0], _compact(c[1]), c[2]] for c in checks or []) == sorted(
            [t, _compact(predicate), True] for t, predicate in _CHECKS
        )
        valid &= sorted(keys or []) == sorted(
            [
                *k[:3],
                "gba." + k[3] if k[3] else None,
                k[4],
                True,
                False,
                "a" if k[1] == "f" else " ",
            ]
            for k in _KEYS
        )
        own = group if group in _GROUPS else "gba_runtime"
        valid &= all(
            list(granted)
            == [
                (table, column) in _INSERTS[own],
                (table, column) in _UPDATES[own],
                *(
                    value
                    for other in _GROUPS
                    for value in (
                        (table, column) in _INSERTS[other],
                        (table, column) in _UPDATES[other],
                    )
                ),
                table in _READS["gba_receipt_worker"] or (table, column) in _WORKER_COLUMN_READS,
            ]
            for table, column, *granted in privileges or []
        )
        valid &= sorted(columns or []) == sorted(_COLUMNS)
        valid &= sorted([i[0], i[1], _compact(i[2]), i[3]] for i in indexes or []) == sorted(
            [table, name, _compact(definition), True] for table, name, definition in _INDEXES
        )
    if not valid:
        raise DatabaseUnavailableError("Provider receipt schema is unavailable")
