# Независимый обзор: правка двух browser-спеков (коммит 3b9734c) и evidence-документы

**Вердикт: PASS.** Блокирующих (P1) и обязательных к правке (P2) находок нет. Есть три замечания P3 и одна заметка P3, все про формулировки evidence и про устройство прогона. Код правки в замечаниях не участвует.

## Область и способ

- Репозиторий: `C:/Users/alexa/.codex/worktrees/package-i4-review-corrections/Gorgona Booking`, ветка `codex/package-i4-review-corrections`, HEAD `b7953a4`, `git status` чист.
- Основной предмет: `3b9734c` (`web/tests/counterparties.spec.ts`, `web/tests/documents.spec.ts`). Для `2bca502` выполнена только проверка 6 (целостность). Продуктовую логику девяти файлов я не рецензировал.
- Обзор выполнил агент-ревьюер, который не писал это изменение. Работа только на чтение: git show/diff/rev-parse/ls-tree/cat-file, чтение файлов, grep. Один вспомогательный Python-скрипт во временном каталоге сессии только читал JSON и считал хеши. Тесты, сборки, браузеры, БД, сеть и fetch не запускались.
- Дата обзора: 2026-10-12.

## Находки

Находок уровня P1 и P2 нет. Замечания P3:

1. **P3. Сказано больше, чем доказывает `toBeDisabled()`.**
   - Место: `docs/plan/evidence/2026-10-12-i4-review-corrections/FOLLOWUP_VALIDATION.md:86-88`. Там сказано, что заморозку редактора «доказывала и доказывает следующая строка (`toBeDisabled()`)».
   - Редактор блокируется не только конфликтом. `web/components/counterparties.tsx:349-350`: `locked = busy || ... || Boolean(pending) || conflict || Boolean(proposal)`. `web/components/documents.tsx:322`: `locked = busy || !enabled || interrupted || conflict`.
   - Старая проверка в ветке «прошла впустую» срабатывала до ответа 409. В этот момент редактор уже заблокирован по `busy`/`pending`/`proposal`, поэтому `toBeDisabled()` проходил, ничего не доказывая о конфликте.
   - После правки `toBeDisabled()` стоит за ожиданием текста конфликта. React объединяет `setError` и `setConflict` из одного `catch` (`counterparties.tsx:263-269`, `documents.tsx:219-223`), так что теперь строка осмысленна.
   - Нужна правка текста: «после правки доказывает», а не «доказывала и доказывает».

2. **P3. Формулировки о гонке сильнее, чем данные.**
   - Место: `FOLLOWUP_VALIDATION.md:37-39` («Обычно опрос успевал первым») и `:64` («воспроизведены детерминированно»).
   - Проба `probe-red` не измеряет гонку. Она строит оба состояния искусственно. «До конфликта» снимается до клика, потому что проба вставлена перед `confirm`/`Save document`. «После» снимается после явного ожидания текста сообщения. Каждая проба выполнена по одному разу.
   - Гипотеза гонки согласуется с логами: прежний полный прогон упал со strict-violation (`CHECKS.json`, `failed_cases`), документы там прошли. Прямого измерения тайминга нет, и слова «обычно» подкрепить нечем.
   - Это рабочая гипотеза, а не измеренный факт. Правка спеков от этого не зависит: новая проверка устойчива к любому порядку.

3. **P3. Проба причины шла на другой сборке `web/out`, и документ этого не говорит.**
   - Фаза `probe-red` (`probe-red/results.json`): `web_out_before = web_out_after = 2847f1e7…` (154 файла).
   - Все остальные фазы (`static-1` после сборки, `browser-1..3`, `full`, `probe-green`): `c09367d0…` (154 файла).
   - `FOLLOWUP_VALIDATION.md:100` и `built_site` в `FOLLOWUP_SOURCE_PROOF.json` говорят только о пересобранном сайте.
   - Происхождение сборки `2847f1e7…` я установить не могу: NOT VERIFIED. Исходники в `probe-red` совпали с неизменными, компоненты контрагентов и документов диффом не затронуты, так что риск низкий. Различие нужно просто назвать.
   - Похожее ограничение: `probe-green` шёл на временных (не финальных) байтах спеков. Это честно отмечено в `FOLLOWUP_CHECKS.json` (`source_snapshot_equals_full_run: false`), а финальные байты подтверждены фазами `static-1`, `browser-1..3` и `full`. Проба логирует только первую строку ошибки (`fails: Error: expect(locator).toBeVisible() failed`), причина (не найдено или таймаут) не записана.

4. **P3, заметка, действий в этом коммите не требуется.** Mobile зависит от desktop только неявно.
   - В `web/playwright.config.ts:5,13-16` стоят `workers: 1` и порядок проектов, секции `dependencies` нет.
   - Остановка desktop даёт второй, вводящий в заблуждение сбой mobile: так и было в `VALIDATION.md`, где связь «предполагается, но не доказана».
   - Автор об этом пишет (`FOLLOWUP_AUTHOR_REVIEW.md`: зависимость «не менялась»). Это не дефект правки.

## Что проверено

| № | Что проверено | Исход |
|---|---|---|
| 1 | `git show 3b9734c`: состав и запрещённые приёмы | **Подтверждено.** Ровно два файла, `10 insertions, 2 deletions`. В каждом по одному `expect`: `counterparties.spec.ts:139-143`, `documents.spec.ts:161-165`. Комментарий из двух строк, одна старая строка заменена тремя. `first()`, `nth()`, `force`, `skip`, `fixme`, увеличенных timeout и удалённых проверок нет. `git diff 2bca502 3b9734c --stat` даёт те же два файла. |
| 2 | Announcer в Next 16.3.7 (`app-router-announcer.js`) | **Подтверждено.** Узел создаётся в `useEffect` при монтировании (`:38-47`), то есть после гидратации и не в серверном HTML. `AppRouterAnnouncer` включён в `app-router.js:385` для каждого дерева app-router, навигация не нужна. Контейнер `next-route-announcer` добавляется в `document.body` (`:32`), вне `<main>`. Shadow root `mode: 'open'` (`:28-30`). Внутри `div role=alert aria-live=assertive` (`:23-25`). Стиль `:26`: `position:absolute; height/width:1px; clip; overflow:hidden`, без `display:none`, `visibility:hidden` и `aria-hidden`, то есть элемент в дереве доступности и имеет непустой bounding box. Эмпирически: `probe-red` показывает, что `getByRole("alert")` его находит, а прежний `toBeVisible()` проходит. Текст: начальное `''` (`:48`), задаётся только при смене заголовка после первой загрузки (`:62-64`), значение `document.title` или текст первого `h1` (`:51-59`). В приложении единственный заголовок статический, «Book your appointment» (`web/app/layout.tsx:4`), присваиваний `document.title` нет, поэтому текст практически всегда пуст. Даже при смене это заголовок страницы, а не «This counterparty changed.» или «This document changed.». |
| 3 | Дословность текста от API до экрана | **Подтверждено.** `counterparties.py:376-379` и `documents.py:364-365` бросают `ConflictError` с нужной фразой, `api/errors.py` отдаёт её как `error.message` (HTTP 409). `management-api.ts:721-724` создаёт `ManagementApiError(err.code, err.message, status)`. Команда сохранения идёт через `managementFetch`/`authorizedResponse`, поэтому схема ответа не подменяет ошибку (`counterparty-api.ts:19-38,168-190`, `document-api.ts:26-40,107-125`). Компонент вызывает `setError(failure(e))` (`counterparties.tsx:50-51,263`, `documents.tsx:40-41,219`) и рисует `<p role="alert" className="error">` (`counterparties.tsx:369`, `documents.tsx:353`). Подстроки фильтра входят в текст. Спек провоцирует устаревший `expected_revision` при сохранении, это те самые две ветки. Другие формулировки: «This counterparty changed. Reload it.» (`counterparties.py:572,656`) тоже содержит подстроку фильтра, но на пути сохранения не встречается. «The other counterparty changed…» (`:575`), «This link changed…» (`counterparties.py:856`, `documents.py:543`) и «This document or record changed…» (`documents.py:560`) фильтр не совпадают. Это нормально для данного шага. |
| 4 | Claims (b) и (c), структура спеков | **Подтверждено.** Desktop-ветка: `counterparties.spec.ts:32-231`, конфигурационные команды (draft, validate, publish) в `:201-222`, «turned off» в `:226`. Mobile-ветка начинается ожиданием «Counterparties is turned off.» (`:233`). То же в `documents.spec.ts:34-211`, `:179-191`, `:204`, mobile `:213`. Конфиг: `workers: 1`, `fullyParallel: false`, `retries: 0`, проекты desktop затем mobile (`playwright.config.ts:4-6,13-16`). В `probe-red` и в оригинальном сбое (`CHECKS.json`, `failed_cases`) mobile падает на том же ожидании: «element(s) not found», 5000 ms. Записи, нужные mobile (`FAKE Alpha Updated`, `FAKE Supply agreement v3`), создаются до точки остановки, так что другой причины в спеке я не нашёл. Claim (c): та же строка и тот же сбой в `documents.spec.ts` подтверждены логом `probe-red/document-browser.log`. |
| 5 | Все `web/tests/*.spec.ts` на `getByRole("alert")`/`getByRole("status")` | **Безопасно во всех местах.** Alert (16 вхождений). С фильтром по тексту: `booking.spec.ts:101,149,166,302`, `finance.spec.ts:479`, `workforce.spec.ts:29`, два изменённых. Через область: `ledger.spec.ts:197` (`.ledger` это `div.documents.ledger`, `ledger.tsx:327`); `management.spec.ts:85,102` (`getByRole("main")`, announcer вне `<main>`, так как он в `body`); `management.spec.ts:225,331,336,372` (region «Legal entities»/«Departments»); `reservations.spec.ts:20` (region). Status. Next не добавляет `role=status` (в `next/dist/client` такого нет, найдены только файлы announcer). Незаscoped `page.getByRole("status")` (`counterparties.spec.ts:78,93`, `documents.spec.ts:13`, `management.spec.ts:54,121`, `workforce.spec.ts:27`) announcer не затрагиваются. Прочие (`section.`/`panel.`/`contracts.`) ограничены областью. Локаторы `[role=alert]`, `toHaveCount(0)` и `not.toBeVisible()` для alert не используются. |
| 6 | Blob id | **Расхождений нет.** Одиннадцать путей из `changed_sources` в `FOLLOWUP_SOURCE_PROOF.json`: `git rev-parse b7953a4:<path>` совпадает с `git_blob_oid`, SHA-256 содержимого совпадает с `sha256`. `git diff --name-only 490652b 2bca502` равно ровно девяти файлам из `SOURCE_PROOF.json`, blob id равны `filtered_git_blob_oid`. Снимок full-run (429 файлов `api/web`) побайтно совпадает с рабочим деревом. |
| 7 | Доказательства в `FOLLOWUP_VALIDATION.md` против сырых логов | **В основном подтверждено, три замечания P3** (находки 1-3). Подтверждено: `probe-red` обе спеки (строки PROBE, strict-violation на 2 элемента, mobile 5000 ms, `1 failed in 19.22s` и `1 failed in 15.39s`); `probe-green`: «fails» без сообщения, оба прогона `passed` (`16.90s`, `12.86s`); `browser-1..3`: desktop и mobile ok, шесть таймингов точно как в документе (16.48, 11.91, 13.67, 12.01, 13.84, 11.73 s); `full/pytest-full.log`: `1526 passed, 4 skipped in 997.19s (0:16:37)`, 4 пропуска это три container-теста и tenant-site, оба браузерных теста в JUnit PASS; `full/results.json`: `source_unchanged_during_run = true`, `web_out_before == web_out_after`. Проверены ruff/mypy (265 файлов), unit 102, build 23/23, audit exit 1 с двумя high (`next`, `source-map-js`), `docs-unit.log` 18 passed, кластеры остановлены, `postmaster.pid` и файла пароля нет. Фазы `static-1`, `browser-*`, `full` шли на финальных байтах обоих спеков (SHA-256 из `results.json` равны HEAD). |
| 8 | Прочие риски 3b9734c и описаний | Дополнительных дефектов правки не найдено. Фильтр по префиксу сообщения связывает тест с продуктовым текстом; если фраза изменится, тест упадёт явно. Так же сделано в `booking.spec.ts` и `workforce.spec.ts`. Остальное в находках 1-4. |

## NOT TESTED / границы

- Я не запускал тесты, Playwright, браузер, сервер, БД, сборки и CI. Всё сказанное о поведении выведено из чтения кода и сырых логов автора.
- NOT VERIFIED: гонка «первый опрос против ответа 409» как причина исходного сбоя. Логи совместимы с ней, но таймингов нет (находка 2).
- NOT VERIFIED: происхождение `web/out` с хешем `2847f1e7…` из `probe-red` (находка 3).
- NOT VERIFIED: что `gorgona_booking` в `full` импортировался из проверяемого дерева. `runner.py` ставит `PYTHONPATH=<ROOT>/api/src`, что говорит в пользу этого, но `results.json` показывает интерпретатор из venv другого worktree (`package-g-ledger-review`), и импорт я не проверял.
- NOT VERIFIED: remote-наблюдение в `FOLLOWUP_VALIDATION.md:146-147` (`c6b8e34`, run 38204334830, PR = 0). Сеть мне запрещена.
- Не проверено, что файлы, названные «сохранёнными без изменений» (`VALIDATION.md`, `CHECKS.json`, `SOURCE_PROOF.json`, `CHANGED_FILES.md`), совпадают с версиями до коммитов: в 490652b их не было, отдельного снимка у меня нет.
- Поведение Playwright (piercing shadow DOM, правила видимости) я подтверждаю по логам `probe-red`, а не по исходникам Playwright.
- Принадлежность пакета к приёмке, CI точного SHA, независимый обзор девяти файлов `2bca502` вне этого обзора. Решение о приёмке не принимается.
