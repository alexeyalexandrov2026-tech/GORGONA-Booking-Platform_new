# GORGONA — начните здесь (актуальное продолжение, 2026-10-08)

## Current: H3 payment corrections (stacked on the credit notes)

Read [full handoff](NEXT_AGENT_H3_CORRECTIONS_2026-10-08.md) and
[copyable prompt](NEXT_AGENT_PROMPT_H3_CORRECTIONS_2026-10-08.md).
Branch `codex/package-h3-payment-corrections`, own checkout
`C:\Users\alexa\Documents\ChatGPT\gorgona-h3-corrections`, parent `807ed59`
(credit notes, itself on PR17). Code commit `238b157` (forward 0028) and a
docs-only successor are pushed; **no pull request yet** for this branch nor for
the credits branch (the browser pane was signed out): open exactly one draft PR
per branch, credits first. Forward `0028_payment_corrections.sql`: a confirmed
payment is voided or corrected by a new revision under a new settlement event;
its identity stays bound forever; the replaced journal is mirrored
(`payment_correction`), allocations return to the reserve and a correction
confirms its replacement within it; effective P/R everywhere; issued credit,
refund or unknown sent dependencies give `FINANCIAL_RECONCILIATION_REQUIRED`.
Local evidence and decisions:
[validation](evidence/2026-10-08-h3-payment-corrections/VALIDATION.md).
Next: PRs, independent review of 0025–0028, owner decisions, then credit voids
from migration 0029. Nothing is merged; merge, deployment and readiness
promotion are not authorized. Own PG 51470 stopped. Read the actual HEAD and
remote state before continuing.

## Previous: H3 credit notes (stacked on PR17)

Read [full handoff](NEXT_AGENT_H3_CREDITS_2026-10-07.md) and
[copyable prompt](NEXT_AGENT_PROMPT_H3_CREDITS_2026-10-07.md).
Branch `codex/package-h3-credits`, own checkout
`C:\Users\alexa\Documents\ChatGPT\gorgona-h3-credits`, parent `c6c5d89`
(PR17 head). Code commit `76ed64e` (forward 0027) and a docs-only
successor are pushed; **no pull request yet** (the browser pane was signed out):
open exactly one draft PR with base `codex/package-h3-settlement-guards`.
Forward `0027_credit_notes.sql`: credit notes against invoice and manual-accrual
obligations; the unpaid part becomes C, the paid part a separate
`credit_refund` obligation of the opposite direction (100/70/50 → C30/refund20);
one `credit` journal; no active reserve, line capacity, explicit refund account
and reason rules, enforced by the service and again by SQL at commit.
Local full 1099 passed/4 skipped/513.90s with mandatory PostgreSQL/browser;
ruff/format/mypy 214 PASS; web gates PASS; SQL mutation red; upgrade
0026 → 0027 on a populated database PASS.
[Evidence and decisions](evidence/2026-10-07-h3-credits/VALIDATION.md).
Next: independent review of PR17 and this slice, owner decisions, then payment
corrections and credit voids from migration 0028. Nothing is merged; merge,
deployment and readiness promotion are not authorized. Own PG 51470 stopped.
Read the actual HEAD and remote state before continuing.

## Previous: H3 settlement guards (draft PR17)

Read [full handoff](NEXT_AGENT_H3_GUARDS_2026-10-07.md) and
[copyable prompt](NEXT_AGENT_PROMPT_H3_GUARDS_2026-10-07.md).
Branch `codex/package-h3-settlement-guards`, own checkout
`C:\Users\alexa\Documents\ChatGPT\gorgona-h3-guards`, parent `e93ca5c`
(published H2). **[Draft PR17](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/17)
published** on PR16's branch; code commits `24ee21b` (forward 0025) and
`372da57` (forward 0026, self-review corrections); a docs-only successor holds
this handoff. CI on both code commits PASS (push and pull_request runs).
Local full 1053 passed/4 skipped/429.52s with mandatory PostgreSQL/browser;
ruff/format/mypy 211 PASS; upgrade 0024 → 0026 on a populated H2 database PASS.
Fixes F1–F4 of the [independent H2 money/state review](evidence/2026-10-07-h2-settlements/INDEPENDENT_MONEY_STATE_REVIEW_e93ca5c.md):
one identity per external fact, disjoint cash/control accounts, posting date
and business-today bounds, column-level FK readiness.
[Evidence and decisions](evidence/2026-10-07-h3-settlement-guards/VALIDATION.md).
Next: independent review of this slice, owner decisions, HawkScan/Docker, then
the rest of H3 (credits, refunds, corrections) from migration 0027. Nothing is
merged; merge, deployment and readiness promotion are not authorized.
Own PG 51470 stopped. Read the actual HEAD and remote state before continuing.

## Historical: H2 backend and successor handoff

Read [full handoff](NEXT_AGENT_H2_2026-10-07.md) and
[copyable prompt](NEXT_AGENT_PROMPT_H2_2026-10-07.md).
Branch `codex/package-h2-settlements`, own checkout
`C:\Users\alexa\Documents\ChatGPT\gorgona-h2-settlements`, parent 75e809b
(delivered H1 backend). **[Draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16) published;
original eight docs committed/pushed as75c36da. Final docs are a successor.**
Verify current HEAD/origin/CI; do not repeat publication or open a second PR.
Corrective source `15edbed1d608ada9d0901a7710c00eff28c23e71` fixes a diagnosed ledger refresh race in two web files;
financial Python/SQL and frozen migrations are unchanged from54852b4. [CI37578255793](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37578255793) PASS:1044 passed/1 skipped/379.86s;
all3 Docker/image, PG/browser, web69/2.3s and static211 PASS.
Fresh local full:1041 passed/4 skipped/434.68s; focused browser1/17.95s.
Bounded independent UI review PASS; full H2 money/state review remains NOT DONE.
Read the actual HEAD and remote state before continuing.

Forward 0022–0024 add manual accruals, settlement reserves and externally
attested partial confirmations behind the closed finance_documents gate.
Historical author full1041/4/459.51s; fresh corrective full above; Ruff/format/mypy211 PASS;
web gates PASS. Exact-checkpoint [CI37573680437](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37573680437) on75c36da
PASS:1044 passed/1 skipped/381.36s, all3 Docker/image, PG/browser, 69 web tests/2.3s, static211.
Independent money/state review NOT DONE.
[Evidence, changed files and limits](evidence/2026-10-07-h2-settlements/VALIDATION.md).
G/FIN-01 technically_verified; FIN-03/02 planned. Next: H3 credits, refund
obligations and corrections; then H4 UI/admission. No H acceptance/promotion.
Owner/E2 dirty trees 19/9 are preserved; own PG 51462 stopped.
Production/provider/merge is not authorized. The owner approved the push on
2026-10-07; publication is complete. Next agent verifies delivery/review, then H3.
All older instructions below describe their dated snapshots.

## Historical: H1 invoice backend handoff

Read [full handoff](NEXT_AGENT_H1_BACKEND_2026-10-06.md) and
[copyable prompt](NEXT_AGENT_PROMPT_H1_BACKEND_2026-10-06.md).
Branch `codex/package-h1-persistence`, own checkout
`C:\Users\alexa\.codex\worktrees\package-h1-persistence\Gorgona Booking`.
Reviewed source `2d5a8f917b69f1d52adea96aa8209722d1a24d42`; documentation delivery
is a successor. [Draft PR15](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/15)
targets foundation PR14. Read its exact HEAD/CI before continuing.

Forward0021, immutable invoice draft/history/issue, principal obligation and
atomic G accrual, permanent resolve/cancel recovery and journal read-v2 exist.
H1-R01 independently closed; root full953 passed/4 skipped/378.14s,
Ruff/format/mypy204 PASS; independent47 PG and109 relevant units PASS.
[Evidence, changed files and limits](evidence/2026-10-06-h1-backend/VALIDATION.md).
G/FIN-01 technically_verified; FIN-03/02 planned, finance_documents closed.
Next: H2 manual new accruals and settlement/reserve/partial external confirmation;
then H3 credits/refunds and H4 invoice UI/admission. No H acceptance/promotion.
Owner/E2 dirty trees19/9 are preserved; own PG51456/reviewer51460 stopped.
Local continuation/draft publication authorized; production/provider/merge is
not authorized. All older instructions below describe their dated snapshots.

## Historical: H1 foundation after PR14

Сначала [полная передача следующему агенту](NEXT_AGENT_PACKAGE_H1_2026-10-06.md)
и [готовый prompt](NEXT_AGENT_PROMPT_H1_2026-10-06.md).
Репозиторий alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new;
ветка `codex/package-h-invoices`, checkout
`C:\Users\alexa\.codex\worktrees\package-h-finance-plan\Gorgona Booking`.
Создать собственную ветку/checkout от текущего delivered H HEAD; исходные
Booking/E2 с19/9 измененными путями сохранить.

[Draft PR14](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/14)
опубликован после явного разрешения владельца. Проверенный source843d0b3,
checkpointda3966b:
[CI37534227319](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37534227319)
PASS909 passed/1 optional skip, PG/browser/Docker и build PASS.
Эта передача — следующий docs-only commit; свежий exact-HEAD CI проверять вPR14.
[Evidence](evidence/2026-10-06-h1-foundation/VALIDATION.md).

G/FIN-01 technically_verified; H1 IN PROGRESS, FIN-03/02 planned.
Контракты, арифметика и закрытый finance_documents реализованы; H SQL/API/UI нет.
Следующий шаг: forward0021, typed G posting seam и атомарный invoice issue.
Не включать H и не объявлять FIN-03 принятым. Локальное продолжение разрешено;
production/provider/merge не разрешены. Все старые planning snapshots ниже
исторические для своих SHA и не создают нового запроса на действия.

## История: пакет H — план на согласование, 2026-10-06

Продолжение G переходит в отдельную ветку `codex/package-h-finance-plan`, база
`5be6e7a`. [Передача H](NEXT_AGENT_PACKAGE_H_2026-10-06.md),
[план H](PACKAGE_H_PLAN_2026-10-06.md) и
[ADR-0024 Proposed](../adr/0024-invoices-obligations-and-external-settlements.md).
Подготовлена архитектура счетов/обязательств/резервов/внешних подтверждений,
credit/refund и реестра запросов допуска; runtime H не реализован. FIN-03/02
остаются planned. Независимый обзор предлагаемого дизайна PASS;
[отчеты и проверки](evidence/2026-10-06-package-h-plan/VALIDATION.md). Требуется
решение об объеме/предложенных правилах перед кодом. G/FIN-01 сохраняют
technically_verified; его CI не является приемкой H.
Все прошлые продолжения ниже исторические для своих SHA.

## Актуально: пакет G — финансовая основа, 2026-10-06

Продолжать в собственной ветке `codex/package-g-ledger-review`, checkout
`C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking`.
База — принятый план этапа 2 `151472a`; прежняя копия с начатым G сохранена.
[Передача G](NEXT_AGENT_PACKAGE_G_2026-10-06.md) и
[свежая приемка](evidence/2026-10-06-ledger/ACCEPTANCE.md) имеют приоритет над
историческими поручениями ниже.

Миграция 0020, книги/счета/проводки/сторно/периоды/ведомость, API и /ledger
реализованы. Воспроизведен и закрыт SQL-обход баланса после раннего SET CONSTRAINTS.
Все 7 найденных замечаний независимых обзоров закрыты, включая extra permissive
policies. Проверенный код `95a0de4`: full local 858 passed/4 skipped, CI 861 passed/
1 skipped с Docker; независимый final guard code/unit review PASS в своих пределах.
Finance/FIN-01 — technically_verified отдельным коммитом приемки. API/browser
публикуют finance через обычный реестр без положительного override; focused68
Python и4 browser PASS. Recovery после reload/nav и safe cancel сохраняются.
Проверить свежий exact-SHA CI приемочного HEAD в [draft PR #12](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/12).
Без merge, deployment и промышленных миграций.

## Актуально: этап 2 — план согласован владельцем 2026-10-06 (1A, 2A, 3A, 4B)

[План этапа 2](STAGE2_PLAN_2026-10-06.md) и [ADR-0023 (Accepted)](../adr/0023-ledger-foundation.md):
пакеты G (финансовая основа, FIN-01) → H (счета, платежи, допуск провайдеров) →
I (персонал, WORK-01) → J (материалы, STOCK-01) → K (события провайдеров, FIN-02).
Ветка `claude/stage2-finance-plan` (только документы) поверх `claude/stage1-closure`.
Решения: только основа учета, нейтральный план счетов, без пересчета валют,
период закрывают владелец и менеджер. Пакет G реализуется.

## Актуально: этап 1 закрыт технически; далее план этапа 2

Ветка `claude/stage1-closure` поверх F (`ed7884e`, draft PR #11). CORE-01–04 PASS
технически; новый тест `test_stage1_scenarios.py` проводит малый бизнес, сеть
независимых компаний и гибридную компанию с двумя филиалами через все модули этапа 1
без дублирования и утечки. Исправлено: уведомление «результат неизвестен» больше не
показывается во время обычного запроса (договоры, документы, контрагенты). Полная
локальная suite 790 passed / 4 skipped / 303.39 s. CORE-03 для TMS (диспетчерские
полномочия, офлайн-черновики) — этап 3. Production-миграции и backfill NOT TESTED.
Следующий этап — 2 (финансы, персонал, материалы): сначала план и ADR на решение
владельца. [Evidence](evidence/2026-10-06-stage1/ACCEPTANCE.md). Draft PR #9 (E2), #10 (E3), #11 (F) открыты; merge нет..

## Актуально: пакет F — единая занятость ресурсов (CORE-04)

Согласовано владельцем 2026-10-05 ([ADR-0022](../adr/0022-shared-resource-occupancy.md),
[план](PACKAGE_F_PLAN_2026-10-05.md)). Ветка `claude/package-f-occupancy`. Шаг 1
(общая таблица `resource_allocations`, точное зеркало записей, операторский
`backfill-occupancy`) — код `f74b5de`, push CI 37408551883 success,
[evidence](evidence/2026-10-05-occupancy/ACCEPTANCE.md). Далее шаг 2: служебная
резервация ресурсов как второй потребитель и тест CORE-04; затем чтение доступности.
Шаг 2 выполнен: служебные резервации (миграция 0019, `/reservations/`), CORE-04
подтвержден гонками через сервисы и сырой SQL без блокировок; код `bf3645d`, push
CI 37411493038 success. Остается: production-перенос `backfill-occupancy` по
компаниям, вместимость > 1 и аренда — отдельными пакетами.

## История: пакет F на согласовании (документы)

Только документы, без кода: [план пакета F](PACKAGE_F_PLAN_2026-10-05.md) и
[ADR-0022 (Proposed)](../adr/0022-shared-resource-occupancy.md) в ветке
`claude/package-f-occupancy-plan` от приемки E3 `b8834fb`. До кода нужны четыре
решения владельца (второй реальный потребитель для CORE-04, вместимость > 1,
`resource_blocks`, форма переключения чтения). Код F — только после согласования.

## Актуально: E3 — договоры с контрагентами

Начните с [передачи E3](NEXT_AGENT_PACKAGE_E3_2026-10-05.md) и
[доказательств](evidence/2026-10-05-agreements/ACCEPTANCE.md). Ветка
`claude/package-e3-agreements` (worktree `gorgona-e2-documents`) от принятого E2
`c5a3908`. Код `3044f97` (миграция 0017) прошел push CI 37389126365 (success); модуль counterparties
остается technically_verified. Решения владельца 2026-10-05: расторжение действует
на последнюю подписанную версию (открытый черновик дополнения закрывается как
отмененный), дата расторжения может быть в будущем. Draft PR для E2 и E3 не созданы
(нет gh/авторизации) — тексты в `handoff/` worktree и в архиве
GORGONA_HANDOFF_2026-10-05. Далее: CI SHA приемки, PR, затем только документы плана
CORE-04 (пакет F, ADR-0022) на согласование владельцу. Основную копию владельца
не изменять; разделы ниже исторические для своих SHA.

## Актуально: E2 — документы и файлы

Начните с [передачи E2](NEXT_AGENT_PACKAGE_E2_2026-10-05.md) и
[доказательств](evidence/2026-10-05-documents/ACCEPTANCE.md). Ветка
`claude/package-e2-documents` (worktree `gorgona-e2-documents`) от E2-A `4a6f63b`.
Код `2ab24f3` прошел push CI; коммит приемки делает documents technically_verified.
Проверьте CI финального SHA и создайте draft PR в codex/package-e2-file-validation
(gh в этой сессии отсутствовал), затем E3 договоры и CORE-04. Основную копию
владельца не изменять; разделы ниже исторические для своих SHA.

## Актуально: E2-A — валидатор файлов и CSP

Начните с [передачи E2-A](NEXT_AGENT_E2_FILE_VALIDATION_2026-10-05.md) и
[доказательств](evidence/2026-10-05-file-validation/ACCEPTANCE.md).
Ветка codex/package-e2-file-validation от принятого E1 3983dd4. Это только
защитный prerequisite; documents planned. E2 хранение/API/UI, E3 и CORE-04 впереди.
Основную копию владельца не изменять. Прежние результаты E1 ниже исторические
для своих SHA и не заменяют свежую проверку E2-A.

## Текущее продолжение: E1, 2026-10-05

Общие контрагенты реализованы в отдельной ветке `codex/package-e1-counterparties`
поверх E0 `bbe6ecd80d8827ca94a63f15587704ffc22dba62`. Новая миграция 0015:
карточки и контакты с версиями, ручные решения о дублях, подтвержденные связи
с клиентами записей; исходные снимки записей не изменяются. Доступ только
owner/manager всей компании; FORCE RLS, 34 определения guard, пять module gates,
атомарные reference-only receipts/audit. Страница `/counterparties/` работает
с реальными API/БД; проверены desktop/mobile и автоматическая доступность.

Локально: полная suite **595 passed / 4 skipped / 248.75 s**, затем отдельный
добавленный readiness-тест **1 passed / 1.89 s**; web **47 unit**, сборка **15**
страниц, typecheck/lint/format PASS; Ruff/mypy **163** файла PASS. PostgreSQL
18.6 и браузеры обязательны; три контейнерных и один дополнительный внешний
site gate пропущены локально. Независимый ограниченный обзор чувствительного
кода завершен после исправлений; это не самостоятельный прогон reviewer в БД.

Код `2392566595a2df59f8ec3f073ed9bf184df6447f` прошел два полных CI: push **599 passed / 1 skipped / 118.52 s**,
PR **599 passed / 1 skipped / 171.17 s**. Контейнерные gates выполнены в CI.
Отдельный коммит приемки переводит только counterparties в **technically_verified**,
реестр версии 1; исходный business baseline остается booking-only. Проверено
явное включение через публикацию конфигурации без registry override: focused
**68 passed / 37.26 s**. Финальный SHA приемки требует своего CI; свежий результат
публикуется в PR и STATE.json архива, прежний CI не переносится на новый SHA.
Ссылки на SHA/PR/CI и точные границы — в
[приемке E1](evidence/2026-10-05-counterparties/ACCEPTANCE.md).
Начните с [актуальной передачи](NEXT_AGENT_PACKAGE_E1_2026-10-05.md).
[Draft PR #7](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/7) идет в `codex/package-e-isolation-audit`; PR #6 остается отдельным.
Основная копия владельца с незакоммиченной работой сохранена.

Следующие шаги: E2 документы/файлы, E3 договоры по ADR-0020, затем F/CORE-04.
Этап 1 частичен; 39 отраслей/28 критериев сохранены, полные отраслевые циклы
planned. Azure, реальные провайдеры, нагрузка/восстановление, отраслевые пилоты,
промышленная эксплуатация и ручная screen-reader приемка NOT TESTED.
Ни merge, ни deployment, ни промышленная миграция не выполнялись.
Azure/load tool ниже — исторические проверки E0. npm audit повторен 2026-10-05:
prod **0, exit 0**; общий **5 high dev, exit 1** одной braces-цепочки, без
изменения зависимостей. Прежняя Desktop/handoff777 сейчас отсутствует; новая
передача использует отдельную папку GORGONA_HANDOFF_2026-10-05.

Полный финальный локальный прогон приемки: **596 passed / 4 skipped / 251.25 s**,
exit 0, обязательные PostgreSQL/browser и обычный реестр без override. Ранее
попытка дала 302 setup errors из-за остановленной тестовой БД; после проверки
и запуска только disposable 51454 smoke и полный повтор прошли. Это не
промышленный restart. Подробности и оба результата сохранены в приемке.

Принятая версия readiness `e68ce907ba0459ab99e4c71137c044694a920be1`
имеет собственный зеленый CI: [PR run37272593391](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37272593391)
**599 passed / 1 skipped / 173.32 s** и
[push run37272589058](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37272589058)
**599 passed / 1 skipped / 163.07 s**. Web47, mypy163, PostgreSQL/browser/container
gates выполнены; единственный skip — дополнительный внешний site gate. Следующий
документационный HEAD проверяется отдельно и не выдается за эту версию кода.

## Исторические записи до E1

## Актуальное дополнение: аудит E0, 2026-10-04

Продолжение — [передача после аудита E0](NEXT_AGENT_AUDITED_E0_2026-10-04.md),
код 4ad645fc27a2334f55e5c7c47ee1e3de8eede3a5, draft PR #6 в актуальную
codex/universal-business-foundation от 2f16380. Основная копия владельца сохранена.
Исправлены company predicates и web readiness contract по полученному пакету E.
Свежая regression: 7 failed / 4 passed до кода, 1 web failed; после — focused30,
полная локальная suite 538 passed / 4 skipped / 193.26 s, web42 и сборка14,
Ruff/mypy153 PASS. CI конкретного SHA и пределы — в
[приемке E0](evidence/2026-10-04-isolation-audit/ACCEPTANCE.md).
Переданные [план E](PACKAGE_E_PLAN_2026-10-04.md) и
[ADR-0020](../adr/0020-counterparties-documents-and-contracts.md) сохранены;
E1–E3 и CORE-04 еще не выполнены. Исторические цифры/следующие задачи ниже
не считать актуальнее этого дополнения без проверки.

Azure прочитан: Container Apps env Failed, apps0; PostgreSQL18/KeyVault private.
Сквозной staging BLOCKED. В npm остаются 5 dev findings одной braces-цепочки,
prod0; load tool воспроизводит ложный PASS и пока не принят для OPS-02.
Новых провайдеров, сканера файлов, отраслевых пилотов и промышленного запуска нет.


Этот документ — единая точка входа. Он короче истории в [handoff](NEXT_AGENT_HANDOFF_2026-10-04.md) и ссылается на все нужные документы.

## 1. Где проект

- Рабочая копия: `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`.
- Репозиторий: `https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`, ветка **`codex/universal-business-foundation`** (draft PR #1). `main` содержит только начальный README; merge не выполнялся.
- **Первое действие — проверить GitHub CI последнего точного SHA** (`git log -3`; вкладка Actions или публичный API `https://api.github.com/repos/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs?branch=codex/universal-business-foundation` — `gh` на машине нет, логи требуют авторизации, статусы шагов читаются без нее).

## 2. Что сделано и чем подтверждено

| Пакет | ADR | Миграция | Состояние |
|---|---|---|---|
| Юридические лица (черновики) | [0015](../adr/0015-tenant-owned-legal-entity-drafts.md) | 0010 | CI PASS `d97924f` |
| CORE-03 A — подразделения | [0016](../adr/0016-tenant-owned-departments.md) | 0011 | CI PASS `5b3c00b`, [приемка](evidence/2026-10-04-departments/ACCEPTANCE.md) |
| CORE-03 B — межкомпанейское делегирование | [0017](../adr/0017-cross-company-delegation.md) | 0012 | CI PASS `ed370c6`, [приемка](evidence/2026-10-04-delegation/ACCEPTANCE.md) |
| CORE-03 C — группы компаний | [0018](../adr/0018-company-groups.md) | 0013 | CI PASS `6a81dfd`, [приемка](evidence/2026-10-04-groups/ACCEPTANCE.md). CI на `c9193b2` был FAIL: гонка remove→accept (404 вместо 409), исправлена с red→green тестом |
| D — публикация конфигурации (CORE-02) | [0019](../adr/0019-configuration-publication-and-modules.md) | 0014 | CI PASS `5320c4a`, [приемка](evidence/2026-10-04-configuration/ACCEPTANCE.md) |

Подробные результаты каждого шага: [реестр реализации](GORGONA_IMPLEMENTATION_STATUS.md). Состояние всех 28 критериев: [аудит](GORGONA_PLAN_AUDIT_2026-10-04.md). Технические маршруты и поведение API: [DEVELOPMENT](../DEVELOPMENT.md).

Пакет CORE-03 (A–C) собран для существующих модулей. Диспетчерские операции TMS, офлайн-черновики и сводные отчеты групп появятся со своими модулями и должны использовать гранты ADR-0017. Членство в группе доступа не дает.

## 3. Обязательные правила

Читать [AGENTS.md](../../AGENTS.md) и [мастер-план](GORGONA_MASTER_PLAN.md) до кода. Кратко:

- Самостоятельная универсальная GORGONA; KA Nails — отдельный проект вне работы и приемки. 39 отраслей и 28 критериев сохраняются.
- `business_id == tenant_id == salon_id`; никаких копий компаний; не выдумывать бизнес-факты; исторические миграции не менять.
- Типизированные версионированные контракты; idempotency + expected revision; FORCE RLS + schema guard (сейчас **29** определений + триггер записи); аудит; тест red→green; focused и полные проверки; CI точного SHA; evidence; без fake providers и успешных моков.
- **После каждого завершенного шага обновлять handoff, реестр, аудит, DEVELOPMENT и ADR/evidence** — с SHA, состоянием CI, числами тестов и следующим шагом (требование владельца).
- Без merge, deploy и промышленных миграций без явного разрешения владельца. Коммит/push в рабочую ветку — по поручению владельца.
- Один исполнитель на рабочую копию и на тестовый кластер PostgreSQL (имена ролей fixture общие).

## 4. Как проверять локально

1. Web: в `web/` — `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run test:unit` (41), `npm run build` (14 страниц).
2. API статика: в `api/` — `.venv/Scripts/python.exe -m ruff check src tests`, `-m ruff format --check src tests`, `-m mypy`.
3. PostgreSQL 18.6 и браузеры: полная suite с `GBA_TEST_ADMIN_DSN` (передается только дочернему процессу, никогда не выводится), `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1`: `.venv/Scripts/python.exe -m pytest -q -rs --tb=short`. Последний результат (пакет D, до правок ревью): **527 passed, 4 skipped** (три container gate без Docker, внешний site gate).
4. Тестовые кластеры на этой машине:
   - `%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\data` на **127.0.0.1:51454** — прежний кластер. Он работал, запущенный другим процессом в 15:58; этой сессией не использовался и не останавливался. Выяснить владельца перед использованием.
   - `%LOCALAPPDATA%\GorgonaBookingTests\claude-cluster` на **127.0.0.1:51455** — отдельный одноразовый кластер этой сессии из официального EDB PostgreSQL 18.6. Приватный `test-connection.json` лежит в той же папке; пароль не выводить. Запуск: `pg_ctl -D <data> -l <log> -o "-h 127.0.0.1 -p 51455 -c max_connections=250" start` через detached `Start-Process -WindowStyle Hidden`; после работы `pg_ctl stop -m fast`.
   - Скачанный архив EDB (~330 МБ) лежит рядом; удалить можно по решению владельца.
5. Браузерные harness (Python → настоящий test-only OIDC → API → PostgreSQL): компания, филиал, делегирование, группы, конфигурация — `tests/integration/test_management_browser.py`. Перед ними нужен `npm run build`. Переход между страницами в spec только по ссылкам: `page.goto`/`reload` теряет сессию.

## 5. План дальше

Детальная карта — [handoff](NEXT_AGENT_HANDOFF_2026-10-04.md) и раздел 13 мастер-плана. Следующий пакет этапа 1:

Пакет **D** (CORE-02: версии конфигурации, реестр модулей, записи готовности) принят на `5320c4a` по [ADR-0019](../adr/0019-configuration-publication-and-modules.md); пользовательские поля и настройка процессов из разрешенных действий (§4) остаются на следующий инкремент CORE-02.

**Следующий: E** — контрагенты, контакты, договоры, документы с версиями и проверкой файлов, сопоставление без автослияния (модули `counterparties` и `documents` в реестре сейчас planned; включить их можно только после технической проверки). До кода: свой план и ADR-0020, согласованные с владельцем. Потом **F** — единая занятость ресурсов по §12.2.1 (расширение → перенос `booking_allocations` → сверка → общий механизм → переключение чтения → откат; критерий CORE-04). После этапа 1 — этапы 2–9 по мастер-плану (FIN/WORK/STOCK → BEAUTY/TMS → BUILD/RENT/PROPERTY → REST/PRO → SUPPLY → MARKET/ENTERPRISE → специализированные отрасли → OPS/Azure ADR-0012).

## 6. Открытые вопросы и известные ограничения

- **Отдельная задача:** запросы к `gba.memberships` без фильтра компании видят собственные членства вызывающего в других компаниях (permissive policy `memberships_self_read`). Исправлен только `list_members`. Остаются `onboarding/readiness.py` (подсчет владельцев при go-live), `onboarding/service.py`, проверка последнего владельца в `identity/invitations.py`. Нужны тест red→green и явный фильтр.
- Записаны в ADR-0017/0018: аудит на каждый делегированный запрос (объем); `/me` не видит, приостановлена ли компания-владелец; пагинация членств групп; нет блокировки приглашающих; дублирование помощников idempotent-команд в модулях этапа 1; хрупкий текстовый тест списка делегируемых маршрутов.
- **Отдельная задача (не проверена):** web-схема `readiness` в `web/lib/management-contracts.ts` требует поле `missing`, а API `ReadinessView` (`api/setup.py`) возвращает `items`; ответы сохранения `/business-hours`, `/policies`, `/facts/{key}` в web, вероятно, не проходят проверку. Нужен тест red→green.
- Docker на машине нет: контейнерные gates проверяются только в CI.
- Azure/staging, промышленная миграция, реальные провайдеры, нагрузка/RPO/RTO и отраслевые пилоты не проверялись.

## 7. Текст поручения следующему агенту

> Продолжи самостоятельную GORGONA в `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`, ветка `codex/universal-business-foundation`. Сначала прочитай `docs/plan/NEXT_AGENT_START_HERE.md`, AGENTS.md, мастер-план, реестр и handoff; не удаляй чужую незакоммиченную работу. Проверь GitHub CI последнего коммита. Если он красный — исправь причину с тестом red→green. Шаги C и D приняты (evidence `evidence/2026-10-04-groups`, `evidence/2026-10-04-configuration`). Составь план и ADR-0020 для пакета E и согласуй их с владельцем до кода. После каждого шага обновляй handoff, реестр, аудит, DEVELOPMENT и ADR/evidence. Без merge, deploy и промышленных миграций. Отчет по-русски с точными PASS/FAIL/NOT TESTED.
