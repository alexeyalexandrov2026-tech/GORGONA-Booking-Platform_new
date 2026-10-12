# Package I — разбор сбоя полного прогона и повторная проверка, 2026-10-12

**Полный обязательный прогон PASS: 1526 passed, 4 skipped in 997.19s (0:16:37).**
Сбой предыдущего прогона разобран: причина — проверка в двух browser-спеках, а не
продукт. Исправления R2-1/R2-2/R2-3/CR-1 и правка спеков закоммичены локально.
Пакет не принят: CI точного SHA NOT TESTED, публикация и приёмка — решения владельца.

Первый FAIL сохранён без изменений: [VALIDATION.md](VALIDATION.md),
[CHECKS.json](CHECKS.json), [SOURCE_PROOF.json](SOURCE_PROOF.json),
[CHANGED_FILES.md](CHANGED_FILES.md). Эти файлы описывают состояние до коммитов.
Настоящий документ их дополняет, а не заменяет.

## Исходная точка и итог

- Checkout `C:/Users/alexa/.codex/worktrees/package-i4-review-corrections/Gorgona Booking`,
  ветка `codex/package-i4-review-corrections`, база `490652b3f01a1b3de2df2d2e6257fced6caf32e2`.
- До изменений статус, ветка, HEAD и SHA-256 девяти изменённых файлов совпали с
  SOURCE_PROOF.json; процессов PostgreSQL не было.
- Локальные коммиты: `2bca502d7c0c1caf77e9d88a9238974c8bee258b` — исправления второго обзора, девять файлов, те же
  байты, что прошли ограниченный независимый обзор; `3b9734cd90f76726a27ba604d6ee441d7d3cbfeb` — два browser-спека.
  Документы — следующий коммит.
- Ветка не опубликована. Push, PR, merge, rebase, amend, изменение готовности,
  CodeRabbit, production/Azure/provider/funds/credential actions не выполнялись.
- Миграции 0001–0035, зависимости, lockfiles и продуктовый код этим срезом не менялись.

## Причина сбоя

`web/tests/counterparties.spec.ts:139` проверяла `page.getByRole("alert")`. Next.js
держит на каждой странице собственный пустой элемент с `role="alert"` — объявитель
маршрута `__next-route-announcer__`. Поэтому:

1. Пока сообщения о конфликте нет, локатору отвечает один объявитель, и
   `toBeVisible()` **проходит, ничего не проверив**.
2. Когда сообщение появилось, локатору отвечают два элемента, и та же проверка
   падает с strict mode violation.

Исход зависел от того, что случится раньше: первый опрос Playwright или ответ 409
сервера. Обычно опрос успевал первым. В полном прогоне ответ пришёл раньше — отсюда
FAIL при неизменённых файлах контрагентов.

Mobile-сбой — следствие, а не вторая причина. Desktop-сценарий последним шагом
выключает модуль, а mobile-сценарий начинается с ожидания «Counterparties is turned
off.». Если desktop остановился раньше, модуль остаётся включённым.

`web/tests/documents.spec.ts:161` содержала ту же проверку и ту же гонку; в
предыдущем полном прогоне она прошла случайно.

### Доказательство

Во временные копии обеих спек добавлена проба: список элементов `role=alert` до
конфликта, результат прежней проверки без сообщения на странице, ожидание текста
сообщения, затем прежняя проверка. Пробы не коммитились; их версии лежат в
`probe-specs/` каталога прогона.

| Наблюдение (фаза `probe-red`) | Контрагенты | Документы |
|---|---|---|
| `role=alert` до конфликта | только `__next-route-announcer__`, текст пуст | то же |
| Прежняя проверка без сообщения на странице | passes | passes |
| `role=alert` после конфликта | сообщение продукта и объявитель | то же |
| Прежняя проверка после сообщения | FAIL: strict mode violation, 2 элемента | то же |
| Mobile после остановки desktop | FAIL: «… is turned off.», timeout 5000 ms | то же |
| Итог pytest | 1 failed in 19.22s | 1 failed in 15.39s |

Оба сбоя полного прогона воспроизведены детерминированно в обеих спеках.
Обратная сторона подтверждена после правки: когда desktop доходит до выключения
модуля, mobile проходит — в шести focused-запусках и в полном прогоне.

Вторая проба (фаза `probe-green`) проверила новую проверку тем же способом: без
сообщения на странице она **fails**, а сценарий с ней целиком проходит. Значит,
новая проверка не может пройти впустую.

## Правка

По одной проверке в двух спеках; продуктовый код не менялся:

- `web/tests/counterparties.spec.ts`:
  `page.getByRole("alert").filter({ hasText: "This counterparty changed." })`.
- `web/tests/documents.spec.ts`:
  `page.getByRole("alert").filter({ hasText: "This document changed." })`.

Проверка ждёт именно сообщение о конфликте. `first()`, `force`, skip и увеличение
timeout не применялись. Тот же приём уже используется в `booking.spec.ts` и
`workforce.spec.ts`; остальные обращения к `role=alert` в `web/tests` уже
ограничены областью или текстом.

Следствие для прежних результатов: до правки эта строка не доказывала, что
сообщение о конфликте показано. Заморозку редактора доказывала и доказывает
следующая строка (`toBeDisabled()`).

## Проверки, которые действительно выполнены

| Проверка | Исход |
|---|---|
| Проба причины `probe-red`, обе спеки | FAIL ожидаемо: 1 failed in 19.22s; 1 failed in 15.39s |
| Проба новой проверки `probe-green`, обе спеки | PASS; без сообщения новая проверка fails |
| Ruff check / format / mypy | PASS, exit 0 каждый; 265 файлов |
| Web typecheck / lint / format / unit / build | PASS, exit 0 каждый; 102 unit; 23 страницы |
| Focused browser: контрагенты и документы, desktop и mobile | PASS 3 из 3, каждый запуск на своём новом кластере: 1 passed in 16.48s; 1 passed in 11.91s; 1 passed in 13.67s; 1 passed in 12.01s; 1 passed in 13.84s; 1 passed in 11.73s |
| Full serial API/PostgreSQL/browser-required | **PASS: 1526 passed, 4 skipped in 997.19s (0:16:37)** |
| Исходники во время full | не менялись; `web/out` не менялся со сборки до конца full |
| `tests/unit/test_configuration_contracts.py` после правки master plan | PASS: 18 passed in 0.15s |
| Production npm audit | **FAIL exit 1: 2 high (next, source-map-js)**, без remediation |
| Авторский обзор изменённых байтов | выполнен: [FOLLOWUP_AUTHOR_REVIEW.md](FOLLOWUP_AUTHOR_REVIEW.md) |
| Независимый обзор двух спеков | NOT DONE |
| CI точного SHA | NOT TESTED: коммиты локальные, ветка не опубликована |

[FOLLOWUP_CHECKS.json](FOLLOWUP_CHECKS.json) содержит argv, cwd, exit, время и хеши
логов каждой фазы, строки проб, счётчики полного прогона, пропущенные cases, матрицу
и наблюдение за remote. [FOLLOWUP_SOURCE_PROOF.json](FOLLOWUP_SOURCE_PROOF.json)
содержит SHA-256 и Git blob id одиннадцати изменённых файлов, полный снимок api/web
во время full и отпечаток `web/out`. Blob id совпадают с закоммиченными.

## Матрица C2 на свежем полном прогоне

Выбор cases — прежний, из [CHECKS.json](CHECKS.json); числа пересчитаны по новому
JUnit и совпали с прежними. Строки пересекаются, числа не складываются.

| Строка | Выбранные PASS cases | Итог |
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
| I-12 | 40 | **BLOCKED** |

I-12 — BLOCKED, а не PASS: выбранные cases и обязательный локальный полный прогон
прошли, но CI точного SHA требует публикации, а публикация — решение владельца.

## Среда

Python 3.14.6, Node 24.18.0, npm 11.16.0, PostgreSQL 18.6, Playwright 1.63.0,
Next 16.3.7. Каталог прогона: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/i4-counterparty-locator-20261012-490652b`.
Фазы: `probe-red`, `static-1`, `browser-1`…`browser-3`, `full`, `probe-green`. Каждая
фаза с базой данных создала свой кластер (SCRAM, checksums, UTF8, locale C) на
свободном loopback-порту с `max_connections=400`. Пароль создавался в памяти и
вырезался из логов. Все кластеры остановлены, `postmaster.pid` и файл пароля
отсутствуют. Чужие кластеры и порты не использовались.

Remote, только чтение, 2026-10-12T08:21:29Z: опубликована I4 `c6b8e34`, run 38204334830 —
success, PR для I4 — 0; ветки corrections, acceptance и review-2 не опубликованы.

## Не проверено и открыто

NOT TESTED: три container checks и optional external tenant site (4 skipped nodes),
screen reader, HawkScan, load/soak, deployment/production; отдельные browser-пробы
review 2 (timezone ≠ UTC, company-wide) не повторялись. Старые PASS не перенесены.

Решения владельца: публикация ветки и CI точного SHA, независимый обзор двух
спеков, план и Proposed ADR-0025, срок жизни отменённого ключа 24 ч, границы дат
чтения коллег, роль в directory и видимость на уровне компании, расхождение
CORE-04, приёмка и готовность, PR и порядок стека. Remediation аудита — отдельный scope.
