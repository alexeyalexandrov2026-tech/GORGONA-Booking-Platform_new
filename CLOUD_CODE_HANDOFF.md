# Cloud Code handoff — GORGONA business platform

## Current checkpoint — 2026-10-15: K1b receipt storage locally verified; not published

K1b source `543b73221ac1dd0aa738bd8cf33dd468366ef27a`, `codex/package-k1b-inbox`, base `ffb176b3cc4bd83637eff29246f6045e0705b9d3`.
Migration0044 adds owner-provisioned `not_admitted` receipt bindings and an append-only
typed event/delivery inbox. Equal facts replay safely; conflicting facts never overwrite
history. Three races observe the intended pg_locks waits.40 new tests PASS.
Static/build/web114 PASS; focused **252 passed in 79.86s (0:01:19)**;
full **1884 passed, 4 skipped in 1502.59s (0:25:02)**, fresh disposable PostgreSQL18.6.
No HTTP route, global routing grant, worker, operational admission or financial effect.
Complete K-01–K-14 NOT TESTED; FIN-02/STOCK-01 planned; ADR0026/0027 Proposed unchanged.
K push/CI and independent review NOT TESTED. Actual provider execution separately gated.
Runtime npm audit0 PASS; existing development audit5high FAIL. Four container/external skips.
[Validation](docs/plan/evidence/2026-10-15-k1b-receipt-inbox/VALIDATION.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_K1B_2026-10-15.md),
[prompt](docs/plan/NEXT_AGENT_PACKAGE_K1B_PROMPT_2026-10-15.md).

## Previous checkpoint — 2026-10-15: K1a offline boundary locally verified; not published

K1a source `7d25aa2d72874271a62e363817e0624fb502497c` on `codex/package-k1a-event-boundary`: signature-first strict
test snapshot decoding with stripe16.0.0, 96 synthetic tests. Static/build/web114 PASS;
focused **191 passed in 53.85s**; full **1844 passed, 4 skipped in 1444.23s (0:24:04)** on fresh disposable PostgreSQL.
No HTTP route/inbox/worker/schema or money effect; full K1 and K acceptance NOT TESTED.
Provider admission is BLOCKED by separate authorization; K push/CI NOT TESTED.
FIN-02/STOCK-01 stay planned, ADR-0026/0027 Proposed; main remains fedd0f1.
Runtime npm audit0; existing development audit5high FAIL. No provider/credential action.
[K1a record](docs/plan/evidence/2026-10-15-k1a-event-boundary/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K1A_2026-10-15.md).

## Previous checkpoint — 2026-10-15: Package K proposed locally; provider gate closed

The next stage-2 package K / FIN-02 now has a local implementation and acceptance
proposal on `codex/package-k-plan`, based on `df88c20687333668d39fe76a26eabca691e62cb0`.
Documentation only: no K route, worker, schema, dependency or provider operation.
K-01–K-14 are NOT TESTED; actual Stripe test admission is BLOCKED by the separate
provider/credential authorization rule. The K branch is not authorized for push.
FIN-02 and STOCK-01 stay planned; ADR-0026/0027 Proposed. Main remains fedd0f1.
Published J exact-head CI 158 PASS; its accepted technical evidence is preserved.
[K plan](docs/plan/PACKAGE_K_PLAN_2026-10-15.md),
[reuse and validation](docs/plan/evidence/2026-10-15-package-k-plan/ARCHITECTURE_REUSE.md),
[current handoff](docs/plan/NEXT_AGENT_PACKAGE_K_PLAN_2026-10-15.md).

## Previous checkpoint — 2026-10-15: STOCK-01 technical evidence PASS; readiness unchanged

J-01–J-14 technical evidence PASS against `aedbb982a696052d606499f737b1754fce362b6a` with exact CI run 157
success. Full local **PASS: 1748 passed, 4 skipped in 1448.82s (0:24:08)**. STOCK-01 remains planned,
ADR-0026 Proposed; readiness requires the owner's separate explicit authorization. Main
remains fedd0f1. No PR, merge, deployment or production changes. The acceptance documentation
commit needs its own exact-head CI read; api/web source trees are unchanged and recorded.
[Acceptance](docs/plan/evidence/2026-10-15-stock-01-acceptance/ACCEPTANCE.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md).

## Previous checkpoint — 2026-10-15: Package J review fixes part 2 locally verified; acceptance pending

M1, L2, L3 and the two-source destination-insert race are fixed in `7b96fec` on
`codex/package-j-review2-fixes`. Full local **PASS: 1748 passed, 4 skipped in 1448.82s (0:24:08)**. Static/focused PASS;
114 web tests; production audit 0, existing development audit 5 high. No migration or
dependency changed. Exact new CI NOT TESTED at this pre-publication checkpoint.
STOCK-01 remains planned, ADR-0026 Proposed; technical acceptance J-01–J-14 is next.
Main remains fedd0f1. L1/L4 are recorded limits, not fixes.

[Current handoff](docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md), [part-2 record](docs/plan/evidence/2026-10-14-j5-j6-review-fixes-part2/VALIDATION.md).

## Previous checkpoint — 2026-10-14: review of J5 and J6 done; H1 fixed (part 1); not merged

Независимый обзор J5 и J6 проведён: высокая находка H1 (подделка остатка проходила проверку
0042 при смене контекста перед фиксацией) исправлена миграцией 0043: `f366afe` на ветке
`codex/package-j-review2-fixes`. Полный локальный прогон — **PASS: 1746 passed, 4 skipped in 1428.69s (0:23:48)**. Ветка J6 опубликована, CI её
вершины `b3982ba` — PASS. Открыты M1, L2, L3 и тест гонки (часть 2), затем приёмка.
CI этой ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md),
[запись обзора](docs/plan/evidence/2026-10-14-j5-j6-review/REVIEW.md).

## Previous checkpoint — 2026-10-14: package J acceptance preparation (J6) committed; M2 fixed; not merged

Находка M2 независимого обзора измерена и устранена миграцией 0042: при 100 000 движений
одной строки остатка проводка шла 960 мс, теперь 43 мс (45 мс без истории). Добавлены
тесты строк J-12 и J-13 и пробела 10; закоммичено `35227cd` на ветке `codex/package-j-acceptance-prep`.
Полный локальный прогон — **PASS: 1745 passed, 4 skipped in 1646.70s (0:27:26)**. Ветка J5b опубликована, CI её вершины
`f521528` — PASS. Открыты независимый обзор J5 и J6 и сама приёмка STOCK-01. CI этой
ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J6_ACCEPTANCE_PREP_2026-10-14.md),
[запись о срезе](docs/plan/evidence/2026-10-14-j6-acceptance-prep/VALIDATION.md).

## Previous checkpoint — 2026-10-14: package J slice J5b (Stock documents screen) committed; J5 complete; not merged

Вторая часть среза J5 — экран «Складские документы» (`/stock-documents/`) —
закоммичена: `c3da59d` на ветке `codex/package-j5b-stock-documents`; срез J5 завершён. Полный локальный
прогон — **PASS: 1735 passed, 4 skipped in 1587.30s (0:26:27)**. Browser-тест на компьютере и телефоне: доступность без
нарушений, потеря ответа без второго документа, отказ с названной причиной, менеджер
филиала — только перемещения и без сумм. Ветка J5a опубликована, CI её вершины `b003b75`
— PASS. Открыты M2, L6, тесты J-12 и J-13, обзор J5 и приёмка. CI этой ветки на момент
записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J5B_STOCK_DOCUMENTS_2026-10-14.md),
[запись о срезе](docs/plan/evidence/2026-10-14-j5b-stock-documents/VALIDATION.md).

## Previous checkpoint — 2026-10-14: package J slice J5a (Materials screen) committed; not merged

Первая часть среза J5 — экран «Материалы» (`/materials/`) и проверка неопределённой
команды запасов по ключу — закоммичена: `afda55b` на ветке `codex/package-j5-screens`. Полный
локальный прогон — **PASS: 1734 passed, 4 skipped in 1279.06s (0:21:19)**. Browser-тест на компьютере и телефоне: доступность
без нарушений, потеря ответа и её проверка после перезагрузки, повтор тем же ключом,
отмена с отказом поздней копии. Ветка исправлений по обзору опубликована, CI её
вершины `5e3a801` — PASS. Открыты J5b «Складские документы», M2, L6 и приёмка. CI этой
ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J5_MATERIALS_2026-10-14.md),
[запись о срезе](docs/plan/evidence/2026-10-14-j5-screens/VALIDATION.md).

## Previous checkpoint — 2026-10-14: package J review fixes committed; J1–J4 published

Независимый обзор J1–J4 проведён; его находки M1, L1, L2, L4, L5 и часть L3 исправлены и
закоммичены: `33a3ec6` на ветке `codex/package-j-review-fixes`. Главное — перемещение и приёмка
больше не блокируют друг друга намертво; строки остатка и стоимости существуют только
через документы (миграция 0041). Полный локальный прогон — **PASS: 1724 passed, 4 skipped in 1300.24s (0:21:40)**. Предел времени CI поднят до 45 минут. Открыты M2 и L6, экраны (J5) и
приёмка. Владелец 2026-10-14 передал исполнителю три вопроса обзора: «Делай, как ты считаешь нужным. Я доверяю полностью тебе, и ты принимаешь решение.»
CI этой ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW_FIXES_2026-10-14.md),
[запись об исправлениях](docs/plan/evidence/2026-10-14-j-review-fixes/VALIDATION.md),
[запись обзора](docs/plan/evidence/2026-10-13-j-review/REVIEW.md).

## Previous checkpoint — 2026-10-13: package J slice J4 (transfers and returns) published; CI success; not merged

**Обновление 2026-10-13: независимый обзор J1–J4 проведён.** Блокирующих находок нет; две
средние и шесть низких находок не исправлены. Следующий шаг — исправить их в новой ветке от
этой вершины: [запись обзора](docs/plan/evidence/2026-10-13-j-review/REVIEW.md). Строки ниже о том,
что обзора нет, написаны до него.

Вторая часть среза J4 пакета J (возврат по строке исходного документа) написана,
закоммичена и опубликована: `4bd346c` на ветке `codex/package-j4-returns`, поверх опубликованной вершины
первой части (`014e611`). Возврат называет приёмку или списание того же владельца и их
строки, движется обратно источнику и не превышает количества исходной строки. Строка
возврата забирает долю суммы исходной строки; по приёмке запасы уходят по средней цене,
а разница идёт на счёт разницы цен; по списанию материал возвращается по доле его
стоимости. Миграция 0040 таблиц не добавляет. Срез J4 этим закончен; экранов ещё нет.
STOCK-01 остаётся `planned`, модуль в продукте включить нельзя; ADR-0026 остаётся
Proposed.

Проверки: full local **PASS: 1709 passed, 4 skipped in 1637.88s (0:27:17)**; Ruff, format и mypy
PASS на 284 файлах; web typecheck, lint, format, 102 unit и сборка PASS. Гонка двух
возвратов последнего количества засчитана с наблюдаемым ожиданием в `pg_locks`.
Независимый обзор J1–J4 — NOT TESTED: исполнитель проводит его после этой части. Ветка
опубликована 2026-10-13 без PR; CI точного коммита `c7c94ed` — **PASS** (run 38505095541).
`main` не переносился. Где `main` и что опубликовано, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J4_RETURNS_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J4_RETURNS_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j4-returns/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J slice J4 part one (transfers) published; CI success; not merged

Первая часть среза J4 пакета J (перемещение между местами хранения) написана,
закоммичена и опубликована: `0d923a4` на ветке `codex/package-j4-transfers`, поверх опубликованной вершины
среза J3 (`07bde5b`). Перемещение проводится одной командой: документ, строки и по два
движения на строку — расход из места документа и приход в место назначения. Денег оно
не двигает: нет денежной части, оценки и проводки, стоимость владельца не меняется,
блокировка книги не берётся. Внутри филиала его проводит менеджер филиала, между
филиалами — владелец или менеджер всей компании. Миграция 0039 таблиц не добавляет.
Возврата и экранов ещё нет. STOCK-01 остаётся `planned`, модуль в продукте включить
нельзя; ADR-0026 остаётся Proposed.

Проверки: full local **PASS: 1676 passed, 4 skipped in 1876.88s (0:31:16)**; Ruff, format и mypy
PASS на 283 файлах; web typecheck, lint, format, 102 unit и сборка PASS. Пять вариантов
гонок засчитаны с наблюдаемым ожиданием блокировки строки в `pg_locks`. Независимый
обзор — NOT TESTED: исполнитель решил провести его один раз после обеих частей J4. Ветка
опубликована 2026-10-13 без PR; CI точного коммита `7e31cc8` — **PASS** (run 38498098941).
`main` не переносился. Где `main` и что опубликовано, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J4_TRANSFERS_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J4_TRANSFERS_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j4-transfers/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J slices J1–J3 published; CI success; not merged

Срез J3 пакета J (списание по средней цене) написан, закоммичен и опубликован:
`565b68f` на ветке `codex/package-j3-writeoffs`, поверх среза J2. Списание проводится одной
командой: документ, строки, расходные движения, остатки, стоимость и одна проводка
`stock` в книге владельца — в одной транзакции. Сумму расхода считает база по
скользящей средней; остаток не уходит в минус. Миграция 0038 таблиц не добавляет.
Возвратов, перемещений и экранов ещё нет. STOCK-01 остаётся `planned`, модуль в
продукте включить нельзя; ADR-0026 остаётся Proposed.

Проверки: full local **PASS: 1651 passed, 4 skipped in 1727.29s (0:28:47)**; Ruff, format и mypy
PASS на 282 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS. Три гонки
засчитаны с наблюдаемым ожиданием в `pg_locks`. Ветка опубликована 2026-10-13 без PR;
она несёт план, J1, J2 и J3. CI точного коммита `c4a2422` — **PASS** (run 38482480419).
`main` не переносился. Независимый обзор — NOT TESTED: исполнитель решил провести его
один раз после среза J4. Где `main` и что опубликовано, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J3_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J3_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j3-writeoffs/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J slice J2 committed locally; not published

Срез J2 пакета J (счета материалов для книги и приёмка с суммами) написан и закоммичен
локально: `f8e1212` на ветке `codex/package-j2-receipts`, поверх среза J1. Приёмка
проводится одной командой: документ, строки, движения, остатки, стоимость по скользящей
средней и одна проводка `stock` в книге владельца — в одной транзакции. Миграция 0037
добавляет восемь таблиц `stock_*`; суммы видит только участник всей компании. Списаний,
возвратов, перемещений и экранов ещё нет. STOCK-01 остаётся `planned`, модуль в продукте
включить нельзя; ADR-0026 остаётся Proposed.

Проверки: full local **PASS: 1616 passed, 4 skipped in 1295.93s (0:21:35)**; Ruff, format и mypy
PASS на 281 файле; web typecheck, lint, format, 102 unit и 23 страницы PASS. Независимый
обзор и CI — NOT TESTED: ни одна ветка пакета J на момент записи не опубликована. Где
`main` и опубликованы ли ветки, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J2_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J2_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j2-receipts/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J slice J1 committed locally; not published

Срез J1 пакета J (материалы и места хранения, денег нет) написан и закоммичен локально:
`39fc819` на ветке `codex/package-j1-materials`. Миграция 0036 добавляет четыре таблицы
`stock_*` с защитой строк по компании и филиалу, упорядоченными неизменяемыми версиями и
замком модуля; API `/v1/businesses/{id}/inventory/items` и `/places`; карта прав версии 7;
реестр модулей версии 3, где `inventory` зависит от `finance`. STOCK-01 остаётся
`planned`, модуль в продукте включить нельзя; ADR-0026 остаётся Proposed.

Проверки: full local **PASS: 1573 passed, 4 skipped in 1342.47s (0:22:22)**; новые тесты
J1 — 40 passed; Ruff, format и mypy PASS на 274 файлах; web typecheck, lint, format, 102
unit и 23 страницы PASS. Независимый обзор и CI — NOT TESTED: ветка на момент записи не
опубликована. Где `main` и опубликована ли ветка, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J1_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J1_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j1-materials/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J plan approved; code not started

Владелец согласовал план пакета J этапа 2 (базовые материалы, STOCK-01), выбрав
двенадцать решений. Главное: материалы ведутся со стоимостью по скользящей средней и сами
делают проводки в книге учёта; приёмку, списание и возврат проводит владелец или менеджер
всей компании; модуль «Запасы» зависит от «Финансов». ADR-0026 остаётся Proposed до
приёмки STOCK-01. Кода пакета нет: изменены только документы.

Проверки: `git diff --check` PASS; ссылки новых документов ведут на существующие файлы.
Тесты и CI — NOT TESTED: кода в срезе нет, ветка `codex/package-j-plan` на момент записи не
опубликована. Основа — `main` на `fedd0f1`; где `main` сейчас, читать из
`git ls-remote origin main`. Сервер, API, миграции и статусы готовности не менялись.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J_PLAN_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J_PLAN_PROMPT_2026-10-13.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: workforce screens checked in eight untested situations

Экраны «Персонала» проверены в настоящем браузере в восьми ситуациях, которые приёмка
Package I назвала непроверенными: 16 из 16 на компьютере и телефоне. Найдены и исправлены
два дефекта экрана «Мои смены»: он показывал смены вне выбранных четырёх недель и молча
обрезал длинный список. Сервер, API, миграции и статусы готовности не менялись.

Проверки: full local **PASS: 1532 passed, 4 skipped in 1419.45s (0:23:39)**; Ruff, format и mypy PASS на
266 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS. CI на
момент записи NOT TESTED. 2026-10-13 владелец решил опубликовать ветку `codex/workforce-screen-situations` и после
зелёного CI точного коммита перенести на неё `main` одним обычным push; результат CI и
положение `main` читать из GitHub Actions и `git ls-remote origin main`.

[Актуальный handoff](docs/plan/NEXT_AGENT_WORKFORCE_SCREENS_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_WORKFORCE_SCREENS_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-workforce-screen-situations/VALIDATION.md).

## Previous checkpoint — 2026-10-12: main fast-forwarded to the head of the stack

`main` перенесён с `46cd866` на `8a34a80` одним обычным push без force по решению владельца
от 2026-10-12. В `main` теперь вся основная линия: 113 коммитов, миграции 0001–0035.
CI на `main`: **PASS**, [run 38338644832](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38338644832) на `8a34a80`: задание 1108 с, pytest 958 с; текст логов не читался.
Ничего не развёрнуто; статусы готовности не менялись. PR #2–#5 признаны заменёнными и не
сливаются. Страницы PR: отмечены как слитые: #1; закрыты без слияния: нет; остаются открытыми: #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22.

Новая работа начинается от `main`. Запись о выполнении лежит на ветке `codex/merge-plan`, на один
коммит документов впереди `main`.

[Handoff после переноса `main`](docs/plan/NEXT_AGENT_AFTER_MERGE_2026-10-12.md),
[готовый prompt](docs/plan/NEXT_AGENT_AFTER_MERGE_PROMPT_2026-10-12.md),
[план слияния и его выполнение](docs/plan/MERGE_PLAN_2026-10-12.md).

## Previous checkpoint — 2026-10-12: production dependency audit cleared

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
([план](docs/plan/MERGE_PLAN_2026-10-12.md)); PR #2–#5 считаются заменёнными и не сливаются. Где сейчас
`main`, читать из `git ls-remote origin main`; запись о выполнении — на ветке `codex/merge-plan`.

[Handoff среза аудита](docs/plan/NEXT_AGENT_WEB_DEPENDENCY_AUDIT_2026-10-12.md),
[готовый prompt](docs/plan/NEXT_AGENT_WEB_DEPENDENCY_AUDIT_PROMPT_2026-10-12.md),
[запись о срезе](docs/plan/evidence/2026-10-12-web-dependency-audit/VALIDATION.md).

## Previous checkpoint — 2026-10-12: package I accepted technically; WORK-01 and CORE-04 verified

WORK-01 записан как `technically_verified` на коде `f41f9a8`. Модуль `workforce` стал
включаемым: компания получает его, только опубликовав конфигурацию с ним. CORE-04
записан как `technically_verified` отдельным коммитом `1b925f1` по основаниям пакета F.
ADR-0025 — Accepted as implemented. Решение: 2026-10-12 владелец поручил исполнителю
выбирать самостоятельно и на предложение выполнить приёмку ответил «Continue»;
трактовка записана в [записи о приёмке](docs/plan/evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md).

Проверки дерева приёмки: full local **PASS: 1531 passed, 4 skipped in 972.96s (0:16:12)**; Ruff, format и mypy PASS на
265 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS; независимая
проверка изменения PASS. CI коммита приёмки: **PASS**, [run 38236481277](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38236481277) на `75f2b9b`: задание 1037 с, pytest 899 с; текст логов не читался.
Production audit **FAIL: 2 high** (next, source-map-js).

Это техническая приёмка. Пилота и разрешения на production нет. PR и merge не
выполнялись; миграции и зависимости не менялись. Утверждения ниже о том, что
WORK-01 или CORE-04 planned, а workforce закрыт, относятся к своим датам.

[Handoff приёмки](docs/plan/NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md),
[запись о приёмке](docs/plan/evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md),
[независимая проверка](docs/plan/evidence/2026-10-12-work-01-acceptance/INDEPENDENT_CHECK.md),
[предыдущий срез: исправления и публикация](docs/plan/evidence/2026-10-12-i4-review-corrections/FOLLOWUP_VALIDATION.md).
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

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md),
[evidence и точные ограничения](docs/plan/evidence/2026-10-12-i4-review-corrections/VALIDATION.md).
Ниже сохранены исторические срезы. Их инструкции/результаты не заменяют текущий
handoff и не означают, что dirty corrections входят в HEAD490652b.

## Previous: I4 fixes re-reviewed; acceptance blocked by three findings — 2026-10-12

Local branch `codex/package-i4-review-2`, own managed checkout
`C:/Users/alexa/.codex/worktrees/package-i4-review-2/Gorgona Booking`, base `0356eb5`.
Read [review 2](docs/plan/evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW_2.md),
[measured evidence](docs/plan/evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW_2_CHECKS.json)
and the [updated continuation](docs/plan/NEXT_AGENT_PACKAGE_I_ACCEPTANCE_2026-10-12.md).

Review result FAIL: R2-1/P2, hidden-shift access through swap after same-home
reinvitation with no current profile; R2-2/P2, concurrent different-key cancels
leave 21 markers despite the cap of 20 (open/off/not-accepted); R2-3/P3, a valid
human reason `Clock-in` is hidden by the screen's string filter. Five targeted
checks fail across these three findings; no product correction was made.

Fresh PASS: 86 focused / 104.38s; standard browser 1 / 150.78s; timezone≠UTC and
company-wide addition browser 1 / 149.74s, desktop/mobile across three phases.
Static/web PASS, unit 102, pages 23; source hashes 16/16. Production audit FAIL
2 high. Full suite was not repeated in this review; earlier full C1 is a separate
snapshot. CI c6b8e34 is still success; exact local review-commit CI NOT TESTED.
Temporary probes restored/removed, own clusters stopped, runtime unchanged.

I-09 and I-12 now FAIL in the current plan. Correct the three findings on a new
branch with failing checks first, smallest coherent fixes, focused/full/static/web
and actual browser checks, then independent review and fresh evidence. WORK-01,
CORE-04 and workforce stay planned/closed. Owner policy/acceptance/publication
decisions remain pending. No push/PR/merge/deployment/production migration.

## Previous: Package I acceptance evidence prepared; no promotion — 2026-10-12

Continue from [the updated handoff](docs/plan/NEXT_AGENT_PACKAGE_I_ACCEPTANCE_2026-10-12.md)
and [the fresh matrix](docs/plan/evidence/2026-10-12-i-acceptance/ACCEPTANCE.md).
Local branch `codex/package-i-acceptance` starts at verified local/remote I4 head
`c6b8e341a7e88957ee5011e54e9aa06453b31b49`; changes are documentation/evidence only.
Read the final local documentation SHA from Git. The branch is not published.

Fresh PASS: complete PostgreSQL/browser-required suite 1506 passed / 4 skipped /
1026.84s; I4 three phases on desktop/mobile (six Playwright cases); Ruff/format/mypy
264; web typecheck/lint/format, unit 102 and build 23 pages. Exact-source CI c6b8e34
PASS: run 38204334830, job 114664366391, 1509 passed / 1 skipped / 595.96s, including
required container checks. Local container skips and the optional external site
remain NOT TESTED locally. Source hashes match 16/16; own clusters stopped.
Current production npm audit FAIL: 2 high (next, source-map-js).

I-01–I-11 PASS for recorded cases; I-12 conservatively BLOCKED pending a second
independent source review of a806380..b66eb41. The first review exists, but fresh
regression execution does not replace a source review of the fourteen fixes.
Package I is not accepted. WORK-01/CORE-04 and workforce readiness are unchanged;
migrations 0001–0035, code and dependency locks are preserved. Owner decisions on
the working plan/ADR, policy choices, acceptance/readiness, PRs and stack order
remain open. Exact-SHA CI for the new local documentation commit is NOT TESTED.
No push/PR/merge, deployment, production migration or CodeRabbit.

## Previous: colleague-shift visibility is a branch setting; branch published — 2026-10-11

Successor entry point: [handoff for the next agent: acceptance of package I, instructions and copyable prompts](docs/plan/NEXT_AGENT_PACKAGE_I_ACCEPTANCE_2026-10-12.md).
Owner decision of 2026-10-11 on the first open choice of I4: staff see colleagues'
published shifts by default, and the owner, a manager or the manager of that
branch may hide them. Same branch codex/package-i4-workforce-screens on the I4
record 5f0e58f; final code commit 419eda8097554c024cb76cde38fe901c386a5e29. Forward 0035
adds append-only branch setting versions with an SQL guard for the author and one
lock per branch; it is part of the packaged workforce approvals and of the
branch-policy restore. New routes: GET/PUT /workforce/locations/{id}/settings and
GET /workforce/my-changes/{id}/shifts (a participant reads the shifts their own
request names, also while browsing is hidden). Schedule has a Privacy section; My
shifts closes the swap choice and says why.
[Evidence](docs/plan/evidence/2026-10-11-i4-shift-visibility/VALIDATION.md),
[commands](docs/plan/evidence/2026-10-11-i4-shift-visibility/COMMANDS.md).
PASS: complete suite 1500 passed / 4 skipped / 953.19s on 419eda8; real browser on desktop and phone
1 / 103.56s; one race with an observed pg_locks wait; Ruff/format/mypy 263;
web unit 102 and build 23 pages. The owner allowed publishing this branch: it is
pushed; exact-commit CI of 5f0e58f is success (run 38132277248); CI of later heads
is read on GitHub. No PR. Independent review DONE on 2026-10-11 by a non-author:
no critical or high finding, two medium, seven low, seven notes
([review](docs/plan/evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW.md),
[author's response](docs/plan/evidence/2026-10-11-i4-shift-visibility/AUTHOR_RESPONSE.md)).
Fourteen of sixteen are fixed in b66eb41: a hidden branch now also refuses a new
swap, the outside-schedule mark follows the time in effect, discarding is limited
to 20 a day; two are documented and left to the owner. Complete suite after the
fixes: 1506 passed / 4 skipped / 2306.13s. A discarded key cannot write for the 24 hours its
receipt lives, not for ever. Containers, external site,
HawkScan, load/soak, deployment/production NOT TESTED. Inherited production npm
audit FAIL 2 high. WORK-01/CORE-04 and the workforce readiness lock are unchanged;
migrations 0001–0034 are untouched. No CodeRabbit.

## Previous: I4 implemented and locally validated — 2026-10-11

Successor entry point: [package I after I4: open items and copyable prompts](docs/plan/NEXT_AGENT_PACKAGE_I_REVIEW_2026-10-11.md).
Local branch codex/package-i4-workforce-screens on the I4 handoff
d22b61cf53612ab85c157c00ecd75fd1630ba1c2; final code commit
f4a7395e3ab9515e410143103142f44072af6cba. Three management screens over I1–I3:
Schedule, My shifts and Timesheets, on desktop and phone. Five small read and
outcome routes were added after failing tests; no migration. A lost answer is
settled with the server by the original key; the browser keeps identifiers only.
[Evidence](docs/plan/evidence/2026-10-11-i4-workforce-screens/VALIDATION.md),
[commands](docs/plan/evidence/2026-10-11-i4-workforce-screens/COMMANDS.md).
PASS: complete suite 1486 passed / 4 skipped / 907.37s on f4a7395; real browser on desktop and phone
1 / 92.97s; two cancel races with observed pg_locks waits; Ruff/format/mypy 261;
web unit 101 and build 23 pages. Independent review NOT DONE (the author's
re-read only). No push/PR; exact-commit CI, containers, external site, HawkScan,
load/soak, deployment/production NOT TESTED. Inherited production npm audit
FAIL 2 high. Migrations 0001–0034, WORK-01/CORE-04 and the workforce readiness
lock are unchanged. Package acceptance (matrix I-01–I-12) and publication remain
owner decisions. FIN-03 check stays a separate task. No CodeRabbit.

## Previous: I3 implemented and locally validated — 2026-10-11

Successor entry point: [I4 handoff and copyable prompt](docs/plan/NEXT_AGENT_PACKAGE_I4_2026-10-11.md).
Verified I3 code commit: `ec9524aa77d0d26fee7253380d226f394cc587fd`.
The handoff is a separate documentation change; I4 is not started here.

Local branch codex/package-i3-timesheets on I2
49276bf800eb929589785e192db489e17ac77fa7. Forward0034 adds own start/end/breaks,
immutable corrections/decisions, last-approved effective time, stable-user
one-open/overlap protection and original-revision replay. Own closure/history
work when workforce is off. No journal or shared occupancy is created.
[Evidence](docs/plan/evidence/2026-10-11-i3-timesheets/VALIDATION.md),
[independent source review](docs/plan/evidence/2026-10-11-i3-timesheets/INDEPENDENT_REVIEW.md).
PASS: final focused76/67.46s, Ruff/format/mypy254,
web94/build and corrected-source review14 SHA matches. All17 I3 races require
observed pg_locks waits. Four SQL/state findings reproduced and fixed.
Full I3 suite PASS:1473 passed / 4 skipped / 832.46s.
Migrations0001–0033, WORK-01/CORE-04 and workforce readiness remain unchanged.
No push/PR; exact-commit CI, I4 screens, containers, deployment/production and
load/soak NOT TESTED. Inherited production npm audit FAIL2 high.
Next slice I4 and package acceptance remain. FIN-03 check stays a separate task.
No CodeRabbit.

## Previous: I2 implemented and locally validated — 2026-10-10

Local branch codex/package-i2-shift-changes on I1
69270cc8bfdfb763cc8f5fc9b7892b13db987bce. Forward0033 adds handover, swap and
home-open pickup with explicit consent, manager approval, exact skill snapshots,
atomic shared occupancy and original-event receipt replay. No new dependency.
[Evidence](docs/plan/evidence/2026-10-10-i2-shift-changes/VALIDATION.md),
[independent source review](docs/plan/evidence/2026-10-10-i2-shift-changes/INDEPENDENT_REVIEW.md).
Focused156/114.89s plus six replacement-skill cases/7.48s, Ruff/format/mypy248,
web94/build and corrected-source review PASS. Full suite PASS:
1380 passed / 4 skipped / 738.66s. All ten races require observed pg_locks waits.
Independent findings reproduced and fixed: hidden prior resource release under
RLS and foreign self pickup. Migrations0001–0032 unchanged. WORK-01/CORE-04 and
the workforce readiness lock remain unchanged. No push/PR; exact-SHA CI,
containers (3 skip), external site (1 skip), deployment, production and load/soak
NOT TESTED. Inherited production
npm audit FAIL:2 high nodes. I3 timesheets, I4 screens and package acceptance
remain; the FIN-03 acceptance check is a separate task. No CodeRabbit.

## Previous: I1 implemented and locally validated — 2026-10-09

Branch codex/package-i1-workforce from I0 14190730. Forward0032 adds
membership profiles sharing a stable user resource, versioned skills and shifts,
atomic shared occupancy assignments, typed API, permission6 and fail-closed
schema approval. [Evidence](docs/plan/evidence/2026-10-09-i1-workforce/VALIDATION.md),
[independent review](docs/plan/evidence/2026-10-09-i1-workforce/INDEPENDENT_REVIEW.md).
Focused 81/45.49s, Ruff/format/mypy 239 and web 94/build PASS; independent final
code review PASS. Full project suite PASS: 1301 passed / 4 skipped / 772.12s.
The first full run failed with DiskFull and remains preserved in the evidence.
Three container tests and one external-site test remain NOT TESTED.
WORK-01/CORE-04 unchanged;
workforce remains closed outside test readiness overrides. No push/PR/CI,
deployment, production migrations, cloud or provider action.
I2 changes, I3 timesheets, I4 screens and acceptance remain. Staff home transfer
is a separate lifecycle; unsafe moves fail closed. Inherited npm production
dependency audit reports2 high nodes, not repaired by I1.

## Previous: package I started, plan and slice I0 — 2026-10-09

[Handoff and copyable prompt](docs/plan/NEXT_AGENT_PACKAGE_I_2026-10-09.md),
[progress against the master plan](docs/plan/PROJECT_PROGRESS_2026-10-09.md),
[package I plan](docs/plan/PACKAGE_I_PLAN_2026-10-09.md),
[ADR-0025](docs/adr/0025-workforce-shifts-and-timesheets.md),
[slice I0 inventory](docs/plan/evidence/2026-10-09-i0-resource-kinds/INVENTORY.md).
Package I (shifts, shift changes, timesheets; WORK-01) has a plan and ADR-0025.
The owner did not approve them explicitly but delegated the choice of next
steps, so the recommended options are working defaults. Slice I0 on
`codex/package-i0-resource-kinds` changes no schema or source: seven tests pin
what booking, reservations and staff setup do with resource kinds today, and the
inventory lists what slice I1 must change with the planned `staff` kind. Full
local run: PASS, 1238 passed / 4 skipped / 644.59 s. WORK-01 and the `workforce` module stay planned; no
shift, change or timesheet code exists. The package I branches are local.
Package H is described in the next section; its draft PR and the independent
check of the acceptance commit are still open. No
merge/deploy/production/provider/funds action.

## Previous: package H technically accepted (FIN-03) — 2026-10-09

[Handoff and copyable prompt](docs/plan/NEXT_AGENT_H_ACCEPTANCE_2026-10-09.md),
[audit](docs/plan/evidence/2026-10-09-h-acceptance-audit/AUDIT.md),
[acceptance record](docs/plan/evidence/2026-10-09-h-acceptance/ACCEPTANCE.md).
H1–H4 are implemented at `319f144` on `codex/package-h4-ui-admission`:
migrations 0021–0031, the H API and the Financial documents and Provider
admission screens. Draft PR15–PR22 are stacked and open; nothing is merged.
Exact-SHA CI for `319f144` is success (push 37876007880, pull_request
37876031010); its steps build the web app and the production image and run
PostgreSQL 18, Ruff, mypy and pytest.
Independent audit on a separate checkout and cluster: full local suite
1231 passed / 4 skipped / 662.06 s with mandatory PostgreSQL and browser;
Ruff/format/mypy 230 and web gates PASS; four SQL guard mutations were all
caught. No money defect was found. Findings A-01–A-11 are in the audit; the only
P2 (provider admission is writable with `finance` alone) is closed by the
owner's decision of 2026-10-09: no code change, H4 is not deployed before H
acceptance, admission is accepted together with H.
**FIN-03 is `technically_verified` by the owner's decision of 2026-10-09** on
code `319f144`. `finance_documents` is enableable by a company's own published
configuration and the test-only readiness overrides are removed. Full local run
on the acceptance tree: 1231 passed / 4 skipped / 666.05 s. ADR-0024 is
Accepted. FIN-02 remains planned. Branch `codex/package-h-acceptance` holds the
audit `71359f9` and the acceptance commit `ec39622`; it was pushed on 2026-10-09
by the owner's decision and exact-SHA CI for `ec39622` is success (push
37887856597). No draft PR is open for it yet (GitHub sign-in needed); an
independent check of the acceptance commit is NOT DONE.
No merge/deploy/production/provider/funds action. The sections below are
historical snapshots.

## Historical H2 backend handoff — 2026-10-07

[Full successor handoff](docs/plan/NEXT_AGENT_H2_2026-10-07.md),
[copyable prompt](docs/plan/NEXT_AGENT_PROMPT_H2_2026-10-07.md),
[changed files/checks/limits](docs/plan/evidence/2026-10-07-h2-settlements/VALIDATION.md).
Branch codex/package-h2-settlements from the delivered H1 backend 75e809b.
**Published in [draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16), target H1 PR15; no merge.**
Original eight docs committed/pushed as75c36da; final docs are a successor.
Read actual final HEAD/origin/current-head CI in PR16/exported delivery state.
Corrective source `15edbed1d608ada9d0901a7710c00eff28c23e71` fixes a diagnosed ledger refresh race in two web files;
financial Python/SQL and frozen migrations are unchanged from54852b4. [CI37578255793](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37578255793) PASS:1044 passed/1 skipped/379.86s;
all3 Docker/image, PG/browser, web69/2.3s and static211 PASS.
Fresh local full:1041 passed/4 skipped/434.68s; focused browser1/17.95s.
Bounded independent UI review PASS; full H2 money/state review remains NOT DONE.
Forward 0022–0024 add manual accruals as new obligations, settlement documents
with approval/reserve/sent/release/cancel, and externally attested partial
confirmations that move exactly R→P with one balanced journal and a permanent
external identity. PostgreSQL and the service both enforce P+C+R<=A at commit.
Historical author full suite1041/4/459.51s; fresh corrective results are above.
Mandatory PostgreSQL18.6 and browser;
Ruff/format/mypy211 and web gates PASS. Exact-checkpoint CI75c36da
[37573680437](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37573680437) PASS:1044 passed/1 skipped/381.36s; all3 Docker/image,
PG/browser, 69 web tests/2.3s and static211 PASS.
Independent money/state review NOT DONE; HawkScan was not run.
FIN-03/02 remain planned and finance_documents unavailable. H3 credits, refund
obligations and corrections and H4 UI/admission remain unfinished.
Owner/E2 dirty trees preserved; own cluster 51462 stopped.
No merge/deploy/production/provider/funds action. The H1 section below is
superseded for continuation; its evidence remains snapshot-specific.

## Historical H1 backend handoff — 2026-10-06

[Full successor handoff](docs/plan/NEXT_AGENT_H1_BACKEND_2026-10-06.md),
[copyable prompt](docs/plan/NEXT_AGENT_PROMPT_H1_BACKEND_2026-10-06.md),
[changed files/checks/reviews](docs/plan/evidence/2026-10-06-h1-backend/VALIDATION.md).
Delivery branch codex/package-h1-persistence; reviewed source2d5a8f9 from
foundation18e3f5e. [Draft PR15](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/15)
targets PR14. Read exact current delivery HEAD/CI there.
Real forward0021 and invoice API persist one immutable issue, principal
obligation and G accrual atomically; minimal permanent recovery and explicit
journal-v2 are implemented. Root953/4skip/378.14s, Ruff/format/mypy204 PASS;
independent corrective review47 PG/109 units PASS, H1-R01 closed.
FIN-03/02 remain planned and finance_documents unavailable. H2 settlement/
manual accrual, H3 credits/refunds and H4 UI/admission remain unfinished.
Owner/E2 dirty trees preserved; own root51456 and review51460 stopped.
No merge/deploy/production/provider/funds action. Historical foundation below
has been superseded for continuation; its evidence remains snapshot-specific.

## Historical H1 foundation — 2026-10-06

Owner continued local work and explicitly approved H1 source publication.
[Draft PR14](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/14)
targets planning PR13. Delivery branch codex/package-h-invoices; reviewed
source843d0b3, checkpointda3966b. Exact-head CI37534227319 PASS909 passed/
1 optional skip with PG/browser/Docker and build. This handoff update is a
docs-only successor; refresh current PR14 head/CI.
[Copyable successor prompt](docs/plan/NEXT_AGENT_PROMPT_H1_2026-10-06.md).
Read [H1 handoff](docs/plan/NEXT_AGENT_PACKAGE_H1_2026-10-06.md) and
[checks/boundaries](docs/plan/evidence/2026-10-06-h1-foundation/VALIDATION.md).
Strict contracts, pure allocation math and planned finance_documents/registry2
are implemented. H1 workflow is IN PROGRESS; actual H SQL/API/UI is not built.
FIN-03/02 remain planned; G acceptance and old published configurations remain.
Earlier planning/review statements below describe their own snapshots.

## Historical H planning snapshot — 2026-10-06

Own branch codex/package-h-finance-plan from G head5be6e7a.
Read [H handoff](docs/plan/NEXT_AGENT_PACKAGE_H_2026-10-06.md),
[H plan](docs/plan/PACKAGE_H_PLAN_2026-10-06.md) and
[ADR-0024 Proposed](docs/adr/0024-invoices-obligations-and-external-settlements.md).
Docs only: typed invoices/obligations/settlement reserves, externally attested
partial payments, credits/refund obligations and admission requests are proposed.
No H money code/schema/provider activation; FIN-03/02 remain planned.
Independent proposed-design review PASS; owner scope confirmation remains
pending before code. [Review/check evidence](docs/plan/evidence/2026-10-06-package-h-plan/VALIDATION.md).
G finance remains technically verified; its exact-SHA CI is not H validation.

## Current G continuation — 2026-10-06

Read [package G handoff](docs/plan/NEXT_AGENT_PACKAGE_G_2026-10-06.md) and
[fresh evidence](docs/plan/evidence/2026-10-06-ledger/ACCEPTANCE.md).
Branch codex/package-g-ledger-review from accepted stage-2 plan 151472a;
own checkout under .codex/worktrees/package-g-ledger-review/Gorgona Booking.
The original gorgona-e2-documents and owner checkout are preserved.
Ledger books/accounts/double entry/reversals/periods/trial balance and real API/UI
are implemented. The early-SET-CONSTRAINTS balance bypass was reproduced and fixed.
All seven independent findings are closed, including unexpected permissive SQL policies.
Evidence code 95a0de4: full local 858 passed/4 skipped, exact-SHA CI 861 passed/1 skipped
with required Docker gates; independent final guard-delta code/unit review PASS.
Fresh accepted-registry focused: 68 Python and 4 desktop/mobile browser flows,
without positive readiness overrides; 68 web unit tests PASS. Recovery and safe cancellation prevent
the delayed original from running after an unresolved request is cancelled.
Finance/FIN-01 are technically verified by a separate acceptance commit. A new
configuration publication enables finance; no existing configuration is changed.
Check the fresh acceptance HEAD CI in draft PR #12; evidence names source SHA and review boundaries.
No merge, deployment, production migration, providers or Azure changes.
Older continuation sections below are historical for their own code versions.

## Current E2-A continuation — 2026-10-05

Read [E2-A handoff](docs/plan/NEXT_AGENT_E2_FILE_VALIDATION_2026-10-05.md) and
[evidence](docs/plan/evidence/2026-10-05-file-validation/ACCEPTANCE.md).
Branch codex/package-e2-file-validation from accepted E1 3983dd4. This increment
is the bounded file-profile/CSP prerequisite, no storage/API/UI/migration or
documents readiness promotion. Continue E2 persistence/integration per ADR0020/0021,
then E3 and CORE-04. Owner dirty checkout is preserved; no production action.

## Current E1 continuation — 2026-10-05

Read [the E1 handoff](docs/plan/NEXT_AGENT_PACKAGE_E1_2026-10-05.md) and
[acceptance](docs/plan/evidence/2026-10-05-counterparties/ACCEPTANCE.md) first.
Current branch codex/package-e1-counterparties builds on audited E0 bbe6ecd and
targets that branch in its own draft PR. Owner checkout remains untouched.
Versioned counterparties/contacts, explicit duplicate decisions and manual booking
links are implemented; E2 documents/files and E3 agreements are next, then CORE-04.
Code 2392566595a2df59f8ec3f073ed9bf184df6447f has green exact push/PR CI (599/1);
a separate acceptance promotes counterparties to technically_verified. Registry v1
and booking-only baseline remain unchanged; each business explicitly publishes it. Local API/browser/static gates passed with explicit
container/external-site skips; production/providers/Azure/load remain unverified.
The October-4 continuation and earlier counts below are historical, not current
code acceptance. Preserve all 39 profiles, 28 criteria and generic booking.

## Current continuation — 2026-10-04

The owner authorized correction of the complete universal-business plan and the start of implementation. Read [the corrected master plan](docs/plan/GORGONA_MASTER_PLAN.md) and [implementation evidence](docs/plan/GORGONA_IMPLEMENTATION_STATUS.md) first. Preserve all 39 industry profiles and existing generic booking workflows. `business_id` is the existing tenant boundary; multiple profiles do not create duplicate companies. GORGONA supplies software, including inventory and transport tools for its customers, without operating its own warehouse or carrier.

The current repository develops GORGONA only. KA Nails is a separate project, outside this implementation and release scope. The first-tenant proposals and brand instructions below are historical context; do not treat them as current tasks or platform acceptance requirements.

The [2026-10-04 plan-conformance audit](docs/plan/GORGONA_PLAN_AUDIT_2026-10-04.md) maps all 28 acceptance criteria. Stage 1 is partial. A confirmed security issue in the old development hold endpoint has been corrected: `/v1/holds` is registered only in local/test/CI, while hosted bookings retain the customer validation/capability path. The linked audit records the failing regression, fresh focused PASS and independent review; compare every later CI result with its exact commit.

Azure is the accepted deployment direction ([ADR-0012](docs/adr/0012-azure-hosting.md)); the OCI proposal below is historical. Production actions still require their acceptance gates and owner authorization. Begin with baseline defects, then the typed business foundation and shared resource/financial/material invariants. No provider approval or production readiness is implied by this handoff.

Baseline at the start of this work: clean checkout at `76ce4e52f1c19b176586c8f69e55d4df735d1a1e`. Prior results on that unchanged version were 151 API tests passed, 12 AI tests passed, 17 AI tests skipped, and web type checking passed. Rerun relevant checks after changes; do not reuse these as evidence for a new tree.

The current implementation also includes location-scoped booking/resource operations, branch invitations, legacy command-receipt compatibility and a fail-closed PostgreSQL access-definition guard. Read [ADR-0014](docs/adr/0014-location-scoped-workspace.md) and the latest [next-agent handoff](docs/plan/NEXT_AGENT_HANDOFF_2026-10-04.md) before continuing. No industry-wide or production readiness is implied.

## Historical handoff — 2026-09-30 (preserved reference)

The sections below describe the original proposal, audit and later repository separation. They are not current deployment instructions or current implementation status. The current continuation, master plan and accepted ADRs take precedence.

Prepared 2026-09-30. This document is the starting context for the next coding environment. Read it before writing application code. The complete local project is this repository; all paths below are relative to its root.

## Objective and scope

Build a reusable, tenant-aware appointment platform named **GORGONA Booking AI** with **KA Nails** as its first tenant. The customer-facing KA Nails experience should follow the supplied official logo. Implement a deterministic booking system before the AI concierge. This handoff is Phase 0 audit/design; do not report the product as implemented.

The owner asked for a new GitHub project and considered Cloudflare/Supabase. They then asked whether **Oracle server could replace Supabase and Cloudflare**. Proposed direction: OCI-hosted web/API plus PostgreSQL, with Cloudflare optional for DNS/CDN/WAF. This is an architecture proposal, not a deployed system. The owner explicitly chose **not** to pause existing Supabase projects; the new Supabase project is deferred. Preserve existing GORGONA/Fresh Nails services and data.

## What exists here

- `assets/brand/ka-nails-logo.png`: exact supplied logo; SHA-256 `BB2FE1C05EB7183B8B8F55EEE861B06D80256CF5349B2958E1432FA3B83FBF53`.
- `source/PRODUCT_BRIEF.txt`: complete pasted owner brief, copied verbatim for full context. The later OCI/deferred-Supabase decisions in this handoff take precedence.
- `docs/architecture/INITIAL_AUDIT.md`: evidence and limitations from the two owner-controlled Fresh Nails reference repositories.
- `docs/architecture/TARGET_ARCHITECTURE.md`: proposed OCI-first modular monolith and decision list.
- `docs/architecture/DATA_MODEL.md`, `BOOKING_ENGINE.md`, `MULTITENANCY.md`, `SECURITY_MODEL.md`, `AI_TOOL_MODEL.md`: domain, trust and concurrency contracts.
- `docs/architecture/DESIGN_SYSTEM.md`, `ANALYTICS.md`, `OBSERVABILITY.md`, `RELEASE_PLAN.md`: customer experience and quality gates.
- Local Git repository on `main`, with no external remote until account access is restored.

## Verified findings and blockers

1. This task's starting folder had no Git repository. The owner's accessible GitHub account is `alexeyalexandrov2026-tech`. `Fresh-Nails` is a Vite/React marketing site with static JSX prices and Square links. `Fresh-Nails-AI-Receptionist-by-Gorgona-One-AI` is a separate Next.js/Dify/Supabase chat project. Neither is a KA Nails booking core. They were cloned read-only into this task's `work/` folder, outside this deliverable.
2. The old OCI `gorgona-node` was recorded as **TERMINATED** in a prior audit. On 2026-09-30, `oci iam region-subscription list --profile GORGONA --auth security_token` failed because the session expired. No current VM, cost, IP, SSH access or deployed application was verified. Do not target historical IP `150.136.90.12`.
3. Supabase organization `Gargona One` is free; creation reported $0/month but failed because its owner has reached the two active free-project limit. Active projects are `gorgona-camera-feed` and `Gorgona-one-claude`. The owner chose to keep both running and defer the new project.
4. The GitHub connector lacks a create-repository operation. GitHub's in-app page was unauthenticated and Git Credential Manager supplied no reusable credential. No GitHub repo or remote exists for this project. Cloudflare's in-app page was also at sign-in. No Cloudflare project or DNS change was made.
5. The product brief refers to a separate GORGONA/KA Nails architecture image, but only the logo image and text brief were available. Authentic KA Nails photos, domain, address, schedule, staff, legal/policy wording and the base Hammam booking duration were not supplied/verified.

## Next execution sequence

1. Reconcile owner decisions: confirm OCI compartment and current host plan, budget, domain, business timezone, staff/hours, service durations, deposit/cancellation/tax rules, photo rights and whether Square remains temporary booking. Do not infer these from Fresh Nails.
2. Renew OCI browser security-token session using `GORGONA` profile; list current instances/compartments and verify exact target. No VM restart, infrastructure creation or production deployment before cost, blast radius and rollback are reviewed with owner. Do not create an OCI API signing key by default.
3. Once GitHub login is available, create a **private** `gorgona-booking-ai` repository under the owner's chosen account, add its URL as `origin`, push the reviewed local `main`, and verify GitHub file/hash parity. Do not push cloned Fresh Nails references, secrets or task `work/` files.
4. Turn the approved architecture into ADRs, exact migrations, typed API contracts and tests. Implement tenant/catalog and staff/scheduling first; then transactional holds and appointments. Use PostgreSQL `tstzrange` + GiST exclusion for exclusive resources; the 100-concurrent-attempt acceptance is one success and 99 typed conflicts. Keep the AI outside booking authority.
5. Set up isolated staging on verified OCI infrastructure, private PostgreSQL, TLS, backups/PITR, restore drill, telemetry and CI before production. Cloudflare remains optional. Do not turn on a public booking CTA until it reaches a real validated booking/payment flow.

## Product facts from supplied brief that may be seeded after owner validation

- Hammam Luxury: $145; heel care and ritual included; gel not included.
- Hammam Luxury + Gel: $160, public duration range 120–145 minutes.
- Hammam Luxury + Gel French: $175, public range 130–155 minutes.
- Extra Foot Massage: +$20 and exactly +15 minutes booking time.
- Other Salon Gel Removal: +$15, subject to staff assessment when required.
- Hammam Spa Upgrade: +$40 only for compatible pedicures; must not stack with Hammam Luxury.
- French Gel: +$15 and only with compatible gel service.
- Base Hammam deterministic booking duration is **unknown**. Do not invent one or publish it as bookable.

## Security and release rules

No browser service-role credentials; trusted tenant context; composite tenant foreign keys and RLS; verified payment webhooks and idempotency; transactional outbox; structured, redacted logs; tested restore. AI tools are typed, tenant-scoped, policy-checked and have no arbitrary SQL/shell/HTTP access. Preserve human correction and audit history. Treat tests and live validation as separate evidence, and keep the status labels PASS / FAIL / BLOCKED / NOT TESTED.

## Suggested first prompt in Cloud Code

> Open this repository and read `CLOUD_CODE_HANDOFF.md` and every file in `docs/architecture/`. Treat the supplied KA Nails logo as the brand source. First verify Git state and the current OCI/GitHub access. Do not reuse Fresh Nails as KA Nails source. Make a detailed, testable M1 plan for an OCI-first modular monolith, identify owner decisions and deployment gates, and implement only the next approved, reviewable slice. Do not claim application or infrastructure completion from these design documents.

## Repository separation update (30 September 2026)
The logo source paths above record Phase 0 provenance. The unchanged PNG now belongs to the independent KA-nails repository at `public/assets/ka-nails-logo.png`; the old bytes remain in Git history. Platform origin is `alexeyalexandrov2026-tech/-GORGONA-Booking-Platform`. No push or deployment was performed. See `docs/architecture/REPOSITORY_SEPARATION.md`.
