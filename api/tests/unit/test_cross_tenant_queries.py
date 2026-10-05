"""SQL on tables with cross-company read policies must filter by company.

`gba.tenants` and `gba.memberships` carry permissive policies that also show a caller's
other companies (and a platform admin every company); `gba.tenant_hosts` is readable by
everyone for host resolution. Row-level security alone therefore does not scope a query
on them: each one needs an explicit company predicate, except the reviewed lookups below.

The check is a conservative text scan, not a SQL parser: the predicate must appear in the
same statement level as the table (not outside its subquery), and an OR at that level
makes the statement suspect. Dynamic or quoted table names are reported for review.
"""

import ast
import re
from pathlib import Path

import gorgona_booking

_SOURCE = Path(gorgona_booking.__file__).parent
_GUARDED = r"(tenants|memberships|tenant_hosts)"
_TABLE = re.compile(
    rf"(?<!')(?<!insert into )\b\"?gba\"?\.\"?{_GUARDED}\"?(?![\w.])", re.IGNORECASE
)
_DYNAMIC = re.compile(r"\"gba\"\.|\bgba\.\{", re.IGNORECASE)
_STATEMENT = re.compile(r"\b(select|union|insert|update|or)\b", re.IGNORECASE)
_COMPANY = r"(?:%s|gba\.current_tenant_id\(\))"
_FILTER = {
    "tenants": re.compile(rf"(?<![\w])(?:\w+\.)?(?:id|tenant_id)\s*=\s*{_COMPANY}", re.I),
    "memberships": re.compile(rf"(?<![\w])(?:\w+\.)?tenant_id\s*=\s*{_COMPANY}", re.I),
    "tenant_hosts": re.compile(rf"(?<![\w])(?:\w+\.)?tenant_id\s*=\s*{_COMPANY}", re.I),
}
# Reviewed cross-company lookups: (file, exact SQL fragment, reason). Only references
# inside the fragment are exempt, never the rest of the statement.
_ALLOWED = (
    (
        "api/salons.py",
        "from gba.memberships m left join gba.tenants t on t.id = m.tenant_id",
        "/v1/me lists the caller's own memberships in every company",
    ),
    (
        "api/salons.py",
        "join gba.memberships s on s.tenant_id = g.servicer_tenant_id",
        "/v1/me lists grants usable through the caller's servicing memberships",
    ),
    (
        "tenancy/resolver.py",
        "select tenant_id from gba.tenant_hosts where host = %s",
        "public host resolution",
    ),
    (
        "onboarding/service.py",
        "select tenant_id from gba.tenant_hosts where host = %s",
        "operator onboarding checks that a host is free",
    ),
    (
        "business/departments.py",
        "select 1 from gba.{} where tenant_id = %s and id = %s",
        "reference check over fixed table names (legal entities, locations)",
    ),
    (
        "db/provisioning.py",
        "gba.{}",
        "transaction setting name gba.<key>, not a table",
    ),
    (
        "db/schema_guard.py",
        "SELECT 1 FROM gba.{} {}",
        "approved policy text built from fixed table names (not a query of guarded tables)",
    ),
)


def _sql_strings(path: Path) -> list[str]:
    strings: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            parts = [
                v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}"
                for v in node.values
            ]
            strings.append("".join(parts))
    return [" ".join(s.split()) for s in strings if "gba" in s.lower()]


def _segment(text: str) -> tuple[str, bool]:
    """The rest of the table's statement level, and whether it holds a top-level OR."""
    depth, end, has_or = 0, len(text), False
    for match in re.finditer(r"[()]|" + _STATEMENT.pattern, text, re.IGNORECASE):
        token = match.group(0)
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            if depth < 0:
                end = match.start()
                break
        elif depth == 0:
            if token.lower() == "or":
                has_or = True
                continue
            end = match.start()
            break
    return text[:end], has_or


def _problems(text: str, exempt: list[tuple[int, int]] | None = None) -> list[str]:
    exempt = exempt or []
    problems = []
    for match in _TABLE.finditer(text):
        if any(start <= match.start() < stop for start, stop in exempt):
            continue
        segment, has_or = _segment(text[match.end() :])
        if has_or or not _FILTER[match.group(1).lower()].search(segment):
            problems.append(f"{match.group(0)}{segment[:80]}")
    for match in _DYNAMIC.finditer(text):
        if not any(start <= match.start() < stop for start, stop in exempt):
            problems.append(f"dynamic or quoted name: {text[match.start() : match.start() + 60]}")
    return problems


def _exempt_spans(relative: str, text: str) -> list[tuple[int, int]]:
    spans = []
    for path, fragment, _ in _ALLOWED:
        if path != relative:
            continue
        start = text.find(fragment)
        while start != -1:
            spans.append((start, start + len(fragment)))
            start = text.find(fragment, start + 1)
    return spans


def test_queries_on_cross_company_tables_filter_by_company() -> None:
    found: list[str] = []
    for path in sorted(_SOURCE.rglob("*.py")):
        relative = path.relative_to(_SOURCE).as_posix()
        for text in _sql_strings(path):
            exempt = _exempt_spans(relative, text)
            found.extend(f"{relative}: {problem}" for problem in _problems(text, exempt))
    assert found == []


def test_reviewed_cross_company_lookups_still_exist() -> None:
    for relative, fragment, reason in _ALLOWED:
        texts = _sql_strings(_SOURCE / relative)
        assert any(fragment in text for text in texts), (relative, reason)


def test_the_check_detects_missing_company_filters() -> None:
    unfiltered = (
        "select booking_state from gba.tenants",
        "SELECT booking_state FROM GBA.TENANTS",
        'select booking_state from "gba"."tenants"',
        "select (select count(*) from gba.memberships where role = 'owner'), "
        "(select count(*) from gba.tenant_hosts where tenant_id = gba.current_tenant_id())",
        "select role from gba.memberships where id = %s for update",
        "select exists (select 1 from gba.memberships where role = 'owner') "
        "from gba.locations where tenant_id = %s",
        "select 1 from gba.memberships where tenant_id = %s or role = 'owner'",
        "select 1 from gba.memberships where role = 'owner' UNION select 1 from gba.invitations "
        "where tenant_id = %s",
        "select 1 from gba.memberships where tenant_id = any(%s)",
        "select 1 from gba.{} where tenant_id = %s",
    )
    for sql in unfiltered:
        assert _problems(sql), sql
    filtered = (
        "select booking_state from gba.tenants where id = %s",
        "select 1 from gba.memberships m join gba.users u on u.id = m.user_id "
        "where m.tenant_id = %s and u.email_normalized = %s",
        "insert into gba.memberships (tenant_id, user_id) values (%s, %s)",
        "select (select count(*) from gba.memberships "
        "where tenant_id = gba.current_tenant_id() and role = 'owner'), 1",
    )
    for sql in filtered:
        assert not _problems(sql), sql
    exempt_fragment = "from gba.memberships m left join gba.tenants t on t.id = m.tenant_id"
    joined = f"select 1 {exempt_fragment} join gba.tenants x on x.slug = m.role"
    assert len(_problems(joined, [(9, 9 + len(exempt_fragment))])) == 1
