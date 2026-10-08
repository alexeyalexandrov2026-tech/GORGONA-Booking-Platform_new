# Независимое техническое ревью H3 — 2026-10-08

## Результат

**FAIL — подтверждены пять находок: одна P1 и четыре P2.** Восемь новых
регрессионных проверок воспроизводят их на неизменённом коде. Существующие
целевые проверки: **215 PASS**. Исправления не выполнены; опубликованные
миграции и исходники приложения не изменены.

Обход `P + C + R <= A` в выполненных сценариях не обнаружен. Это ограниченный
результат проверки, а не доказательство отсутствия всех денежных ошибок.
F1 показывает повторный учёт одной case-insensitive source identity **внутри**
допустимого principal; арифметический cap этого не предотвращает.

Проверенный HEAD: `4532e3f62aae8ac2152dfeb388ce7f7ee214fcbd`.
Ветка: `codex/package-h3-credit-voids`.
Checkout: `C:\Users\alexa\Documents\ChatGPT\gorgona-h3-credit-voids`.
Origin: `https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.git`.
Этот отчёт — единственный файл предлагаемого отдельного коммита после указанного
HEAD. Он не является acceptance-коммитом и не меняет FIN-03/FIN-02.

## Проверка передачи и GitHub

Архив `GORGONA_handoff_2026-10-08_H3_complete.zip`:
SHA-256 `c59c93ae21f3762f5561c1e158688aadf917aab6b2ae86a129f7061de60140f8`.
Проверены все **149** файлов `MANIFEST.sha256`; дубликатов и небезопасных путей
ZIP нет. Архив распакован без перезаписи в
`C:\Users\alexa\Documents\ChatGPT\Gorgona Booking\handoff\H3_REVIEW_2026-10-08_01a11c5a`.
Все **138** файлов под `repo/` побайтово совпали с проверяемым checkout.
Прочитаны `00_START_HERE.md` и `NEXT_AGENT_H3_VOIDS_2026-10-08.md`.
Архив содержит документацию и тестовые помощники, а не самостоятельную копию
исходников. Поручение владельца, полученное в этой сессии, определяет объём
работ; вложенные промпты сами по себе не запускались.

До создания PR проверены GitHub REST branch heads, workflow runs точных SHA и
все существующие PR по этим head branches. Дубликатов PR не было.

| Ветка | Подтверждённый SHA | CI точного SHA | Созданный черновик / база |
|---|---|---|---|
| `codex/package-h3-credits` | `807ed594f808ea4919718205f78085406c054038` | [37719158462 — success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37719158462) | [PR18](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/18) / `codex/package-h3-settlement-guards` |
| `codex/package-h3-payment-corrections` | `1d96a64c3b85507d1db230e1dcb7dd21e6947046` | [37790605230 — success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37790605230) | [PR19](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/19) / `codex/package-h3-credits` |
| `codex/package-h3-credit-voids` | `4532e3f62aae8ac2152dfeb388ce7f7ee214fcbd` | [37806763957 — success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37806763957) | [PR20](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/20) / `codex/package-h3-payment-corrections` |

PR созданы через подключённый GitHub connector от
`alexeyalexandrov2026-tech`, по порядку стека, и прикреплены к текущему чату.
Состояния — draft; merge не выполнялся. Запросов на запуск CodeRabbit не было.
CI выше подтверждает исходные ветки; новый коммит отчёта получает отдельную
проверку после push и не подменяет проверенный кодовый HEAD.

## Объём, независимость и критерии

Ревью выполнено новым исполнителем, не автором H3, с двумя дополнительными
read-only проверяющими в отдельных ветках и checkout на том же HEAD. Они читали
кредитные и settlement/correction части; один основной исполнитель запускал
все PostgreSQL проверки. Все находки ниже подтверждены основным исполнителем,
а не перенесены из чужих заключений без проверки.

Просмотрены пять миграций `0025`–`0029` и четыре запрошенных файла:
`business/settlements.py`, `business/credit_notes.py`,
`business/financial_math.py`, `db/financial_guard.py`. Для проверки договоров
и повторного использования дополнительно прочитаны ADR-0024, package H plan,
актуальные части master plan/handoff, G journal/reversal implementation,
финансовые контракты и существующие integration fixtures. Поздние определения
SQL рассматривались как замена ранних, а не как параллельные версии функций.

Наблюдаемые критерии:

- Неотрицательные effective P/C/R и `P+C+R<=A` после commit.
- Одна external source identity не создаёт второй payment/journal.
- SQL runtime role соблюдает те же state, lineage, amount и tenant/book правила,
  что и сервис, включая deferred commit checks.
- Коррекция следует подтверждению в payment revision и settlement sequence;
  зеркало точно соответствует заменяемому journal.
- Paid/refund/unknown dependencies требуют отдельной reconciliation без эффектов.
- Runtime-readable контракты представляют каждую разрешённую SQL запись.
- Readiness отказывает при повреждении обязательных H-контролей.

Архитектура повторно использует PostgreSQL ledger как источник истины, общий
`gba.lock_ledger`, READ COMMITTED, insert-only версии, typed/versioned Pydantic
контракты и существующие реальные PostgreSQL/API fixtures. Новых зависимостей,
платёжных адаптеров или отдельного money store для ревью не добавлено.

## Подтверждённые находки

### F1 — P1: регистр греческой сигмы обходит external-source deduplication

**Место:** `api/src/gorgona_booking/db/migrations/0026_settlement_guard_corrections.sql:22`.
Затронуты вызовы `gba.external_identity_key` из сервиса и SQL payment insert guard.

Функция использует Unicode `lower`, которое оставляет разные ключи для uppercase
`FAKE-ΟΣ` и lowercase `fake-ος`: `fake-οσ` и `fake-ος`. Unicode определяет Σ как
uppercase обеих lowercase форм σ/ς; обычное lowercase не обеспечивает caseless
matching. [Unicode FAQ](https://www.unicode.org/faq/casemap_charprop.html),
[PostgreSQL 18 string functions](https://www.postgresql.org/docs/18/functions-string.html).

**Воспроизведение:** счёт A=100, два settlement по 50, одинаковый source account
alias и две указанные case-вариации reference. API вернул **200/200**, создал два
payment journals и P=100. Отдельный сценарий первого подтверждения через API и
второго через **runtime-role прямой SQL** также committed с двумя journals.
Ожидалось `FINANCIAL_SOURCE_ALREADY_RECORDED`/unique rejection для второго факта.

**Доказательство:** `test_case_only_sigma_transfer_must_not_be_counted_twice` и
`test_sigma_direct_sql_must_not_count_same_transfer_twice` в приложении ниже:
`200 != 409`, `2 != 1`. `P+C+R=A` сохранён; ошибка — semantic duplicate, а не
переполнение cap. Фикстуры вручную аттестуют тестовый внешний факт; реальный банк
или provider не использовался.

**Последствие:** возможен повторный учёт одной вручную аттестованной передачи и
двойная проводка, пока хватает principal.

**Предложение после решения владельца:** forward `0030+` с согласованным Unicode
caseless identity contract и проверкой collisions существующих references перед
его применением. Не объединять обнаруженные реальные денежные записи автоматически.
Для Unicode matching PostgreSQL 18 предоставляет `casefold`; выбор collation,
normalization и миграция старых идентичностей требуют отдельной проверки.

### F2 — P2: SQL позволяет отмене предшествовать исходному подтверждению

**Место:** `api/src/gorgona_booking/db/migrations/0028_payment_corrections.sql:343`
(event binding и revision continuity, строки 343–363);
актуальный deferred checker:
`api/src/gorgona_booking/db/migrations/0029_credit_voids.sql:719`.

Проверяется contiguous payment revision, но не рост settlement `sequence`
относительно исходного payment и предыдущей correction. SQL insert guard требует
соответствующее событие текущей транзакции, но не причинный порядок событий.

**Воспроизведение:** на reserved settlement в одной runtime transaction записаны
`payment_voided` sequence=4, затем `confirmed` sequence=5, исходный payment при
sequence=5 и его revision=2/void при sequence=4; journals и зеркало точные.
`SET CONSTRAINTS ALL IMMEDIATE` и commit **успешны**. Затем независимо прочитаны
исходный/void sequences **[5,4]**; баланс P=0/C=0/R=100/A=100.

**Доказательство:** `test_sql_void_event_cannot_precede_original_confirmation`:
`4 > 5` ложно. Схема, триггеры, RLS и grants для сценария не изменялись.

**Последствие:** immutable history содержит отмену ещё не подтверждённого платежа;
порядок settlement events и payment revisions противоречит друг другу. Это
state/audit defect, не доказанное завышение текущего P.

**Предложение после решения владельца:** SQL before/deferred checks должны
требовать sequence каждой revision больше исходного payment sequence и больше
sequence предыдущей revision; добавить multi-revision transaction regression.

### F3 — P2: SQL кредит с 199 строками невозможно прочитать через H API

**Место:** credit admission в
`api/src/gorgona_booking/db/migrations/0029_credit_voids.sql:113` сохраняет общий
bound 199 из `0021_invoice_accrual.sql:36`, который `0029` не сужает;
`api/src/gorgona_booking/business/financial_contracts.py:305` допускает 198;
`api/src/gorgona_booking/business/credit_notes.py:235` строит этот view без
обработки такого сохранённого состояния.

**Воспроизведение:** A=100.00; runtime SQL создаёт issued credit из 199 уникальных
строк по 0.01, все на одну исходную invoice line; C=1.99, refund отсутствует.
199 counter lines плюс одна control line дают ровно 200 journal lines. Полный
graph прошёл `SET CONSTRAINTS ALL IMMEDIATE` и commit. GET credit вызвал
необработанный `CreditNoteView ValidationError`: **at most 198 items, not 199**.
Баланс после commit: C=1.99, available=98.01.

**Доказательство:** `test_sql_credit_line_limit_must_match_read_contract`.
Стандартный ASGI test transport перекидывает server exception в тест; API log
подтвердил unhandled error в `load_credit`. Это runtime/API отказ, а не ошибка
pytest setup. Схема и controls при прямой записи не изменялись.

**Последствие:** SQL-valid immutable credit невозможно прочитать через действующий
view contract. Последствие для void — статический вывод из вызова того же
`load_credit` в `credit_notes.py:834`; отдельный HTTP void именно 199-line
документа не запускался.

**Предложение после решения владельца:** выровнять credit-specific SQL/API bound
и проверить уже сохранённые 199-line документы до forward constraint. Учесть,
что partial unpaid/refund split требует две control lines, поэтому простое
расширение всех API limits до 199 не решает полный случай.

### F4 — P2: архивирование исторического счёта блокирует зеркальный H void

**Место:** `api/src/gorgona_booking/business/credit_notes.py:903`,
`api/src/gorgona_booking/db/migrations/0027_credit_notes.sql:217`,
`api/src/gorgona_booking/business/settlements.py:1270`.
Общий H posting path:
`api/src/gorgona_booking/business/ledger.py:1083`.

Credit void копирует обязательные неизменные исторические строки, но их SQL
insert проверяет текущий `not archived` counter account. Payment mirror проходит
обычный append path с тем же запретом. Архивирование этих счетов через штатный
account API при наличии H history разрешено. G отдельно допускает точные
reversals по архивным счетам (`0020_ledger.sql:356` и `:375`), поэтому повторно
использованный append path не сохраняет это свойство для H mirrors.
ADR-0024 запрещает автоматическое изменение archive state счёта, но явный
запрет точного historical mirror без изменения этого state не формулирует.

**Воспроизведение 1:** invoice100, unpaid credit20, архивировать counter account
через account API (200), вызвать credit void: **409 FINANCIAL_STATE_INVALID**.
**Воспроизведение 2:** подтвердить70, архивировать исторический cash account
(200), вызвать payment void: **409 LEDGER_STATE_INVALID**, archived account.

**Доказательство:**
`test_credit_mirror_can_use_its_archived_historical_counter_account` и
`test_payment_mirror_can_use_its_archived_historical_cash_account`.

**Последствие и граница:** корректировка ошибочной historical attestation требует
сначала снова активировать архивный счёт. Денежная порча этими отказами не
показана; обходной путь — явное переоткрытие счёта. Поэтому P2, а не P1.
Если владелец намеренно выбирает такую H policy, её следует явно принять и
объяснить пользователю; текущая ошибка о сменившемся credit этого не объясняет.

**Предложение после решения владельца:** отделить строго проверенное historical
mirror от replacement/new posting и согласовать это с G reversal policy;
SQL должен проверять exact mirror/lineage, сохраняя запрет новых обычных проводок
на архивные счета. Не снимать общий archived-account запрет.

### F5 — P2: readiness не проверяет usable helper grants и transaction defaults

**Место:** `api/src/gorgona_booking/db/financial_guard.py:256` и `:307`.

Helper approval сравнивает signature/result/body/flags, но не runtime `EXECUTE`;
column approval сравнивает type/nullability, но не default expression.

**Воспроизведение 1:** только в одноразовой БД owner role выполняет
`REVOKE EXECUTE ON FUNCTION gba.credit_voided(uuid,uuid,uuid) FROM gba_runtime`.
Readiness и ledger overview остаются **200/200**; прямой вызов helper от runtime
отказывает с **SQLSTATE 42501**. После проверки grant восстановлен.

**Воспроизведение 2:** owner role меняет только default
`financial_document_versions.created_transaction` на `'0'::xid8`.
Readiness остаётся **200**, а обычное сохранение invoice draft получает
**409 FINANCIAL_STATE_INVALID**. Default восстановлен на
`pg_catalog.pg_current_xact_id()` в `finally`.

**Доказательство:** `test_readiness_refuses_missing_helper_execute` и
`test_readiness_refuses_wrong_transaction_default`.

**Последствие и граница:** readiness даёт ложную готовность повреждённой/частично
развёрнутой схемы. Эти сценарии требуют privileged DDL; runtime role сам не
менял grants/defaults. Обход money cap через default0 **не доказан**: другие
current-transaction checks блокируют запись. Риск — отказ workflow, ошибочно
выдаваемый как business conflict в сценарии default0, и неполный rollout guard.

**Предложение после решения владельца:** packaged approvals для обязательных
defaults и effective runtime EXECUTE permissions с отрицательными DDL tests.
Обязательные положительные разрешения проверять по каждому требуемому privilege.

## Проверки и ограничения

Локальное окружение: существующие Python3.14/psycopg/pytest зависимости проекта,
PostgreSQL18.6. Кластер из handoff по пути `h3-guards-20261007` отсутствовал на
диске. Для ревью создан собственный кластер
`%LOCALAPPDATA%\GorgonaBookingTests\h3-independent-review-20261008`,
только loopback `127.0.0.1:51472`, scram authentication. Пароль не выводился,
не копировался в архив/репозиторий и не входит в этот отчёт. Fixtures создают
одноразовую БД, применяют 0001–0029 как test owner и выполняют операции как
non-owner runtime role с действующими RLS/grants. В конце каждого запуска БД
удаляется штатным fixture teardown. Остальные кластеры не использовались.
После запусков в собственном кластере осталась только БД `postgres`; кластер
остановлен, `pg_isready` подтвердил отсутствие ответа на 51472.

| Проверка | Результат |
|---|---|
| Архив SHA256/manifest; сравнение repo-файлов | PASS: 149 / 138, несовпадений 0 |
| GitHub ветки / expected SHA / exact-SHA CI | PASS: все три, ссылки выше |
| Отсутствие дублирующих PR перед созданием | PASS; создано ровно 3 draft PR |
| Целевые existing integration/unit tests | PASS: 215, 141.89s, exit0 |
| Первый external probe setup | FAIL среды: 7 setup errors / Windows Proactor loop; исправлен импорт существующего selector-backend fixture |
| Подтверждающие regression probes | FAIL ожидаемо: 8 assertion failures, 12.44s, exit1; это воспроизведённые дефекты |
| CAP / mirror / dependency / RLS races имеющихся целевых suites | PASS в составе 215; без универсального утверждения о всех interleavings |
| Static `financial_math.py` bounded integer/cap/split/correction review | Проверено; новой подтверждённой находки нет |
| Изменения приложения/миграций | Нет; commit только REVIEW.md |
| Полная 1160-test suite, web/build/Axe, HawkScan, local Docker | NOT TESTED заново: read-only ревью не меняет приложение |
| Production/Azure/provider/real money | NOT TESTED; не выполнялись |

Первый initdb вызов имел неверно переданный PowerShell аргумент `--pwfile`;
исправлена форма аргумента, после чего кластер успешно инициализирован. Первый
external pytest вызов имел PowerShell parameter binding error (`-p` дважды);
аргументы переданы явным массивом. Ни один из этих setup failures не выдаётся
за результат тестирования приложения. Тестовые скрипты существуют вне Git.

Команда существующих целевых проверок (из `api`, с уже настроенным приватным
`GBA_TEST_ADMIN_DSN`, `GBA_REQUIRE_POSTGRES=1`, `PYTHONPATH=api/src;api`):

```powershell
python -m pytest -q -p no:cacheprovider --tb=short `
  tests/integration/test_credit_voids.py `
  tests/integration/test_credit_notes.py `
  tests/integration/test_payment_corrections.py `
  tests/integration/test_external_payments.py `
  tests/integration/test_settlements.py `
  tests/unit/test_financial_documents.py `
  tests/unit/test_credit_void_contracts.py `
  tests/unit/test_credit_contracts.py `
  tests/unit/test_settlement_contracts.py
```

Команда воспроизведений: сохранить Python-приложение ниже **вне checkout** как
`test_review.py`; из `api` с тем же приватным test DSN запустить:

```powershell
python -m pytest -q -p no:cacheprovider -p tests.integration.conftest `
  C:\path\outside-repository\test_review.py -s --tb=short
```

Ожидаемый результат на `4532e3f`: **8 failed**. Положительные finance readiness
overrides находятся в существующих test fixtures; production registry не
изменялся. Все суммы, пользователи, счета и references — fake test data.

## Решение для владельца

Сначала решить F1 и не принимать H3 как завершённый финансовый пакет до повторной
проверки. F2/F3/F5 требуют согласования SQL/contracts/guard; для F4 явно выбрать
historical-mirror policy. Исправления — только новым утверждённым объёмом,
миграция с `0030` или далее, без редактирования опубликованных 0025–0029.
Никакие найденные данные не удалять и денежные записи не объединять автоматически.
Merge, force-push, rebase/amend, deployment, production migrations, provider/
credential actions, FIN-03/02 promotion и ручной CodeRabbit здесь не выполнялись.

Инструменты: PowerShell, Git, `rg`, подключённый GitHub connector, GitHub REST,
Codex managed worktrees, Python/pytest/psycopg, PostgreSQL18.6, официальные
PostgreSQL/Unicode документы; skills `evidence-engineering` и
`multi-reviewer-patterns`.

## Приложение: полный воспроизводимый тестовый файл

В приложении сохранена точная исполняемая версия последнего подтверждающего
запуска. SHA-256 исходного внешнего `test_review.py`:
`efa89fa4f3b2f5dddb2e0774b06beffe51dfe929cd690b2a711d720bc55715b9`.
Она не является изменением тестов/кода проекта. Два независимых проверяющих
сверили находки с этим файлом, runtime log и текущими исходниками; их замечания
по SQL pointers и границам статических выводов внесены в отчёт.

```python
"""External review probes; production source and tracked tests stay unchanged."""
import json
from uuid import UUID, uuid7

import psycopg
import pytest
from pydantic import ValidationError

from gorgona_booking.db.pool import tenant_transaction
from tests.conftest import anyio_backend
from tests.integration import test_credit_notes as shared
from tests.integration.test_credit_voids import _void
from tests.integration.test_payment_corrections import corrections

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
credits = shared.credits


def observe(name, **values):
    print(json.dumps({"probe": name, **values}, ensure_ascii=True, default=str))


async def test_case_only_sigma_transfer_must_not_be_counted_twice(credits, corrections, app_pool):
    obligation, _ = await credits.invoice()
    first = await corrections.held([(obligation, "50.00")])
    second = await corrections.held([(obligation, "50.00")])
    refs = ("FAKE-\u039f\u03a3", "fake-\u03bf\u03c2")
    a = await credits.payments.confirm(first, 3, [(obligation, "50.00")], "50.00", refs[0])
    b = await credits.payments.confirm(second, 3, [(obligation, "50.00")], "50.00", refs[1])
    async with tenant_transaction(app_pool, credits.ledger.business) as conn:
        keys = await (await conn.execute(
            "select gba.external_identity_key(%s,'preserve'),gba.external_identity_key(%s,'preserve')", refs
        )).fetchone()
    balance = await credits.settlements.balance(obligation)
    observe("sigma_api", statuses=[a.status_code, b.status_code], keys=keys,
            paid=balance["paid"], journals=await credits.payments.payment_journals(app_pool))
    assert a.status_code == 200
    assert b.status_code == 409, "same transfer with upper/lower final sigma was recorded twice"


async def test_sigma_direct_sql_must_not_count_same_transfer_twice(credits, corrections, app_pool):
    obligation, _ = await credits.invoice()
    await credits.paid(obligation, "50.00", "FAKE-\u039f\u03a3")
    second = await corrections.held([(obligation, "50.00")])
    await credits.payments.write_directly(app_pool, second, 4, obligation, 5000, "fake-\u03bf\u03c2")
    count = await credits.payments.payment_journals(app_pool)
    observe("sigma_sql", journals=count, balance=await credits.settlements.balance(obligation))
    assert count == 1, "runtime-role direct SQL counted the case-only duplicate"


async def archive_account(credits, account):
    http, auth, base = credits.ledger.client, credits.ledger.auth, credits.ledger.base
    view = await http.get(f"{base}/accounts/{account}", headers=auth)
    assert view.status_code == 200, view.text
    body = view.json()
    archived = await http.put(f"{base}/accounts/{account}", headers=credits.ledger.headers(), json={
        "schema_version": 1, "expected_revision": body["revision"], "code": body["code"],
        "type": body["type"], "name": body["name"], "archived": True,
    })
    assert archived.status_code == 200, archived.text


async def test_credit_mirror_can_use_its_archived_historical_counter_account(credits):
    obligation, (line,) = await credits.invoice()
    credit = await credits.credit(obligation, [(line, "20.00")])
    await archive_account(credits, credits.settlements.invoices.counter)
    response = await _void(credits, credit["document_id"])
    observe("archived_credit_void", status=response.status_code, response=response.json())
    assert response.status_code == 200, "a historical credit mirror should not need an active counter account"


async def test_payment_mirror_can_use_its_archived_historical_cash_account(credits, corrections):
    obligation, _ = await credits.invoice()
    settlement, payment = await corrections.confirmed([(obligation, "70.00")], "70.00", "FAKE-ARCHIVED")
    await archive_account(credits, credits.payments.cash)
    response = await corrections.void(settlement, payment, 4)
    observe("archived_payment_void", status=response.status_code, response=response.json())
    assert response.status_code == 200, "a historical payment mirror should not need an active cash account"


async def test_readiness_refuses_missing_helper_execute(credits, owner_conn, app_pool):
    http, auth, base = credits.ledger.client, credits.ledger.auth, credits.ledger.base
    owner_conn.execute("revoke execute on function gba.credit_voided(uuid,uuid,uuid) from gba_runtime")
    try:
        ready = await http.get("/health/ready")
        ledger = await http.get(base, headers=auth)
        denied = None
        try:
            async with tenant_transaction(app_pool, credits.ledger.business) as conn:
                await conn.execute("select gba.credit_voided(%s,%s,%s)",
                                   (credits.ledger.business, credits.ledger.book, uuid7()))
        except psycopg.errors.InsufficientPrivilege as exc:
            denied = exc.sqlstate
        observe("missing_execute_guard", readiness=ready.status_code, ledger=ledger.status_code, runtime_sqlstate=denied)
        assert denied == "42501"
        assert ready.status_code == 503, "helper is unusable by runtime but readiness reports ready"
    finally:
        owner_conn.execute("grant execute on function gba.credit_voided(uuid,uuid,uuid) to gba_runtime")


async def test_readiness_refuses_wrong_transaction_default(credits, owner_conn):
    http = credits.ledger.client
    owner_conn.execute("alter table gba.financial_document_versions alter column created_transaction set default '0'::xid8")
    try:
        ready = await http.get("/health/ready")
        saved = await credits.settlements.invoices.save()
        observe("wrong_xid_default_guard", readiness=ready.status_code, draft=saved.status_code,
                error=saved.json().get("error"))
        assert ready.status_code == 503, "transaction default breaks writes but readiness reports ready"
    finally:
        owner_conn.execute("alter table gba.financial_document_versions alter column created_transaction set default pg_catalog.pg_current_xact_id()")


async def test_sql_void_event_cannot_precede_original_confirmation(credits, corrections, app_pool):
    obligation, _ = await credits.invoice()
    settlement = await corrections.held([(obligation, "100.00")])
    tenant, book, actor = credits.ledger.business, credits.ledger.book, credits.ledger.user.user_id
    payment, original, reversal = uuid7(), uuid7(), uuid7()
    async with tenant_transaction(app_pool, tenant) as conn:
        await conn.execute(
            "insert into gba.settlement_events (tenant_id,book_id,settlement_id,sequence,kind,created_by) "
            "values (%s,%s,%s,4,'payment_voided',%s),(%s,%s,%s,5,'confirmed',%s)",
            (tenant,book,settlement,actor,tenant,book,settlement,actor))
        await conn.execute(
            "insert into gba.external_payments (tenant_id,book_id,id,settlement_id,sequence,direction,currency,"
            "amount_minor,actual_external_date,entry_date,cash_account_id,source_account_alias,"
            "external_reference,attestation,entry_id,created_by) values "
            "(%s,%s,%s,%s,5,'receivable','USD',5000,'2026-10-02','2026-10-02',%s,"
            "'FAKE bank','FAKE sequence inversion','manual_attestation',%s,%s)",
            (tenant,book,payment,settlement,credits.payments.cash,original,actor))
        await conn.execute(
            "insert into gba.external_payment_allocations (tenant_id,book_id,payment_id,line_no,obligation_id,amount_minor) "
            "values (%s,%s,%s,1,%s,5000)", (tenant,book,payment,obligation))
        await conn.execute(
            "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
            "values (%s,%s,%s,'2026-10-02','USD','payment',%s,%s)", (tenant,original,book,str(payment),actor))
        await conn.execute(
            "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
            "values (%s,%s,1,%s,%s,'debit',5000),(%s,%s,2,%s,%s,'credit',5000)",
            (tenant,original,book,credits.payments.cash,tenant,original,book,credits.settlements.invoices.control))
        await conn.execute(
            "insert into gba.external_payment_revisions (tenant_id,book_id,payment_id,revision,settlement_id,"
            "sequence,kind,entry_date,attestation,reason,evidence_source,reversal_entry_id,created_by) "
            "values (%s,%s,%s,2,%s,4,'voided','2026-10-04','attested_erroneous_confirmation',"
            "'FAKE reverse chronology','FAKE review',%s,%s)", (tenant,book,payment,settlement,reversal,actor))
        await conn.execute(
            "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
            "values (%s,%s,%s,'2026-10-04','USD','payment_correction',%s,%s)",
            (tenant,reversal,book,f"{payment}:2:reversal",actor))
        await conn.execute(
            "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
            "select tenant_id,%s,line_no,book_id,account_id,case side when 'debit' then 'credit' else 'debit' end,"
            "amount_minor from gba.journal_lines where tenant_id=%s and entry_id=%s", (reversal,tenant,original))
        await conn.execute("set constraints all immediate")
    async with tenant_transaction(app_pool, tenant) as conn:
        history = await (await conn.execute(
            "select p.sequence,r.sequence from gba.external_payments p join gba.external_payment_revisions r "
            "on r.tenant_id=p.tenant_id and r.book_id=p.book_id and r.payment_id=p.id where p.id=%s", (payment,)
        )).fetchone()
    observe("reverse_event_chronology", original_and_void_sequences=history,
            balance=await credits.settlements.balance(obligation))
    assert history[1] > history[0], "runtime SQL committed a void before its original confirmation"


async def test_sql_credit_line_limit_must_match_read_contract(credits, app_pool):
    obligation, (original_line,) = await credits.invoice()
    tenant, book, actor = credits.ledger.business, credits.ledger.book, credits.ledger.user.user_id
    party = credits.settlements.invoices.party
    control, counter = credits.settlements.invoices.control, credits.settlements.invoices.counter
    document, entry = uuid7(), uuid7()
    line_ids = [uuid7() for _ in range(199)]
    async with tenant_transaction(app_pool, tenant) as conn:
        await conn.execute(
            "insert into gba.financial_documents (tenant_id,book_id,id,created_by,kind) "
            "values (%s,%s,%s,%s,'credit_note')", (tenant,book,document,actor))
        for revision in (1, 2):
            issued = revision == 2
            await conn.execute(
                "insert into gba.financial_document_versions (tenant_id,book_id,document_id,revision,state,"
                "direction,counterparty_id,counterparty_revision,currency,invoice_date,control_account_id,"
                "title,number,principal_minor,line_count,credited_obligation_id,entry_id,issued_on,attestation,"
                "applied_minor,created_by) values (%s,%s,%s,%s,%s,'receivable',%s,1,'USD','2026-10-03',%s,"
                "'FAKE SQL 199 lines','FAKE-SQL-199',199,199,%s,%s,%s,%s,%s,%s)",
                (tenant,book,document,revision,'issued' if issued else 'draft',party,control,obligation,
                 entry if issued else None,'2026-10-03' if issued else None,
                 'confirmed_account_treatment' if issued else None,199 if issued else None,actor))
            for number, line_id in enumerate(line_ids, 1):
                await conn.execute(
                    "insert into gba.financial_document_lines (tenant_id,book_id,document_id,revision,line_no,"
                    "line_id,credited_line_id,counter_account_id,description,amount_minor) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s,'FAKE one minor',1)",
                    (tenant,book,document,revision,number,line_id,original_line,counter))
        await conn.execute(
            "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,source_kind,source_id,created_by) "
            "values (%s,%s,%s,'2026-10-03','USD','credit',%s,%s)", (tenant,entry,book,str(document),actor))
        for number in range(1, 200):
            await conn.execute(
                "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
                "values (%s,%s,%s,%s,%s,'debit',1)", (tenant,entry,number,book,counter))
        await conn.execute(
            "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_id,side,amount_minor) "
            "values (%s,%s,200,%s,%s,'credit',199)", (tenant,entry,book,control))
        await conn.execute("set constraints all immediate")
    failure = None
    try:
        response = await credits.ledger.client.get(f"{credits.base}/{document}", headers=credits.ledger.auth)
        status = response.status_code
    except ValidationError as exc:
        status = None
        failure = [{k: error[k] for k in ('type','loc','msg')} for error in exc.errors()]
    observe("sql_199_credit_lines", sql_committed=True, http_status=status, validation=failure,
            balance=await credits.settlements.balance(obligation))
    assert failure is None and status == 200, "SQL accepts a credit that the read contract cannot represent"
```
