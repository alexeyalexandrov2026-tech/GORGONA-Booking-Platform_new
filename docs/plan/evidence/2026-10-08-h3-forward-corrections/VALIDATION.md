# H3 — исправления независимого ревью F1–F5, 2026-10-08

## Объём и состояние

Владелец одобрил F1–F5, включая F4, forward-only 0030 и изменения приложения,
отдельный Draft PR, PostgreSQL/regression/security/tenant checks и успешный CI.
Основание — [независимое ревью](../2026-10-08-h3-independent-review/REVIEW.md).
База: `codex/package-h3-credit-voids`, коммит отчёта
`785fb7f3d4ba57a9b758b693d92ee1b2d95fa35b`. Ветка изменений:
`codex/h3-forward-corrections`; checkout:
`C:\Users\alexa\.codex\worktrees\h3-forward-corrections-20261008\Gorgona Booking`.
Origin: `https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.git`.

Кодовые и локальные проверки ниже — **PASS**. CI точного опубликованного SHA
проверяется отдельно после commit/push; этот документ не подменяет такой запуск.
FIN-03/FIN-02 остаются planned; `finance_documents` не повышен и не включён.
Merge, deployment, production migrations и provider/money operations не выполнялись.

## Изменённые файлы и поведение

| Файл | Изменение |
|---|---|
| `api/src/gorgona_booking/db/migrations/0030_h3_forward_corrections.sql` | Единственная новая миграция: preflight и SQL исправления F1–F4; опубликованные 0001–0029 сохранены |
| `api/src/gorgona_booking/business/ledger.py` | Проверка точной исторической зеркальной проводки перед разрешением архивного счёта |
| `api/src/gorgona_booking/db/financial_guard.py` | Одобрение актуальных 0030 SQL bodies, effective EXECUTE helper functions и 20 timestamp/transaction defaults |
| `api/src/gorgona_booking/db/ledger_guard.py` | Проверка последнего определения journal-line guard из 0030 |
| `api/src/gorgona_booking/db/h3_upgrade.py` | Typed owner-side rehearsal всей 0030 с обязательным rollback |
| `api/src/gorgona_booking/db/cli.py` | `check-h3-upgrade`, без вывода DSN/source identities |
| `api/src/gorgona_booking/db/migrate.py` | Общий экспорт существующего migration advisory-lock key; значение не изменено |
| `api/tests/integration/test_h3_forward_corrections.py` | 18 PostgreSQL/API regressions, включая SQL bypass, archive races, helper permissions и tenant/book scope |
| `api/tests/integration/test_h3_upgrade.py` | 6 upgrade/rehearsal проверок на непустой 0029, отказ при конфликтах, неизменность всех строк/RLS/checksums |
| `docs/DEVELOPMENT.md` | Операторская процедура и границы разрешений |
| `docs/plan/GORGONA_IMPLEMENTATION_STATUS.md` | Текущее состояние F1–F5; предыдущий H3 сохранён как исторический snapshot |
| Этот документ | Проверенные результаты и ограничения |

- **F1/P1:** NFKC → PostgreSQL 18 Unicode `casefold` под `pg_unicode_fast` → NFKC
  после существующего удаления ignorables. API и SQL используют один helper;
  греческая sigma и `Straße`/`STRASSE` имеют один ключ. Interior whitespace
  сохраняется. Нормализованные alias/reference существующих payments проверяются
  до принятия новой схемы, включая навсегда связанные voided/corrected identities.
- **F2/P2:** каждый revision settlement event следует исходному payment и
  предыдущему revision event. Before guard и deferred consistency checker
  обеспечивают один причинный порядок при прямом SQL и commit.
- **F3/P2:** credit-note line_count ограничен 198 в before/deferred checks;
  общий существующий предел 199 для invoice/manual accrual не сужен.
- **F4/P2:** helper разрешает только связь текущей transaction с исходной credit
  issued journal или заменяемой effective payment journal. В SQL и приложении
  проверены tenant/book, line number/account/amount и противоположная сторона;
  дата/currency и финальная полнота зеркала проверяются существующими H controls.
  Credit void копирует неизменные финансовые строки целиком. Replacement entry
  не получает исключение. Архивирование никогда не меняется автоматически.
- **F5/P2:** readiness отказывает 503 при утрате обязательного effective EXECUTE
  или изменении H `now()`/`pg_current_xact_id()` defaults; одобрения берутся из
  packaged contracts, а не из текущей повреждённой БД.

0030 SHA-256:
`e68611d3ef292f84257b0ed4b9c323cb33284c8f8786838d3ffe928b08a6cf4e`.
Новых зависимостей, provider SDK, инфраструктуры или платёжных адаптеров нет.

## Существующие данные и preflight

0030 берёт ACCESS EXCLUSIVE на `external_payments`, `external_payment_revisions`,
`financial_documents`, `financial_document_versions`. В рамках той же transaction
создаются четыре временные SELECT-only policy для конкретного migration owner;
имена SQL identifiers безопасно цитируются. RLS/FORCE RLS не отключаются,
runtime/public не получают policy, migration owner не входит в `gba_runtime`.
Все временные policy удаляются до завершения успешной миграции; при отказе
transaction rollback возвращает прежнюю функцию/схему и удаляет policy.

All-company scan отказывает с count-only `0030 preflight:` при:

1. Collisions нового identity key в tenant/book/direction и alias/reference.
2. Revision events с sequence не больше исходного/предыдущего payment event.
3. Любой версии credit note с line_count > 198.

Непустая 0029 fixture содержит invoice A=100, payment P=70, credit C=30 и refund
obligation 20. Preview и реальная миграция проверены на row counts и SHA-256
отсортированных JSON каждой таблицы `gba`: все строки совпали до/после.
Применена только 0030; повторный migrate — no-op; checksum manifest точный.
Три независимых conflict snapshots: preview и real migrate оба отказали,
checksum 0030 отсутствует, все row hashes/counts и прежняя identity function
сохранены; четыре FORCE RLS flags true, временных policy нет.
Superuser и уже обновлённая schema отказаны preview-командой.

Копирование fake fixtures в отдельные disposable БД использует test-only
superuser snapshot restore без restore-time triggers; проверяемые действия
выполняются обычным runtime или nonsuperuser owner. Это не production repair.
Production dataset не подключался: **NOT TESTED**. Перед отдельно разрешённым
production upgrade оператор обязан выполнить эту проверку на фактической цели.

## Измеренные проверки

Один основной исполнитель запускал PostgreSQL suites последовательно на своём
PostgreSQL 18.6 loopback cluster, порт 51472. Credentials из локального pwfile
вводились только через environment; они не выводятся и не входят в Git.
`PYTHONPATH` указывал на данный checkout; `GBA_REQUIRE_POSTGRES=1` исключает
ложный PASS через пропуск PostgreSQL fixtures.

| Проверка | Наблюдаемый результат |
|---|---|
| Red: 8 исходных reproductions на неизменённом 785fb7f/0029 | **8 FAIL**, 8 deselected, 12.78 s; именно нарушения assert/ожидаемого SQL refusal, без setup errors |
| Full core pytest после SQL/application исправлений, обязательные PostgreSQL/browser | **1182 PASS, 4 SKIP**, 564.49 s, exit 0 |
| Final focused: `test_h3_forward_corrections.py`, `test_h3_upgrade.py`, `test_roles_and_migrations.py`, `test_migration_files.py` | **47 PASS**, 34.33 s, exit 0 |
| Ruff format/check | **PASS**, 221 Python files |
| Strict mypy | **PASS**, 221 source files |
| Web typecheck/lint/format | **PASS** |
| Web unit | **69 PASS** |
| Web production build | **PASS**, Next.js 16.3.7, 18 routes |
| Published 0001–0029 diff against base | Empty — **PASS** |
| `git diff --check` / `git diff --cached --check` after final documentation writes | **PASS**, exit 0, no whitespace errors |

Full local core run preceded the preview CLI/module and two additional preview
negative cases. All final Python files passed fresh static/focused checks; the
final-head mandatory CI covers the complete final tree, including Docker runtime.
Local full skips: three Docker checks (Docker unavailable locally) and one
optional external tenant-site check; that tenant project is outside Booking scope.

A preliminary extended run was invalidated after overlapping disposable fixture
processes rotated their shared test-role passwords. Its result is not evidence.
Those processes/owned test databases were closed; the accepted full run above
used a fresh, isolated sequential execution.

Regression coverage verifies identity/API/direct-SQL agreement, nonincreasing
events and 199-line admission refusal, exact historical voids on archived cash
and counteraccounts, denial of new/replacement postings on archived accounts,
replacement to an active account, tampered mirrors, current-transaction linkage,
foreign tenant/book/kind refusal, and both archive/credit-void race orders under
`gba.lock_ledger`. Existing financial dependencies, budget caps and state tests
are retained in the full suite; no automatic financial reconciliation was added.

## Независимая проверка и границы

Read-only reviewer в отдельном checkout/branch проверил final 0030 SHA выше,
minimal function-body changes, preservation of prior budgets/dependencies,
owner-only preflight policies and strict archived-mirror resolution. SQL/core
blockers не обнаружены. Reviewer не запускал параллельные DB suites.
Операторская команда также прошла read-only review: blockers не обнаружены,
общий advisory lock, обязательный rollback, sanitized CLI output и отказ при
несоответствии versions/checksums подтверждены чтением. Имена manifest rows не
сравниваются — это существующее правило `migrate`; точность здесь означает
набор version/checksum, а не отдельное доказательство имён. Reviewer не запускал
tests; runtime outcomes в таблице получены основным исполнителем.

Использованы Git/PowerShell, существующие Python/pytest/psycopg/Ruff/mypy,
локальный PostgreSQL 18.6 и npm/Next/Playwright harness. GitHub connector нужен
для отдельного Draft PR; GitHub Actions — для проверки exact-head CI.
Skills evidence-engineering и multi-reviewer-patterns применены для red/green
доказательств и независимого read-only review. CodeRabbit не запускался вручную.
Docker локально и реальные production/provider данные — **NOT TESTED**.
Документация/проверки не предоставляют разрешение на merge/deployment/migration.
