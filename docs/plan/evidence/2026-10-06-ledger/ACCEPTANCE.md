# Пакет G — финансовая основа (FIN-01), 2026-10-06

Статус FIN-01 и модуля finance: **technically_verified** (2026-10-06).
Проверенный код: `95a0de4ac9f5aa3c96b054c5504f59115b0e4b69`.
Это техническая приемка пакета G, без промышленной приемки или разрешения на deploy.
Основа: принятый ADR-0023 и решения владельца 1A, 2A, 3A, 4B.
База — `151472a68d736ef21f68550ec36674eb36efc23c` (план этапа 2), ее собственный
[CI 37425859611](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37425859611)
PASS. Этот результат не переносится на новый код G.

## Состав и сохранение

Своя ветка `codex/package-g-ledger-review`, своя рабочая копия:
`C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking`.
Из `gorgona-e2-documents` перенесены девять измененных/новых файлов с проверкой
совпадения SHA256. Исходная рабочая копия и основная копия владельца не изменялись.

Миграция 0020 добавляет поддерживаемые валюты, книги юридических лиц, версии
настроек, план счетов и его версии, неизменяемые проводки/строки и события периода.
Миграции 0001–0019 не менялись. Таблицы финансов компании используют FORCE RLS,
tenant-bound FK и ограничение всей компанией. Runtime не может редактировать или
удалять историю; триггеры защищают историю и при использовании owner role.

Учет использует точные integer minor units; через API деньги передаются строками.
Одна проводка относится к одной книге и валюте. Источник/ID операции уникальны
в книге, сторно допускается один раз и зеркалит исходную проводку. Начальные
остатки вводятся явной проводкой `opening`. Пересчета валют и автоматических
проводок из стоимости записей нет.

Маршруты `/v1/businesses/{id}/ledger`, `/books/{id}`, счета, проводки, сторно,
периоды и ведомость подключены к настоящим API/БД. Карта прав версии 5:
`finance.read/manage/close` доступны owner/manager всей компании; поддержка,
сотрудники, филиальные членства и делегаты не получают финансовый доступ.

Страница `/ledger/` выполняет эти операции, показывает сохраненные строки и
историю закрытия/открытия. Для повтора в текущем компоненте сохраняются ключ и
тело команды. До отправки в sessionStorage записывается только типизированная
ссылка: actor/business/book, ключ, тип команды, ID/версия/последовательность.
Токены, суммы, описания и полное тело в storage не записываются. После reload,
навигации или повторного входа того же пользователя новая команда заблокирована
до разрешения результата. Выбранная книга восстанавливается, в том числе вне
первой страницы юридических лиц. Закрытие вкладки/новый браузер не являются
гарантией восстановления: отдельный source_id хозяйственной операции нужен для
дедупликации намерения между независимыми сессиями.
Книги/счета имеют expected revision, периоды — expected sequence; неизменяемые
проводки используют уникальный ID. Настройки и план счетов сворачиваются через
нативный details/summary, таблица ведомости доступна с клавиатуры.

После полного прогона, независимого обзора и CI точного SHA readiness повышается
отдельным коммитом приемки. Finance можно включить только новой публикацией
конфигурации владельцем/менеджером; реестр не меняет уже опубликованные настройки.
API и browser fixtures больше не повышают finance искусственно: они публикуют его
через обычный реестр. Только отрицательный gate test временно понижает готовность
до implemented и доказывает MODULE_NOT_READY. Чтение истории и восстановление
неопределенных команд продолжаются после отключения finance.

## Найденные дефекты и проверка изменения

До исправления: **2 failed / 22 passed**. Маршруты учета отвечали 404.
Главный дефект: после раннего `SET CONSTRAINTS` SQL позволял дописать строку и
закоммитить несбалансированную проводку. Теперь отложенные ограничения стоят
и на заголовке, и на строках; поздняя вставка снова проверяет баланс и сторно.
Оба исходных regression tests прошли после изменения.

Расширенный schema guard проверяет восемь company-only политик, семь module gates,
tenant-isolation predicates, неизменяемость, последовательности версий/периодов,
оба отложенных balance triggers и утвержденные тела функций из поставляемой
миграции. Измененные/отключенные определения приводят к 503, включая health readiness.
Не используются ожидаемые определения, прочитанные из самой БД. Тела функций
сравниваются точно: пробел внутри SQL-литерала может изменить смысл и не удаляется.
Общая функция require_enabled_module также проверяется точным сравнением.

Два SQL race tests наблюдают реально ожидающий advisory lock через pg_locks.
При закрытии первым ожидающая проводка отказывается; при проведении первым
оно фиксируется и закрытие следует за ним. Это проверка обоих порядков с новым
снимком после ожидания, не имитация гонки.

Независимый обзор в отдельной рабочей копии обнаружил два P1 и три P2. Все пять
исправлены и представлены на повторную проверку:

1. После ранней проверки ограничений исходная проводка могла получить новые
   строки после уже созданного сторно. Теперь такая вставка отвергается.
2. REPEATABLE READ сохранял старый снимок открытого периода после ожидания lock.
   Все ledger mutations теперь требуют READ COMMITTED; неподдерживаемая изоляция
   отвергается до изменения данных. API использует READ COMMITTED.
3. Нормализация пробелов скрывала изменение SQL-литерала. Проверка определения
   точная, включая общую блокировку публикации конфигурации.
4. Неопределенная команда терялась при reload. Добавлены минимальная session
   ссылка и реальные POST commands/{key}/resolve и /cancel. Resolve сверяет actor,
   книгу и ресурс с receipt, а после удаления обычного 24h receipt — с неизменяемой
   записью того же пользователя. Cancel сначала проверяет фактический результат
   под общей ledger lock; для еще не сохраненной команды создает постоянный
   ledger_command_cancellations. Поздний исходный запрос получает 409
   LEDGER_COMMAND_CANCELLED. Если он успел первым, cancel возвращает committed.
   Этот восьмой RLS control table не создает денежного эффекта; восстановление и
   отмена доступны при отключенном finance. Проверены оба порядка гонки.
5. Ведомость могла иметь верные итоги при неверных отдельных строках. Zod теперь
   проверяет уравнение остатков/оборотов каждой строки с BigInt и затем итоги.

SQL red для трех независимых обходов и red Zod regression были получены перед
исправлениями; green подтвержден текущими focused проверками. Ошибка подключения
после долгой паузы (PostgreSQL shared-memory error 487) учитывалась как ошибка
окружения, а не red доказательство дефекта. Перезапущен только свой тестовый кластер.

Первый browser harness потребовал исправления точных select locators.
Затем desktop прошел; mobile нашел нарушение keyboard access у прокручиваемой
таблицы. Добавлен фокусируемый именованный регион. Последующий прогон обоих
проектов прошел с настоящим входом OIDC/PKCE, PostgreSQL, потерей только ответа
реального PUT, сторно, ведомостью и периодами. Тестовый IdP и все данные явно FAKE.

Первый полный прогон: **1 failed / 838 passed / 4 skipped / 296.02 s**.
Единственный failure — устаревший configuration locator Finance·Planned после
перехода в Implemented. Теперь проверяется реально недоступный unfinished module;
отдельный API-тест продолжает проверять запрет включения finance до приемки.
Повторный configuration browser harness: PASS, desktop и mobile.

Второй полный прогон после recovery: **26 failed / 821 passed / 4 skipped /
284.87 s**. Первая ошибка была DuplicateTable в восстановлении test boundary:
scope marker стоял перед новым cancellation CREATE TABLE, поэтому finally
оставлял удаленные location policies и вызывал последующие 503. SQL scope block
теперь содержит только восемь восстанавливаемых политик; таблица, grants и
immutable trigger стоят до marker. Дополнительно обновлен unit snapshot с 49
на 50 boundary definitions и проверяется число параметров ledger guard. Политики
и runtime guard не ослаблялись. Свежая проверка affected schema/booking/reservation
путей: **64 passed / 14.96 s**, после нее заново запущена вся suite.

Третий полный прогон коммита `6735f88`: **1 failed / 846 passed / 4 skipped /
328.89 s**. Независимый повторный browser review воспроизвел ту же ошибку и
детерминированно подтвердил red: после полной загрузки выбрать текущее юрлицо
еще раз — форма книги исчезала. Обработчик теперь не сбрасывает состояние при
неизменном выборе; в recovery scenario добавлена проверка повторного выбора
после загрузки. Первоначальные пять замечаний повторно прошли независимую SQL/API
проверку; найденный дополнительный P2 проверяется отдельно.

Draft [PR #12](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/12)
нацелен на `claude/stage2-finance-plan`. Первый
[CI 37494622944](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37494622944)
для `6735f88` — FAIL: strict mypy отверг обращение теста к неэкспортированным
импортам LEDGER_BOUNDARY/LEDGER_PARAMETERS через schema_guard. Тест теперь
импортирует определения непосредственно из ledger_guard; свежий local strict
mypy по 197 файлам PASS. Ожидается CI нового коммита после UI исправления.

Коммит `4961d1a4990c6d5af37a512fc414d1f7714399dc`: полный local PASS —
**847 passed / 4 skipped / 330.20 s**. Три skips — Docker (локально не настроен),
один — необязательное встраивание в отдельный внешний сайт.
[CI 37495564576](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37495564576)
точного SHA PASS: **850 passed / 1 skipped / 254.33 s**; Docker gates включены
GBA_REQUIRE_CONTAINER=1 и прошли. Этот green не закрывает следующий дефект.

Независимая последняя проверка обнаружила дополнительный P1: лишняя permissive
SELECT policy оставляла утвержденную tenant policy неизменной, но открывала
runtime чужую книгу, тогда как health/API readiness продолжали возвращать 200.
HTTP-утечка чужого ответа не утверждается: доказан обход DB RLS и незамеченная
порча границы. [Обзор 4961d1a](INDEPENDENT_REVIEW_4961d1a.md) сохраняет red и hashes.
Семантика OR объединения permissive policies проверена в
[PostgreSQL 18 CREATE POLICY](https://www.postgresql.org/docs/18/sql-createpolicy.html).

Теперь guard отвергает любую лишнюю permissive policy на всех восьми таблицах
учета. Он не удаляет политики автоматически и не изменяет production schema:
readiness и ledger API отвечают 503 до восстановления утвержденной схемы.
Новый собственный red: **1 failed / 34 deselected / 1.97 s** — health возвращал
200 вместо 503. После исправления **66 passed / 20.64 s**: все ledger SQL/API,
11 вариантов дополнительных политик (восемь таблиц; SELECT/INSERT/ALL;
public/runtime/member role) и document/guard contracts. После finally удаления
fault policy readiness снова 200. Fresh Ruff/format/strict mypy 197 файлов PASS.
Окончательная проверка этого guard на `95a0de4`:

- Полная local suite **PASS: 858 passed / 4 skipped / 358.82 s**. Локальные три
  Docker skips компенсируются обязательными container gates в CI; внешний сайт
  остается отдельным необязательным тестом.
- [CI 37496936531](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37496936531)
  точного `95a0de4` **PASS: 861 passed / 1 skipped / 223.29 s**; PostgreSQL 18,
  browser и Docker обязательны. Web unit 68, сборки web/image, Ruff и mypy PASS.
- [Финальный независимый обзор](INDEPENDENT_REVIEW_95a0de4.md) **PASS** для
  конечного guard/test diff: 21 unit, Ruff/format/mypy трех файлов, 95 placeholders
  и параметров, восьми таблиц и 11 regression cases. PG runtime последнего guard
  не повторялся независимо; его доказывают отдельные root/CI прогоны. Ранее
  независимый reviewer выполнил 88 Python checks, реальные UI 4 сценария и
  отдельные deterministic UI probes на собственной БД. Все найденные 3 P1 и
  4 P2 закрыты; конкретных незакрытых findings нет.

Два последующих запуска прежнего агента остановила автоматическая проверка
содержимого. Финальный ограниченный code review выполнен другим агентом в новой
отдельной clean checkout. Это не заменяло runtime proof статическим предположением:
отдельные реальные full suites выше сохраняют свои SHA и границы.

После повышения реестра и удаления положительных test overrides свежий focused
**PASS: 68 Python / 63.52 s**, внутри **4 desktop/mobile browser / 29.5 s**.
Обычная публикация finance и тот же полный учет проверены без promotion fixture;
отрицательный тест readiness продолжает отказывать. Приемочный commit требует
свежего полного CI; его точный HEAD/run проверяются в [PR #12 Checks](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/12/checks)
и записываются в финальный отчет/описание PR без переноса старого green на новый SHA.

Независимый [обзор приемочного diff a6f2d8b](INDEPENDENT_ACCEPTANCE_REVIEW_a6f2d8b.md)
PASS по source: ссылки на95a0de4/schema20, обычные API/browser fixtures, только
отрицательный readiness override с restoration через monkeypatch; финансовая
логика не менялась. Runtime этого приемочного diff не повторялся независимо.
Первый local full a6f2d8b остановлен на устаревшем Configuration snapshot:
**1 failed / 74 passed / 3 skipped / 84.00 s**. Focused configuration затем
подтвердил старое finance-as-unready ожидание (1 failed / 12 passed / 7.15 s).
В явные списки enableable добавлен finance; отказ по MODULE_NOT_READY теперь
проверяет planned workforce. Отдельный ledger negative test понижает именно
finance и сохраняет доказательство запрета до acceptance. Assertions не удалены.
Свежий Configuration API/contracts: **31 passed / 6.66 s**. Последний полный
прогон и CI этого test-snapshot исправления должны завершиться перед финальным отчетом.

## Свежая проверка

| Проверка | Результат |
|---|---|
| Focused contracts + SQL/API + browser приемочного реестра | PASS: 68 Python / 63.52 s; внутри 4 Playwright / 29.5 s, desktop + mobile; без положительного override |
| Ledger SQL/API и document/guard contracts | PASS: 66 passed / 20.64 s; оба close/post и cancel/post порядка, 11 дополнительных policy cases |
| Web unit | PASS: 68 tests / 1.3 s, включая 5 ledger boundary tests |
| Web typecheck/lint/format | PASS, exit 0 |
| Web build | PASS, страница /ledger; 17 routes в таблице Next.js, 18 generated static pages |
| Ruff / Ruff format | PASS; 197 Python files |
| Strict mypy | PASS; 197 source files |
| Восстановление schema boundary и регрессии booking/reservations | PASS: 64 passed / 14.96 s |
| Полная suite проверенного кода 95a0de4 | PASS: 858 passed / 4 skipped / 358.82 s |
| CI точного SHA 95a0de4 | PASS: 861 passed / 1 skipped / 223.29 s, Docker gates обязательны |
| Независимый обзор | PASS в пределах отчетов: исходный runtime/browser review + final guard delta review; все 7 findings закрыты |

Логи этой сессии находятся в игнорируемом `handoff/package-g-review/`; учетные
данные там не лежат. PostgreSQL 18.6 для проверки создан отдельно на loopback
127.0.0.1:51456, вне checkout. Тестовые базы создаются/удаляются fixtures; ранее
работавший кластер на 51454 не использовался и не останавливался.

## Источники и версии

- PostgreSQL **18**: [CREATE TRIGGER](https://www.postgresql.org/docs/18/sql-createtrigger.html)
  и [Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html),
  проверены 2026-10-06. Факт документации: SET CONSTRAINTS может досрочно вызвать
  отложенный триггер; конкретный обход подтвержден нашим SQL regression test.
- [SIX ISO 4217 List One](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml),
  опубликован **2026-09-17**, получен 2026-10-06. Все **155** включенных кодов и
  масштабы сравнены с XML: PASS. Исторический BGN исключен из новой таблицы.
  SHA256 сохраненного XML:
  `46325cfd61095f45ca26ca7b734ad7b20c9cfecdd518b16707da1aa9a74d3e98`.
  Поддерживаемая таблица не заявляет поддержку фондовых/металлических кодов
  или масштабов вне 0/2/3. Внешняя сеть не нужна для runtime.
- Существующие lockfiles сохранены: Python 3.14.6, FastAPI 0.142.1,
  Pydantic 2.13.5, psycopg 3.3.6; Next.js 16.3.7, React 19.3.0,
  Zod 4.6.5, Playwright 1.63.0. Новых зависимостей нет.

## Границы

Никаких merge, deployment, production migrations, Azure changes или настоящих
платежных провайдеров. Пакеты H–K не реализуются этим изменением. Нагрузочные
цели, эксплуатация, ручная screen-reader приемка и финансовая/налоговая
пригодность для конкретной юрисдикции NOT TESTED. Эта платформа не подает отчетность
и не имитирует списание или оплату.

Исторический вариант незакоммиченной 0020 не следует подменять в уже мигрировавшей
БД: checksum history проверяется migrator. Эта сессия проверяла только новые
одноразовые базы. Развертывание и перенос существующей БД требуют отдельной
авторизации и проверки фактического migration history.
