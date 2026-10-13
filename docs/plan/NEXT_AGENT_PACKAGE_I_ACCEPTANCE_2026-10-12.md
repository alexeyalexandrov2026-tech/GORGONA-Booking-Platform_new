# Next agent — Package I acceptance preparation, 2026-10-12

## Current checkpoint — 2026-10-12: production dependency audit cleared

Production-аудит зависимостей web (`npm audit --omit=dev`) — **PASS: 0 находок**; было
FAIL: 2 high. Обновлены `next` 16.3.7 → 16.3.8 и `source-map-js` 1.2.1 → 1.2.2. Код
приложения, тесты и миграции не менялись. Полный аудит вместе с инструментами
разработки — **FAIL: 5 high**: одна цепочка `braces`, исправленной версии которой не
существует; в production-образ она не попадает.

Проверки обновлённого дерева: full local **PASS: 1531 passed, 4 skipped in 1023.50s (0:17:03)**; Ruff, format и mypy PASS на
265 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS. CI:
**PASS**, [run 38315410876](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38315410876) на `8a1a7ab`: задание 1204 с, pytest 1057 с; текст логов не читался.
Ветка `codex/web-dependency-audit` опубликована с разрешения владельца (основа `4630ca3`).

Состояние Package I не изменилось и описано в следующем разделе.

Владелец 2026-10-12 выбрал перемотку `main` на вершину ветки `codex/merge-plan`
([план](MERGE_PLAN_2026-10-12.md)); PR #2–#5 считаются заменёнными и не сливаются. Где сейчас
`main`, читать из `git ls-remote origin main`; запись о выполнении — на ветке `codex/merge-plan`.

[Актуальный handoff](NEXT_AGENT_WEB_DEPENDENCY_AUDIT_2026-10-12.md),
[готовый prompt](NEXT_AGENT_WEB_DEPENDENCY_AUDIT_PROMPT_2026-10-12.md),
[запись о срезе](evidence/2026-10-12-web-dependency-audit/VALIDATION.md).

## Previous checkpoint — 2026-10-12: package I accepted technically; WORK-01 and CORE-04 verified

WORK-01 записан как `technically_verified` на коде `f41f9a8`. Модуль `workforce` стал
включаемым: компания получает его, только опубликовав конфигурацию с ним. CORE-04
записан как `technically_verified` отдельным коммитом `1b925f1` по основаниям пакета F.
ADR-0025 — Accepted as implemented. Решение: 2026-10-12 владелец поручил исполнителю
выбирать самостоятельно и на предложение выполнить приёмку ответил «Continue»;
трактовка записана в [записи о приёмке](evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md).

Проверки дерева приёмки: full local **PASS: 1531 passed, 4 skipped in 972.96s (0:16:12)**; Ruff, format и mypy PASS на
265 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS; независимая
проверка изменения PASS. CI коммита приёмки: **PASS**, [run 38236481277](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38236481277) на `75f2b9b`: задание 1037 с, pytest 899 с; текст логов не читался.
Production audit **FAIL: 2 high** (next, source-map-js).

Это техническая приёмка. Пилота и разрешения на production нет. PR и merge не
выполнялись; миграции и зависимости не менялись. Утверждения ниже о том, что
WORK-01 или CORE-04 planned, а workforce закрыт, относятся к своим датам.

[Handoff приёмки](NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md),
[готовый prompt](NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md),
[запись о приёмке](evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md),
[независимая проверка](evidence/2026-10-12-work-01-acceptance/INDEPENDENT_CHECK.md),
[предыдущий срез: исправления и публикация](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_VALIDATION.md).
Ниже сохранены исторические срезы; их результаты не заменяют текущий handoff.

## Previous checkpoint — 2026-10-12: corrections uncommitted; full suite FAIL

R2-1/R2-2/R2-3/CR-1 исправлены в рабочей копии
`C:/Users/alexa/.codex/worktrees/package-i4-review-corrections/Gorgona Booking`,
branch `codex/package-i4-review-corrections`, HEAD490652b. **Нового коммита нет.**
Final focused47PASS,20новых regressionsPASS, workforce browser/static/web и
ограниченный независимый source reviewPASS. Full **1failed,1525passed,4skipped /
1124.75s**: counterparty desktop ambiguous alert locator; mobile module-off timeout.
Причина mobile ещё не доказана. Следующий шаг — diagnosis/focused/full/review,
после зелёных ворот local commit. Production auditFAIL2high. I-09 scopedPASS,
I-12FAIL; acceptanceBLOCKED, WORK-01/CORE-04planned, workforce закрыт.
Миграции/dependencies/readiness не менялись; API/web strict v1 reason_source
требует согласованного выпуска. Новая ветка не опубликована; её CI NOT TESTED.

[Актуальный handoff](NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md),
[готовый prompt](NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md),
[evidence и точные ограничения](evidence/2026-10-12-i4-review-corrections/VALIDATION.md).
Ниже сохранены исторические срезы. Их инструкции/результаты не заменяют текущий
handoff и не означают, что dirty corrections входят в HEAD490652b.

## Previous: повторный обзор выполнен, следующий срез — исправления

Обзор 2 **FAIL**: R2-1 medium/P2 — чтение скрытой смены через swap после
повторного приглашения в тот же филиал без нового профиля; R2-2 medium/P2 —
гонка разных cancel-ключей создаёт 21 маркер вместо 20; R2-3 low/P3 — экран
скрывает допустимую человеческую причину `Clock-in`. Код не исправлялся.
[Отчёт](evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW_2.md),
[точные проверки](evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW_2_CHECKS.json).
I-09/I-12 текущего плана FAIL. WORK-01/CORE-04 остаются planned, workforce закрыт
вне фикстур; пакет не принят. Ни одна новая ветка не опубликована.

Актуальная копия обзора:
`C:/Users/alexa/.codex/worktrees/package-i4-review-2/Gorgona Booking`, локальная
ветка `codex/package-i4-review-2` от `0356eb564ca645ea2c6e50aa3f5844b738d45276`.
Коммит документов обзора читать из Git. Исходная acceptance-копия
`C:/Users/alexa/Documents/ChatGPT/gorgona-package-i` сохранена на `0356eb5`.
Перед изменением проверять оба фактических состояния, не переносить новые
документы в чужую/грязную копию автоматически. Удалённая I4 c6b8e34 и её CI
success проверены заново; CI локальной ветки обзора NOT TESTED.

Свежие результаты: 86 focused PASS / 104.38s; standard browser PASS 1 / 150.78s;
timezone≠UTC + company-wide staff browser PASS 1 / 149.74s, обе ширины/три фазы.
Отрицательные пробы не исправлены: quota 3 FAIL / 10.70s, lifecycle 1 FAIL +
2 PASS / 7.99s, human-reason browser 1 FAIL / 72.26s. Static/web PASS, unit 102,
build 23; production audit FAIL 2 high. Source SHA256 16/16. Полный suite в
этом обзоре не повторялся. Свои кластеры 54378/55504 остановлены; все временные
test-изменения восстановлены/удалены, копии и журналы сохранены вне Git в
`C:/Users/alexa/AppData/Local/GorgonaBookingTests/i4-review2-20261012-0356eb5`.

Следующий безопасный шаг:

1. Прочитать AGENTS, master/plan, ADR-0025, этот текущий раздел и обзор 2.
   Проверить Git, удалённую голову и exact-SHA CI до правок.
2. Создать отдельную ветку исправлений от проверенной головы обзора, например
   `codex/package-i4-review-corrections`, и свою копию/одноразовый кластер.
   Не перезаписывать существующую ветку или другой checkout.
3. Перенести воспроизведения в постоянные regression tests и сначала получить
   настоящие red: R2-1 без active profile после same-home reinvitation;
   R2-2 с двумя наблюдаемыми INSERT waiters, все три gate states; R2-3 настоящая
   человеческая причина в API/карточке/history. Не ослаблять проверки ради green.
4. Минимально исправить безопасный home/отказ нового swap, сериализацию quota
   actor/business и различение человеческих/системных причин. Сохранить старый
   replay/историю, module-off closure/recovery, веточные права, неизменяемую
   историю и SQL-инварианты. Новая схема только при необходимости, следующим
   фактическим номером миграции с guard/restore, без изменения 0001–0035.
5. Focused → полный serial suite → static/web/build → desktop/mobile browser;
   не пересобирать web во время полного suite. Затем независимый обзор
   исправлений и свежие проверки после новых правок. Сохранить первый FAIL и
   итоговые PASS/FAIL/BLOCKED/NOT TESTED, точные команды/числа/SHA, обновить
   evidence/status/handoff и локальный коммит.
6. Не принимать пакет и не повышать readiness. Push/PR/merge, production/Azure,
   providers/funds/credentials требуют отдельного прямого решения владельца.
   CodeRabbit не запускать. Старые результаты ниже — исторический срез подготовки,
   а не инструкция снова начать уже выполненный обзор или объявить его PASS.

## Previous: подготовка приёмки до новых отрицательных проб

**Acceptance preparation completed locally. Package I is not accepted.**
I-01–I-11 PASS for their recorded executed cases; I-12 is conservatively BLOCKED
pending a second independent source review of the post-review fixes. WORK-01 and
CORE-04 remain `planned`, workforce is closed outside fixtures. This document
supersedes its earlier acceptance-preparation prompt at handoff c6b8e34; earlier
slice evidence remains historical and unchanged.

## Start here

| Field | Observed state |
|---|---|
| Repository | alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new |
| Checkout | C:/Users/alexa/Documents/ChatGPT/gorgona-package-i |
| Current local branch | codex/package-i-acceptance |
| Base branch | codex/package-i4-workforce-screens |
| Verified base/handoff SHA | c6b8e341a7e88957ee5011e54e9aa06453b31b49 |
| Final code SHA | b66eb4140c1101d78e1bd4068eac537aab922b38 |
| Final acceptance-document SHA | Read `git log -1 --format=%H`; a commit cannot record its own SHA |
| Latest migration | 0035_work_location_settings.sql; 0001–0035 unchanged |
| Published head | I4 c6b8e34; verify live, do not assume this snapshot is current |
| CI of base | PASS, run 38204334830, job 114664366391, 1509 passed / 1 skipped / 595.96s |
| CI of new local documentation commit | NOT TESTED; acceptance branch is not published |
| PR query for I4 | Zero PRs returned (`state=all`, exact branch head); acceptance PR not created |

Before editing, read AGENTS.md, GORGONA_MASTER_PLAN.md, the current part of
CLOUD_CODE_HANDOFF.md, relevant architecture, the working
[package I plan](PACKAGE_I_PLAN_2026-10-09.md),
[ADR-0025 Proposed](../adr/0025-workforce-shifts-and-timesheets.md), and:

- [Fresh acceptance preparation](evidence/2026-10-12-i-acceptance/ACCEPTANCE.md).
- [Commands, case selections/counts, skipped cases and current audit](evidence/2026-10-12-i-acceptance/CHECKS.json).
- [16/16 current Git-blob hash matches](evidence/2026-10-12-i-acceptance/SOURCE_SHA256.json).
- [Actual base-CI log excerpts](evidence/2026-10-12-i-acceptance/CI_EVIDENCE.json).
- [Original independent review](evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW.md)
  and [author response](evidence/2026-10-11-i4-shift-visibility/AUTHOR_RESPONSE.md).

Inspect `git status`, branch, HEAD, recent log, worktrees and remote before changes.
Do not overwrite successor work or switch a dirty checkout. Local and remote I4
matched c6b8e34 before this preparation. Downloads INVENTORY.md, INDEPENDENT_REVIEW.md
and AUTHOR_RESPONSE.md matched the repository copies byte for byte at that point.
The attached instructions were not separate authorization to publish or accept.

Read-only remote/CI checks:

```powershell
git ls-remote origin refs/heads/codex/package-i4-workforce-screens refs/heads/codex/package-i-acceptance
```

Use the public GitHub REST endpoints under
`https://api.github.com/repos/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`:
`/actions/runs?branch=codex/package-i4-workforce-screens&per_page=10`,
`/actions/runs/38204334830/jobs?per_page=100`, and `/pulls?state=all` with the exact
head filter. Fetch the actual job log through the authorized GitHub connector.
Check the returned head_sha/event/conclusion; no PR-only workflow query proves
the absence of push CI. Do not apply base CI to a different final SHA.

## What was verified freshly

One serial full run with real PostgreSQL 18.6 and browser required:
**PASS: 1506 passed / 4 skipped / 1026.84s** on the unchanged c6b8e34 runtime tree.
Ruff check/format/mypy PASS (264 files); web typecheck/lint/format PASS;
unit **102 passed / 1.4s**; build **23 pages**. I4 executes six successful
desktop/mobile Playwright cases across closed/enabled/off phases, with existing
axe/overflow and recovery assertions. Four other specs are phase-filtered in
each invocation; all six intended phase/viewport cases execute overall.

Base CI was read through the public REST API and GitHub connector:
**1509 passed / 1 skipped / 595.96s**, including the production image build and
required container checks; web unit 102, pages 23, format/mypy 267 files.
The source-hash table is 16/16 matches, and no runtime code changed after b66eb41.
Fresh local production npm audit remains **FAIL: 2 high, next and source-map-js**.
No dependency remediation or readiness promotion was performed.

The evidence matrix selects only cases actually executed in this new C1 run.
Counts overlap between rows and must not be added. The original review covers
a806380, not the fourteen fixes of b66eb41; rerunning regression tests and matching
hashes is not a second source review. I-12 therefore remains conservatively BLOCKED.
Final local documentation-commit CI also remains NOT TESTED until authorized
publication and a successful exact-SHA run.

## Next safe action: independent re-review of the fixes

Use your own branch/checkout, for example `codex/package-i4-review-2`, from the
verified current acceptance head. Inspect existing branches/worktrees first;
do not overwrite an existing review checkout or branch. The author/acceptance
checkout is for one executor only. No product edit is required for a review.

Read the review, author response and current hash evidence. Inspect
`git diff a806380..b66eb41` substantively, including:

1. F1: privacy refusal of a new swap, all lookup/probe/replay paths, handover,
   pickup and the participant request-shift read; document the API/SQL boundary.
2. F2: the effective version's outside-schedule mark on server and screen.
3. F3/F9: 200/201/255-character keys, the per-user/business 20-cancellation limit,
   races and module-off behavior.
4. F5–F8, N1–N4/N6: correspondence to the finding and adjacent behavior.
5. N7: observed wait for the actual top-level receipt writer, not row xmin.
6. F4/N5: the deliberately documented 24-hour lifetime and unbounded date choice;
   these are owner choices, not silently accepted policy changes.

Record PASS/FAIL/BLOCKED/NOT TESTED with actual commands/counts, severity,
path/line and reproduction for any finding. Write INDEPENDENT_REVIEW_2.md under
the existing visibility evidence folder in your own branch, local commit only.
No CodeRabbit. Never use historical counts as your own reproduction.
If a product defect needs correction, reproduce a failing check first, make the
smallest fix on an appropriate isolated branch, then focused/full/static/web
checks and actual browser validation when the screen changes. Fresh evidence
must follow every substantive correction. Migration changes are forward-only,
next actual number, including workforce_guard and branch-policy restoration.

## Owner decisions still pending

- Explicit approval of the working package I plan and Proposed ADR-0025.
- Acceptance and any WORK-01 promotion in a separate authorized commit.
- CORE-04 discrepancy: F acceptance says verified; registry remains planned.
- Publication/PR creation and the unmerged branch stack's merge order.
- A company-wide visibility default (currently branch-local; new branches visible),
  and retaining the refusal of a new swap while hidden.
- Arbitrary date bounds for colleague reads; 24-hour cancelled-key protection;
  the role shown to a branch manager in the directory.
- Separate earlier work: H-acceptance draft PR and independent FIN-03/ec39622 check.

## Environment and preserved boundaries

Python 3.14.6:
`C:/Users/alexa/.codex/worktrees/package-g-ledger-review/Gorgona Booking/api/.venv/Scripts/python.exe`.
Node 24.18.0/npm 11.16.0: C:/Program Files/nodejs, first in PATH.
PostgreSQL 18.6: C:/Users/alexa/AppData/Local/GorgonaBookingTests/postgres-18.6/pgsql/bin.
Playwright browsers were already installed. No new dependency was introduced.

Acceptance artifacts/private helper scripts are outside Git under
`C:/Users/alexa/AppData/Local/GorgonaBookingTests/i-acceptance-20261012-c6b8e34`;
MSIX resolves this into the application's LocalCache (exact paths in CHECKS.json).
Both its bootstrap and retry clusters are stopped. Retry used port 56721;
its postmaster data/port were checked before stop. No plaintext DSN was persisted;
the init password file was removed. Existing cluster directories must not be
reused. Use a new directory and a verified free port for any next run. Do not
start/read/stop other agents' clusters, including 51454, 51458, 51474 or 51511.

Initialize a new SCRAM, UTF-8, locale C, checksummed cluster; start with explicit
`-o "-p <free port> -c max_connections=400 -c listen_addresses=127.0.0.1"`.
For pg_ctl on Windows, use a file output handle: a persistent inherited pipe
stalled the initial local wrapper after successful server startup. The wrapper
was corrected before any test; the first attempt is not a C1 result.
Before stopping, verify postmaster.pid's data directory and port belong to you.

For API tests set PYTHONPATH to your checkout's api/src and api,
PYTHONDONTWRITEBYTECODE=1, GBA_REQUIRE_POSTGRES=1, GBA_REQUIRE_BROWSER=1 for
browser/full runs, and the private GBA_TEST_ADMIN_DSN in the child environment.
Do not print the DSN/password. Build web before the full run; do not rebuild it
while tests read web/out. Exact previous commands are in the fresh acceptance
record and CHECKS.json. A new source SHA requires its own fresh results.

Server authorization remains authoritative; browser storage holds only command
identifiers, actor/company and expected version. Resolve by the original key;
create a new key only after cancellation. Cancelled keys are protected for their
24-hour receipt lifetime, with 20 discards per person/business/day. Success is
shown only after refreshed lists. Preserve tenant isolation, SQL invariants,
versioned typed contracts and the closed readiness path outside fixtures.

NOT TESTED locally: containers (three skips), optional external tenant website,
real screen reader, HawkScan, load/soak, deployment/production and the explicit
browser cases in ACCEPTANCE.md (including effective mark, company-wide addition,
Privacy lost response, 5xx/unreadable recovery and paginated lists). CI containers
are separate PASS evidence, not a local PASS. Do not infer complete coverage.

No new permission to push/PR/merge, force-push, rebase/amend/reset/clean, deploy,
run production migrations, act in Azure, use providers/funds or change credentials.
The 2026-10-11 publication permission covered I4 only. Keep code readiness planned.
The universal Booking platform, KA Nails and the camera Local Gateway remain
separate projects. Preserve unrelated owner/reviewer checkouts. No CodeRabbit.

## Final documentation checks

The private validate_docs.py check ran through the same Python executable:
**PASS: 8 UTF-8 files, 5 Markdown/3 JSON, 166 existing local link targets,
12 matching matrix rows, 16 matching source hashes; git diff --check exit 0;
zero runtime changes; both owned cluster PID files absent.** Limited plaintext
DSN/key pattern checks found zero matches, not a full security audit. The complete
documentation diff was inspected. Repeat this validation after the last edits
and local commit; inspect the actual clean status/HEAD and remote again. A new
source change invalidates inherited functional results and requires fresh tests.
