# Независимый H money/state обзор

Reviewer: отдельный executor `/root/h4_financial_ui`, автор UI, не автор H
backend/0031. Собственный checkout/branch; read-only review текущего integration
source. PG/race/API/browser tests выполняет основной executor. Это bounded
static review, не production certification и не доказательство отсутствия
всех возможных defects.

## Исследованный source

- `business/financial_documents.py`: lines 392–624, atomic issue/source/origin;
  0022 manual-origin distinction и final 0030 invoice consistency.
- `business/settlements.py`: prepare/act 508–686/846–1040,
  confirmation/amendment 1046–1324.
- `business/credit_notes.py`: draft 342–429, issue/void 504–910.
- `business/financial_commands.py`: 109–288; `financial_math.py` целиком.
- 0021–0030 current source/origin/consistency/enforcement functions, effective
  P из 0028, C/R из 0029, historical mirror permission из 0030; financial/ledger
  readiness source/default/function EXEC checks.
- Новые admission API/service/contracts, 0031 и admission guard проверены
  отдельно: typed metadata, false capabilities, history, tenant/book,
  receipt/cancellation/version lineage, privileged SQL/readiness boundaries.

Reviewer независимо подтвердил: monetary services/commands, financial/ledger
guards, 0021–0030 и module/readiness registry имеют EMPTY diff от `12875e8`.
0030 hash `e68611d3ef292f84257b0ed4b9c323cb33284c8f8786838d3ffe928b08a6cf4e`.

## Выводы

Подтверждённых блокирующих money/state findings в изученных путях не найдено.
Prepare не резервирует; reserve читает available после ledger lock.
Confirmation переносит собственный R→P; correction зеркалит предыдущий
effective payment, возвращает allocations и повторно подтверждает в своём
reserve; released void только уменьшает P. Issued credit/refund/sent-unknown
dependencies требуют reconciliation до effects и повторно проверяются SQL.
Void не отменяет реально затронутый refund и проверяет later-refunded-credit
dependency. Journal sets сравниваются двунаправленным EXCEPT ALL. Book/party/
currency/current-transaction lineage, immutable history и actor-scoped recovery
сохраняются. Обычный G reverse отказывает для всех H origins; archived exception
разрешает только точный historical mirror, replacement требует active accounts.

Reviewer выполнил без DB: 5460 valid arithmetic transitions сохранили cap/reserve
поведение; invoice100/paid70/credit50 дал C30/refund20; 3 ordinary metadata words
приняты, 6 Unicode Bearer-spacing вариантов отвергнуты. Exit 0.
Это pure-function evidence, не SQL concurrency proof.

Рекомендованные admission probes подтверждены root PG tests: Unicode credential
spacing, same-count evidence replacement и receipt от более ранней transaction.
Выявленный Unicode spacing API/SQL mismatch исправлен и red→green записан
в [VALIDATION](VALIDATION.md). Последующая static проверка охватила final
lexical key boundary и Unicode whitespace additions.

Дополнительно reviewer проверил [PostgreSQL 18 regex source](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/regex/regc_locale.c#L602-L606):
`[[:cntrl:]]` явно включает C0 и DEL/C1 независимо от locale. Root read-only
runtime query на PG18.6/C подтвердил 32/32 C1 codepoints. Нового C1 defect нет.

NOT TESTED reviewer: PG/races/API/browser/deployment/provider/production data.
Первый root full run выявил admission readiness failure после старых tests.
Reviewer независимо подтвердил причину: legacy location damage test удалял
current_location_id CASCADE, затем восстанавливал только прежние policies,
оставляя пять admission policies удалёнными. Root catalog query подтвердил
missing 5 policies / other 7 guard fragments true. Reviewer одобрил минимальный
test-only restore из packaged 0031 и before/after admission guard assertions:
пять distinct restrictive policies, обе scope predicates сохранены, AST и
diff check PASS/exit0. Root focused regression: 63 PASS/48.53s. Full rerun
остаётся отдельным runtime gate в VALIDATION.
