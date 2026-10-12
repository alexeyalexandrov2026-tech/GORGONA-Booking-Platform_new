# Package I — correction checkpoint / handoff, 2026-10-12

**Полный обязательный прогон FAIL: 1 failed, 1525 passed, 4 skipped in 1124.75s (0:18:44). Приёмка BLOCKED.**
Исправления R2-1/R2-2/R2-3 и дополнительного CR-1 находятся вне коммита.
Их focused/browser проверки и ограниченный независимый source review PASS;
это не отменяет FAIL полного прогона. WORK-01/CORE-04 planned, workforce закрыт.

## Точная исходная точка

Checkout: `C:/Users/alexa/.codex/worktrees/package-i4-review-corrections/Gorgona Booking`.
Ветка `codex/package-i4-review-corrections`, HEAD/base `490652b3f01a1b3de2df2d2e6257fced6caf32e2`.
Девять source/test файлов изменены вне коммита; новые документы тоже вне коммита.
Источником исправлений является эта рабочая копия и [SOURCE_PROOF.json](SOURCE_PROOF.json),
а не HEAD490652b сам по себе. Другие owner/acceptance/review checkout сохранены.
Миграции0001–0035, зависимости/lockfiles/readiness не менялись.

## Реализованные изменения

- R2-1/P2: новый swap определяет home по immutable staff_resource_owners и текущему
  active membership с подходящей областью. Same-home/company-wide reinvitation
  без нового profile не обходит скрытие; несовпадающий home закрывает новый swap.
  Сохранены receipt replay и participant history. Desk использует тот же stable home.
- R2-2/P2: actor/business advisory transaction lock → receipt claim → свежий COUNT
  → marker/audit. Сначала выясняется реальный исход уже исполняемой команды, даже
  при полном лимите; savepoint убирает новый receipt при отказе квоты.
- CR-1/P2 из независимого review: новая unresolved cancellation явно требует
  READ COMMITTED; иначе существующий DatabaseUnavailableError/HTTP503. Известный
  outcome читается и на других уровнях. Red3FAIL/3PASS, затем guard и final checks.
- R2-3/P3: SQL projection возвращает typed reason_source=system/human по событию
  и предыдущей версии, UI показывает человеческие причины независимо от текста.
  Clock-in как человеческая заметка проверена на карточке/history реальным browser.
- Постоянный новый regression module содержит20 случаев: lifecycle/privacy,
  разные cancel keys/реальные lock waiters, full-cap outcome, savepoint rollback,
  isolation guards и четыре системные строки как человеческие причины.

**Совместимость:** reason_source обязателен в строгом v1 TimeView API/web.
Новый API и web нужно выпускать согласованно. Старый strict web отвергнет новое
поле, новый web отвергнет старый ответ. Это release boundary закрытого workforce;
совместимость смешанного deployment не проверена и не заявляется.

## Проверки, которые действительно выполнены

| Проверка | Исход |
|---|---|
| Red permanent regressions до исправлений | FAIL ожидаемо: 9 failed, 1 passed in 30.84s |
| Red human-reason browser | FAIL ожидаемо: 1 failed in 49.99s |
| Red isolation до guard | FAIL ожидаемо: 3 failed, 3 passed, 14 deselected in 6.49s |
| Initial focused до isolation guard | PASS: 214 passed in 222.89s (0:03:42) |
| Workforce browser после исходных исправлений | PASS: 1 passed in 93.47s (0:01:33); шесть intended phase/viewport cases |
| Final focused после isolation guard | PASS: 47 passed in 52.71s |
| Final Ruff/check/format/mypy | PASS exit0 каждый;265 source/test files |
| Web typecheck/lint/format/unit/build | PASS exit0;102 units;23 pages; web не менялся после green |
| Full serial API/PostgreSQL/browser-required | **FAIL: 1 failed, 1525 passed, 4 skipped in 1124.75s (0:18:44)** |
| Workforce regressions в полном прогоне | PASS: все20 новых cases и test_i4_browser |
| Production npm audit | **FAIL exit1:2high next/source-map-js**, без remediation |
| Независимый финальный source review | PASS в ограниченных границах,9 совпадающих hashes |
| CI исправлений | NOT TESTED: source вне коммита/ветка не опубликована |

[CHECKS.json](CHECKS.json) содержит argv/cwd/exit/время/log hashes, JUnit nodes,
первый FAIL, итоговый FAIL и remote observation. [SOURCE_PROOF.json](SOURCE_PROOF.json)
содержит полный api/web snapshot и9 changed-source SHA256/Git blob OIDs.
До/после full исходники совпали. Первый red runner полного hash snapshot не
создавал; ему не приписывается доказательство, которого нет.
[Финальный независимый review](INDEPENDENT_REVIEW.md) и [hashes](SOURCE_SHA256.json),
[первичный CR-1 FAIL](INDEPENDENT_REVIEW_INITIAL.md) и [initial hashes](SOURCE_SHA256_INITIAL.json)
сохранены отдельно. Reviewer самостоятельно проверил static/unit18, но не
запускал integration/browser/full; эти результаты принадлежат основному исполнителю.

## Незакрытый FAIL и следующий диагноз

`api/tests/integration/test_counterparty_browser.py::test_real_counterparty_browser_oidc_pkce_and_database`
возвращает Playwright exit1 (assertion на строке104). Два browser cases:

1. Desktop, `web/tests/counterparties.spec.ts:139`: getByRole("alert") разрешается
   в два элемента: ожидаемый p.error с текстом "This counterparty changed..."
   и пустой Next.js `__next-route-announcer__`. Это доказанная strict-locator
   ambiguity. Product conflict message присутствует; исправление ещё не сделано.
2. Mobile, строка230: ожидание "Counterparties is turned off." истекло за5000ms.
   Desktop и mobile используют один fixture flow. Связь второго отказа с первым
   предполагается по порядку сценария, но не воспроизведена отдельно и не доказана.

Не помечать весь сбой как flaky, infrastructure или unrelated без проверки.
Файлы counterparty API/web/spec не менялись данным срезом; причинность ещё
не установлена. Сохранить этот первый full FAIL. Проверить fixture lifecycle,
scope locator к содержательному сообщению, не скрывать assertion через first(),
force, увеличение timeout или skip. После минимальной правки focused browser
desktop/mobile, affected checks и полный serial suite; новые evidence/review
должны покрывать изменившиеся байты. Новых запусков после full FAIL не было.

## Матрица C2

Это выбранные nodes из фактического full JUnit; строки пересекаются, числа не
складываются. Старые C1 selection rules использованы только для выбора; добавлены
новые privacy/quota/provenance cases. I-12 FAIL из-за обязательного full suite,
хотя его выбранные workforce cases PASS. Внешние acceptance gates отдельно BLOCKED.

| Строка | Выбранные PASS cases | Текущий итог |
|---|---|---|
| I-01 | 3 | **PASS** |
| I-02 | 2 | **PASS** |
| I-03 | 10 | **PASS** |
| I-04 | 10 | **PASS** |
| I-05 | 10 | **PASS** |
| I-06 | 15 | **PASS** |
| I-07 | 10 | **PASS** |
| I-08 | 34 | **PASS** |
| I-09 | 26 | **PASS** |
| I-10 | 152 | **PASS** |
| I-11 | 155 | **PASS** |
| I-12 | 40 | **FAIL** |

## Изменённые исходники

- `api/src/gorgona_booking/business/shift_changes.py`
- `api/src/gorgona_booking/business/timesheet_contracts.py`
- `api/src/gorgona_booking/business/timesheets.py`
- `api/src/gorgona_booking/business/workforce_desk.py`
- `api/tests/integration/test_workforce_review2_fixes.py`
- `web/components/timesheets.tsx`
- `web/lib/workforce-contracts.ts`
- `web/tests/workforce-contracts.spec.ts`
- `web/tests/workforce.spec.ts`

## Среда и непроверенные границы

Python3.14.6, Node24.18.0, npm11.16.0, PostgreSQL18.6. Только собственные
одноразовые SCRAM/checksummed UTF8 localeC clusters; каждый phase со своим
data/port, loopback/max_connections400. Все пять clusters остановлены; full49981
pg-stop exit0; pwfile/postmaster.pid отсутствуют. Пароли/DSN не переносить.
Raw artifacts/helpers: `C:/Users/alexa/AppData/Local/GorgonaBookingTests/i4-corrections-20261012-490652b`.
MSIX-resolved physical paths и source/command hashes сохранены в CHECKS.

Remote read-only observation 2026-10-12T07:14:26.099126Z: опубликована I4c6b8e34,
push CI run38204334830/job114664366391 completed/success, exact-I4 PR count0.
Acceptance/review2/corrections heads не опубликованы. Старый CI не проверяет
новые source files. Push/PR/merge/rebase/amend/reset/clean/force-push, CodeRabbit,
production/Azure/provider/funds/credential actions не выполнялись.

NOT TESTED: три container checks и optional external tenant site (4skip nodes),
screen reader, HawkScan, load/soak, deployment/production; отдельные timezone≠UTC
и company-wide browser probes review2 не повторены. Старые PASS не перенесены.
Owner decisions pending: план/Proposed ADR-0025, 24h cancelled-key lifetime,
date bounds/directory role/company visibility policy, CORE-04 discrepancy,
приёмка/readiness, публикация/PR/stack order. Audit remediation — отдельный scope.
