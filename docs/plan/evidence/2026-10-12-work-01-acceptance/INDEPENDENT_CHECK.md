# INDEPENDENT_CHECK — запись WORK-01 и CORE-04 как `technically_verified`, модуль `workforce` открыт для включения

**Вердикт: PASS.** Блокирующих находок (P1) нет. Есть две находки P2, которые стоит закрыть до коммита, и пять заметок P3. Полный последовательный прогон (accept-full) на момент проверки не закончился.

## Область и способ

- Проверялась неотправленная правка в рабочем дереве, `git diff HEAD -- api web`, семь файлов. База: ветка `codex/package-i4-review-corrections`, HEAD `678a21e`. Заглушку `docs/plan/evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md` (126 байт, «Record in preparation») только отмечаю, её текст не оценивается.
- Проверка шла строго на чтение, 2026-10-12. Её выполнил агент-ревьюер, который это изменение не писал. Использовались чтение файлов, grep и read-only git (`diff`, `show`, `log`, `ls-tree`, `merge-base`, `rev-parse`). Код, тесты, сборки и сеть не запускались, дерево не менялось. Логи прогона прочитаны как есть.
- Полный прогон `accept-full` шёл (`pytest-full.log` на 05:53, около 18%). Я его не ждал и его результат не использую.

## Находки

1. **P2. Текст модуля ссылается на ADR, который сам себя называет непринятым.**
   - Место: `api/src/gorgona_booking/business/modules.py:138` («per-branch setting … (ADR-0025)»).
   - В `docs/adr/0025-workforce-shifts-and-timesheets.md:3` статус: «Proposed (2026-10-09); not explicitly approved».
   - Образец `ec39622` в том же коммите перевёл ADR-0024 в Accepted.
   - Нужно одно из двух. Либо решение владельца и смена статуса ADR в этом коммите. Либо убрать ссылку или написать «ADR-0025, предложен». Это текст каталога модулей, его видят компании.
2. **P2. Запись ссылается на заглушку, а соседние документы утверждают обратное.**
   - Место: `readiness_registry.py:205-213` (evidence WORK-01) и `modules.py:139`.
   - Тест `test_configuration_contracts.py:126-131` проверяет только существование файла, поэтому заглушка пройдёт все тесты. Файл к тому же не в индексе git (`??`), и без `git add` проверка существования упадёт в CI.
   - До коммита нужно закончить ACCEPTANCE.md и привести к одному виду утверждения «WORK-01/CORE-04 planned, workforce закрыт» в `docs/plan/GORGONA_MASTER_PLAN.md:16,37` и `docs/plan/GORGONA_IMPLEMENTATION_STATUS.md:16,37,71,95`. Те же утверждения есть в передаточных файлах и в плане пакета I (grep по `WORK-01/CORE-04`, правила docs/DEVELOPMENT.md).
3. **P3. Формулировка `scope` у CORE-04 неточна.** Место: `readiness_registry.py:154-159`.
   - «Bookings and staff reservations of one or more resources» читается так, будто запись тоже многоресурсная. На деле запись одноресурсная (`modules.py:123-124`, `evidence/2026-10-05-occupancy/ACCEPTANCE.md:79`).
   - «the stage 1 record accepted it» читается как приёмка владельца. Запись stage 1 говорит «technical PASS only» (`2026-10-06-stage1/ACCEPTANCE.md:9-12`).
   - Не названы пределы из `occupancy/ACCEPTANCE.md:39-44,79-84`. Прежние записи до 0018 попадают в общую таблицу только после `backfill-occupancy` по компании. `resource_blocks` остаются отдельно. Прошедшие резервации принимаются.
   - Предлагаю «bookings of one resource and staff reservations of one or more resources» и «the stage 1 record lists it as a technical PASS».
4. **P3. `scope` у WORK-01 не называет известные пределы.** Место: `readiness_registry.py:202-210`.
   - Не упомянуты непроверенные ситуации: настоящий screen reader, потерянный ответ на смену Privacy, 5xx/нечитаемая запись, списки больше страницы, более 20 версий, смена часов внутри смены, My shifts при UTC≠local. Они перечислены в `2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW_2.md:214-216` и `2026-10-12-i-acceptance/ACCEPTANCE.md` (раздел NOT TESTED).
   - Не сказано, что нет проверки трудового законодательства и нет связи смен с доступностью записи клиентов (`PACKAGE_I_PLAN_2026-10-09.md:308-315`, решение 2).
   - Последние исправления `2bca502` смотрел «ограниченный независимый обзор» девяти файлов (`INDEPENDENT_REVIEW.md:3`) и обзор исполнителя, автора окружающего кода (`CORRECTIONS_REVIEW_FOLLOWUP.md:6-12`). В `scope` стоит просто «independent reviews».
   - Минимум: раздел NOT TESTED в ACCEPTANCE.md и одна фраза в `scope`.
5. **P3. Устаревший текст в спеке.** Место: `web/tests/workforce.spec.ts:212`.
   - Причина пропуска «needs the fixture's opened readiness» больше неверна: фикстура реестр не открывает.
   - В описании правки сказано «переименованы заголовок и причина одного теста». Вторая причина осталась.
6. **P3. Состояние «принят, но не опубликован» (теперь состояние по умолчанию) проверено уже, чем остальные.**
   - Через API без публикации проверена одна запись, PUT skills (`test_workforce.py:49-77`). Остальные маршруты проверены в состоянии «включён, затем выключен». Код для «нет строки» и «строка выключена» общий: `configurations.py:461-463`, SQL `0015:16-22`, `0034:108,169`.
   - В браузере фаза closed идёт с отозванной приёмкой, то есть в состоянии `not_accepted`, которого у настоящей компании не будет. Состояние `module_disabled` без профиля и записей, с текстом «Scheduling is turned off…» (`web/components/workforce-shared.tsx:344`) для компании, которая модуль никогда не включала, в браузере не проверялось.
7. **P3. `resolve` и `cancel` не привязаны к модулю.** Место: `api/workforce_desk.py:109-130`, `business/workforce_desk.py:283-356`.
   - Любой активный участник с `WORKFORCE_SELF` (все роли, `permissions.py:36-44`) может в компании, где workforce не включали, оставить до 20 отмен за сутки на человека, то есть квитанции и аудит.
   - Поведение не изменено этим diff: оно было и при непринятом модуле. Текст `stops` этого не отрицает. Параметризованный тест `test_workforce_review2_fixes.py:139` покрывает open, off и not_accepted, но не «никогда не включали».

## Что проверено / исход

| Раздел | Что проверено | Исход |
|---|---|---|
| A. CORE-04 | Критерий `MASTER_PLAN:861`. `occupancy/ACCEPTANCE.md:46-84`: «technically verified locally and in CI», CI на `bf3645d`, независимый обзор (3 medium, исправлены тестами). `stage1/ACCEPTANCE.md:21`: PASS. `bf3645d` и `ed7884e` — предки HEAD. `ed7884e` меняет только документы (`git diff bf3645d ed7884e -- api web .github` пуст). | Подтверждено. Обзор шёл до исправлений, повторного обзора в записи нет. Поэтому `scope` («an independent review») верен, а формулировка задания «обзор на bf3645d» сильнее записи. |
| A. Схема и дата | На `bf3645d` последняя миграция — `0019_resource_reservations.sql`, значит `schema_version=19` верна. `verified_on=2026-10-06` совпадает с UTC-датой `bf3645d` (03:58Z) и `ed7884e` (04:04Z). | Верно, дата защитима. |
| A. Влияние на работу | `CORE-04` встречается в `api/src` только в реестре. `modules.py:134,179` берут статус лишь у WORK-01 и FIN-03. | Поведение не меняется. Изменится лишь ответ `GET readiness-registry` (`api/configurations.py:59`). |
| A. «Аренда» | Критерий требует «новую аренду». Доказана служебная резервация. `scope` прямо говорит «No rental workflow, no capacity above one, no production approval». | Не завышено при сохранении этих оговорок. См. находку 3. |
| B. WORK-01 | Критерий `:866`, матрица I-03/I-04/I-07. `PUBLICATION_CHECKS.json`: прогон 38227457763 на `f41f9a8`, success, шаг `uv run pytest` success (1008 с). `git diff f41f9a8 HEAD -- api web .github` пуст, различаются 12 файлов документов. Последняя миграция 0035, `schema_version=35` верна. | Подтверждено. `scope` совпадает с кодом (смены и назначения в общей занятости, передача, обмен и открытая смена с согласием получателя и утверждением менеджера `0033:8,294,319`, табель, настройка филиала `0035`). Пробелы в пределах — находка 4. |
| B. Пути evidence | `FOLLOWUP_VALIDATION.md` в индексе. `ACCEPTANCE.md` — незафиксированная заглушка. | См. находку 2. |
| C. Тексты | Остановка записей: `workforce.py:47-61`, `shift_changes.py:85-93`, `workforce_desk.py:54-62`, `timesheets.py:111-112`. Дублируется триггерами `0032:374-569`, `0033:403-430`, `0034:105-110,166-171`, `0035:52-53`. Закрытие записи: `timesheets.py:212` (`closing`) и `0034:163` (кроме `clock_out`), а `clock_out` закрывает и открытый перерыв (`0034:230-234`). Разбор и отмена команды: код выше. Чтения: `_access` модуль не проверяет. | Неподдержанных утверждений нет. Побочное наблюдение: перерывы (`break_start`/`break_end`) и отказ (`decline`) тоже остановлены, но в `stops` не названы. После закрытия при выключенном модуле запись остаётся `proposed`, пока модуль не включат. |
| D. Замок | Все пути записи начинаются с `require_workforce`. Без публикации строки в `business_module_states` нет, и `module_enabled` даёт false (`configurations.py:461-463`), то есть `MODULE_DISABLED`. SQL-замки есть на всех таблицах 0032, 0033, 0035 и встроены в сторожей 0034. Diff не трогает SQL, RLS, маршруты и права (`WORKFORCE_READ`/`WORKFORCE_MANAGE` только у manager и owner, не делегируются, `permissions.py:55-62,87-91`). `MODULE_REGISTRY_VERSION` остаётся 2. | Замок цел. Опубликованные конфигурации не меняются: единственный писатель состояний — публикация (`configurations.py:427`). Исключение: находка 7. |
| E. Тесты | Сравнены до и после. `MODULE_NOT_READY` для снятой приёмки сохранён (`test_workforce.py:71-77`, `test_configurations.py:704-741`, `test_i4_browser.py:176-183`). «Принят, но не опубликован» теперь даёт `MODULE_DISABLED` (`test_workforce.py:69-70`). `analytics`: optional, planned, зависит от `organization`, ожидаемый набор проблем ровно один. | Ничего не ослаблено. Патч «отозвано» активен ровно вокруг `browser("closed")`, затем снимается, и `publish(1,…)` идёт на настоящем реестре. Остаточные открытия в `api/tests`: `module_support.py:23-24` (`verified_modules`, нигде не используется, был таким и до правки) и `ledger_support.py:11` (только закрывает finance). Патчи «снять приёмку» в `test_workforce_desk.py:97`, `test_shift_changes_guards.py:485`, `test_timesheet_guards.py:219`, `test_workforce.py:477`, `test_workforce_review2_fixes.py:167` по-прежнему нужны. Старых допущений о закрытости workforce в тестах и в `docs/DEVELOPMENT.md` не найдено, кроме находки 5. |
| F. Логи | `runner.py:31` ставит `PYTHONPATH` на проверяемую копию. Во всех этапах `source_unchanged_during_run=true`. | См. следующие четыре строки. |
| F. red | `accept-red/focused.log:167`: 5 failed, 15 errors, 32 passed. Ошибки — `MODULE_NOT_READY` в фикстуре `workforce`. Падения — два юнит-теста, `test_lifecycle…`, `test_workforce_is_admitted…`, `test_accepted_workforce…`. | Ожидаемо, посторонних падений нет. Сравнение CORE-04 в сводном юнит-тесте упало бы на WORK-01 раньше (`:117-123`) и отдельно красным не показано. |
| F. green | `accept-green/focused.log:13`: 828 passed (весь `tests/unit`, `test_configurations.py` и файлы workforce, shift_changes, timesheets). | Зелёно. Не входят `test_resource_kind_boundaries.py` (единственный потребитель общей фикстуры вне списка) и `test_resource_occupancy.py` / `test_resource_reservations.py` с тестами CORE-04. |
| F. браузер | `accept-browser/focused.log`: фазы closed, enabled, off — по 2 passed (desktop и mobile). Итог: 6 passed, `test_i4_browser` и `test_management_browser`. | Фаза closed идёт под отозванной приёмкой. |
| F. статика | `accept-static/results.json`: ruff check и format, mypy (265 файлов), web typecheck, lint, format, unit, build — exit 0. `web-audit` — exit 1. | Всё зелёное, кроме унаследованного `npm audit` (2 high по production-зависимостям, как и раньше). |
| G. Прочее | `git diff HEAD --check` — чисто. Семь файлов diff согласованы с описанием. | Замечания — находки 1, 2, 5. |

## NOT TESTED / границы

- **Полный прогон не завершён.** Результат `accept-full` не использован. Для этого дерева остаются NOT VERIFIED: `test_resource_kind_boundaries.py` и тесты CORE-04 (их нет в focused green). Косвенно опираюсь на CI `f41f9a8`, где полный pytest шёл на побайтно тех же api/web.
- **CI самой правки нет.** У неотправленной правки нет CI точного SHA (как и у `ec39622` на момент его создания). Идентификаторы CI-прогонов для `bf3645d` (37411493038) и `f41f9a8` (38227457763) я не перепроверял по сети: взято из записей репозитория. Журналы CI `f41f9a8` недоступны (403), известны только итоги шагов.
- **Решение владельца.** Решение владельца о повышении WORK-01 и CORE-04 в репозитории не видно. Раздел `FOLLOWUP_VALIDATION.md:196` называет его отдельным. Это не оценивалось.
- **Не выполнялись:** запуск кода, production-миграция и `backfill-occupancy` вне одноразовых баз, Azure, нагрузка, пилоты, настоящий screen reader, контейнерные проверки локально.
- **Что я не воспроизводил.** Результаты red, green, browser и static взяты из логов чужого прогона. Сам я ничего не запускал.

## Дополнение: проверка правок по замечаниям

**Вердикт: PASS.** Блокирующих находок нет. Есть две новые заметки P3 и одно условие к ещё не написанным документам. Область: только то, что изменилось в четырёх файлах относительно моей первой проверки. Проверка снова строго на чтение, ничего не запускалось и не менялось.

**1. `scope` у CORE-04 и WORK-01** (`readiness_registry.py:154-165`, `:204-217`). Все новые утверждения сверены с уже прочитанными свидетельствами и кодом.
- CORE-04. «Bookings of one resource and staff reservations of one or more resources» совпадает с `occupancy/ACCEPTANCE.md:79` (нет многоресурсной записи) и с миграцией 0019. «The stage 1 record lists it as a technical PASS» совпадает с `stage1/ACCEPTANCE.md:9-12,21`. Оговорка про миграцию 0018 и пообъектный backfill (`:158-160`) точна: `occupancy/ACCEPTANCE.md:39-41`. «Resource blocks stay outside it» точна: `:43,79-80`. Завышения нет.
- WORK-01. «Shifts do not change customer booking availability» подтверждено решением 2 плана пакета I и тестом `test_workforce.py::test_shift_does_not_block_artist_booking` (запись на час смены проходит). «No labour-law rules» и «retention rules» соответствуют разделу «Вне пакета» и фразе плана «не проверяет трудовое законодательство». Устаревших утверждений нет.

**2. `stops` в `modules.py:141-144`.** Названные остановки верны. Перерывы (`break_start`/`break_end`) и решения (`approve`/`decline`) отклоняются в `timesheets.py:111-112` и в SQL (`0034:163-171`). `clock_out` исключён в обоих местах и закрывает открытый перерыв (`0034:230-234`). Замечания в находках 1 и 2 ниже.

**3. `web/tests/workforce.spec.ts`.** Причина пропуска на `:212` теперь верна. Других устаревших формулировок нет. Заголовок на `:165` и причина на `:166` корректны. Строка `:35` относится к `/fixture/user` фиктивного провайдера входа и к реестру не относится. Тексты интерфейса в `workforce-shared.tsx:41-44,344-346` различают «turned off» и «not available yet».

**4. Новый параметризованный тест** (`test_workforce.py:80-109`, `skills`, `shifts`, `privacy`).
- Состояние «принят, но не опубликован» на настоящем реестре он проверяет. Патча нет, публикации нет, фикстуры `workforce` нет, автоиспользуемых патчей реестра в conftest нет (`world`/`manager_a`/`client` публикаций не делают). Тест не проверяет принятость сам, но ответ `MODULE_DISABLED` возможен только при принятом модуле: при снятой приёмке `require_workforce` вернул бы `MODULE_NOT_READY` (`workforce.py:48-50`).
- Тела запросов достигают замка:
  - `skills`: те же поля, что в прежнем тесте.
  - `shifts`: совпадает с `Workforce.shift()` (`test_workforce.py:144-153`) без `staff_profile_id` (необязательное поле, `ShiftInput:89`). Проверки модели проходят: `ends_at` позже `starts_at`, интервал не больше 31 дня, дата 2031 года с часовым поясом.
  - `privacy`: `colleague_shifts_visible` задано строго как bool, `schema_version=1` добавлен общим слиянием.
- Для `manager_a` (менеджер на всю компанию) `require_location` и права `WORKFORCE_MANAGE` проходят. Затем в каждом маршруте `_writes` первым вызывает `require_workforce`, а без строки состояния `module_enabled` даёт false. Ответ `(409, MODULE_DISABLED)` верен для всех трёх маршрутов.
- Пробел: нет `changes` и `time-entries`. Он малозначим. Изменения смен и настройка видимости идут через ту же `workforce._writes`, табель — через тот же `require_workforce`. SQL «нет строки» обрабатывает как отказ везде (`0015:16-22`, `0034:108,169`). Единственная особая ветка — `closing=True` для `clock_out` (`timesheets.py:111`), и в состоянии «никогда не публиковали» открытой записи быть не может.

**Новые находки**
1. **P3.** `modules.py:141-142`. В `stops` не названы остановленные профили сотрудников (`staff_profiles`, `0032:488-491`) и запись настройки видимости филиала (`0035:52-53`). «Decisions on them» стоит уточнить как «decisions on time entries»: сейчас «them» может читаться как «corrections» и не покрывать решения по простому `clock_out`.
2. **P3.** `readiness_registry.py:209-211`. `scope` WORK-01 ссылается на содержимое записи приёмки («reviews listed… screen situations not tested»), которой ещё нет. Утверждение станет верным, только когда запись будет написана с этими двумя списками. Перепроверить при написании.
3. **P3 (необязательно).** `readiness_registry.py:158-160`. Фразу про backfill можно дополнить: резервации сами проверяют ещё не скопированные брони (`occupancy/ACCEPTANCE.md:40-41`). Иначе её можно прочесть как дыру в защите.

**Свидетельства выполнения (логи и хеши)**
- `accept-green-2/focused.log`: 634 passed, 0 failed. Все три параметра нового теста и оба парных теста прошли. Набор: unit, configurations, workforce, resource_kind_boundaries, occupancy, reservations. Это закрывает пробел, отмеченный мной в первой проверке (CORE-04-тесты и `resource_kind_boundaries`).
- Хеши. Текущие `readiness_registry.py`, `modules.py` и `workforce.spec.ts` совпали с записанными в `accept-green-2`, `accept-static-3` и `accept-full-2`.
- Но `test_workforce.py` в `accept-green-2` записан с хешем `90d93c6f…`, а текущий и в `accept-static-3`, и в `accept-full-2` — `b076c641…`. Значит, зелёный focused-прогон выполнялся на первой версии нового теста. Что различие сводится к типизации таблицы маршрутов, я проверить не мог: первой версии файла нет.
- `accept-static-2`: ошибка mypy `test_workforce.py:102 [dict-item]` в первой версии. `accept-static-3`: ruff check и format, mypy (265 файлов), web typecheck, lint, format, unit, build — exit 0. `web-audit` — exit 1, унаследованный.

**Не проверено (NOT VERIFIED)**
- Поведенческий прогон именно окончательных байтов `test_workforce.py` возможен только в `accept-full-2`. Он идёт, я его не ждал и его результат не использую.
- Документы коммита (ADR-0025, запись приёмки, индекс, замена утверждений «planned/закрыт») не написаны, их я не оценивал. Находки 1 и 2 первой проверки остаются открытыми до их появления.
- Принятые известные пределы (находка 7: `resolve`/`cancel` не привязаны к модулю; браузер для компании, никогда не включавшей модуль) в записи приёмки пока не проверены.
