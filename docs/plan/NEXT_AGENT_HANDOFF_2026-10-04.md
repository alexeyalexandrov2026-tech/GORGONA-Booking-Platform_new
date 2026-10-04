# GORGONA — актуальная передача после выбора нового репозитория

## Продолжение в облачной сессии: делегирование между компаниями

**Самое новое состояние — ветка `claude/keen-mayer-lg9ift`.** Она начинается с `codex/universal-business-foundation` на `eaa62339cf82ea69b96f2e8ec346ede585729f02` и добавляет пакет [ADR-0016](../adr/0016-limited-cross-business-delegation.md): миграция 0011, полномочия владельца, назначения обслуживающей компании, делегированный доступ 13 операционных обработчиков, RLS-запреты для делегированной транзакции, guard 45 определений и интерфейс. Pull request для этой ветки не создавался; draft PR #1 остается от `codex/universal-business-foundation`. Код опубликован как `bd1a138a11ebbe506010c243a5a02d9989bc1b52`; push CI [37212099717](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37212099717) PASS: 474 passed, 1 skipped (внешний site gate), 118.32 с, включая контейнерные gates. Подробности — в [реестре](GORGONA_IMPLEMENTATION_STATUS.md); [приемка](evidence/2026-10-04-delegation/ACCEPTANCE.md) содержит локальные доказательства.

Локально на итоговом дереве: API **471 passed, 4 skipped, 112.25 с, exit 0** (PostgreSQL 18.4, браузеры обязательны; пропуски — три контейнерных gate без Docker daemon и внешний site gate), web unit 16, сборка 14 страниц, Ruff/mypy 134 файла. Базовый прогон неизмененного `eaa6233` в той же среде: 410 passed, 4 skipped.

Воспроизведение в Linux-контейнере без доступа к apt-репозиторию PostgreSQL:

1. Серверные binaries PostgreSQL 18: `npm pack @embedded-postgres/linux-x64@18.4.0-beta.17`, распаковать, выполнить `node scripts/hydrate-symlinks.js` в папке пакета, скопировать `native/` вне репозитория. Сервер запускать не от root, отдельным пользователем: `initdb -U <admin> --auth=scram-sha-256`, затем `pg_ctl ... -o "-h 127.0.0.1 -p 55432 -c max_connections=250"`. Пароль администратора не записывать в репозиторий; DSN передавать только окружению pytest (`GBA_TEST_ADMIN_DSN`).
2. Python 3.14 финальной версии (uv 0.8 предлагал только 3.14.0rc2, на котором pydantic падает при сборе тестов): новый uv из PyPI, `uv python install 3.14`, `uv sync --locked --python 3.14.8`.
3. Node 24 с nodejs.org с проверкой SHA256; `npm ci --ignore-scripts` в `web`.
4. Если CDN Playwright закрыт, а установлен другой Chromium, указать `PLAYWRIGHT_BROWSERS_PATH` на локальную папку-прокладку с ожидаемыми именами (`chromium-1243/chrome-linux64`, `chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell`). Это только локальная замена; CI ставит совпадающую сборку.
5. Порядок: web typecheck/lint/format/unit/build, затем в `api`: `ruff format --check .`, `ruff check .`, `mypy`, `pytest -q -rs` с `GBA_REQUIRE_POSTGRES=1 GBA_REQUIRE_BROWSER=1`. Focused: `tests/unit/test_delegation_contracts.py`, `tests/integration/test_delegations.py`, `tests/integration/test_delegation_browser.py`.

Попутно найден и вынесен в отдельную задачу существующий дефект: `api/setup.py:_booking_state` читает `gba.tenants` без фильтра компании (воспроизведено для сотрудника двух компаний). Новых разрешительных политик на `gba.tenants` пакет не добавляет именно из-за таких запросов; не добавлять их без явных фильтров во всех чтениях.


**Обновление по аудиту 2026-10-04:** прочитать [проверку выполнения плана](GORGONA_PLAN_AUDIT_2026-10-04.md). Независимая GORGONA сохраняет 39 отраслей; KA Nails не входит в текущую работу. Исправлен публичный development-only `/v1/holds`: маршрут только для local/test/ci; hosted booking идет через customer API. После воспроизведения четырех ошибок 55 focused unit tests, Ruff/format и strict mypy прошли. Полный CI базы `f8db038` — исторический для следующих изменений. Продуктовый этап 1 не закрыт: далее юридические лица внутри существующей компании, затем структура/делегирование, публикация и общая занятость. Не трактовать прежние пакеты как реализацию этих TODO.

**2026-10-04.** Владелец поручил исправить полный мастер-план, начать реализацию, сохранить работу для следующего агента и продолжать. Завершены исправления основы, черновик гибридного профиля и второй пакет этапа 1: рабочий доступ одного филиала. Вся универсальная платформа не завершена. Предыдущая передача сохранена в [CHECKPOINT_2](NEXT_AGENT_HANDOFF_2026-10-04_CHECKPOINT_2.md), первоначальная — в [CHECKPOINT_1](NEXT_AGENT_HANDOFF_2026-10-04_CHECKPOINT_1.md).

## Где продолжать

**Принятый технически пакет после аудита:** см. [ADR-0015](../adr/0015-tenant-owned-legal-entity-drafts.md) и [приемку](evidence/2026-10-04-legal-entities/ACCEPTANCE.md). Черновики юридических лиц в том же business/tenant, миграция 0010, API, неизменяемые версии и UI опубликованы на `d97924f53a8ff34a69f82d36fe675b965e8aa6e6`. PR CI 37204951503 и push CI PASS: 413 Python passed / 1 optional skip, 91.41 с, required PostgreSQL/browser/container; web unit11/build14 и static checks128 PASS. Guard требует 19 политик. Пропуск маршрутов в центральной проверке ответов найден review, воспроизведен четырьмя тестами и исправлен. Локальный runtime-запуск был отклонен и не выполнялся; runtime PASS получен в GitHub CI. Не объявлять юридические лица зарегистрированными, CORE-03 или этап 1 завершенными; не повторять проверенный пакет и не применять миграцию к живой БД. После изменения кода проверить новый точный SHA.

- Каноническая рабочая копия после переноса: `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`.
- Основной origin: `https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.git`.
- Ветка: `codex/universal-business-foundation`; база нового main: `46cd866e059597aee75da4181dbb8c0928bbe57d`.
- Исходная база `76ce4e52f1c19b176586c8f69e55d4df735d1a1e` и прежний checkout сохранены; детали и свежий статус GitHub в [отчете переноса](REPOSITORY_TRANSITION_2026-10-04.md).
- Не reset/clean/restore и не перезаписывать существующую работу. Только один исполнитель меняет общий checkout и запускает PostgreSQL suite; другим агентам нужны свои ветки и рабочие копии.
- `handoff/` содержит локальные архивы и полную исходную историю, исключенные из Git. Промышленные deployment, миграции и Azure в этом переносе не выполнялись.

Прочитать AGENTS, [master plan](GORGONA_MASTER_PLAN.md), [текущий реестр с точными результатами](GORGONA_IMPLEMENTATION_STATUS.md), DEVELOPMENT, ADR-0009/0012/0014. Старые TODO и FAIL в архивных передачах не считать актуальными.

## Принятые границы

Все 39 направлений и исходная нумерация сохранены. GORGONA предоставляет ПО и посредническую платформу; склады, товары, перевозки и недвижимость принадлежат клиентам. `business_id == tenant_id == legacy salon_id`. Не создавать второй экземпляр компании/каталога/ресурсов для другой отрасли. Независимые перевозчики/франшизы остаются самостоятельными компаниями, группы/делегирование не обходят RLS. KA Nails — отдельный проект вне разработки, запуска и приемки этой платформы. Унаследованные брендовые материалы и результаты внешнего site gate ниже являются историческими примерами, не заданиями продолжения.

Azure ADR-0012 остается целевым размещением Booking. Камерный Local Gateway — другой продукт; не переносить его архитектуру сюда. Промышленный запуск требует отдельной приемки и разрешения. Офлайн — разрешенное чтение и черновики; значимые команды подтверждает сервер. Бизнес принимает деньги своих клиентов отдельно; подписка GORGONA отдельно, комиссии маркетплейса на первом этапе нет.

## Что делает текущий код

- Каталог 39 стабильных IDs/20 NAICS; гибридный профиль с форматами бизнеса, типизированные API и черновик с revision/Idempotency-Key. FORCE RLS/immutable snapshots миграции 0008. Полные workflow statuses всех отраслей остаются planned.
- Booking сохранен: цены, совместимость, снимки, PostgreSQL occupancy, guest capability, ISO1..7, локальные дни/DST, раздельные валюты и многointerval часы. Стоимость записи не является оплатой/выручкой.
- Ограниченное членство допускается только в проверенные рабочие обработчики. TenantAccess несет location_id из проверенного членства, GUC задается transaction-local. Роль проверяется отдельно, membership FOR SHARE сохраняет отзыв со следующего запроса.
- 0009: restrictive RLS для branch-owned parents/children; company-wide config недоступна. Новый /workspace обслуживает Calendar/Bookings/Staff/Overview. /me показывает scope, nav скрывает общие разделы. Общий service catalog читается для выбора услуги, изменения остаются business-wide.
- Owner invitation может содержать филиал своей компании; scope immutable, acceptance сохраняет его и при повторе. Scoped employee не приглашает и не управляет membership. Owner invitations business-wide.
- db/schema_guard.py проверяет утвержденные определения функции и политик PostgreSQL 18, roles/cmd/FORCE. Не заменять проверку определений проверкой одних имен или ненулевых выражений. Отсутствующая или измененная граница доступа дает 503 до запроса бизнес-данных; startup/readiness тот же guard. Не применять миграции автоматически на старте.
- Management receipt сначала проверяется против нынешнего scope. Старый receipt без timezone обогащается настоящей разрешенной location; исходные values сохраняются, операция не выполняется повторно. Измененный scope или revoke не открывают old receipt.
- Мобильный select ограничен контейнером. Проверять window.innerWidth против заданного viewport: сравнение только scrollWidth<=innerWidth пропускало расширение телефона с 390 до 418 px.

## Сохраненные доказательства исходного пакета

Полный финальный API-прогон: **379 PASS, 4 skipped, 113.70 с, exit 0**. Пропуски: три контейнерных gate и отдельный site gate KA Nails. Отдельно: location API и runtime/schema — 24 PASS; location API и оба management browser harness — 13 PASS за 25.25 с. Playwright: обычный кабинет — 3 PASS и 1 намеренный пропуск повторного мобильного цикла; филиальный — 2 PASS (desktop/mobile). SQL подтвердил четыре отмененные записи своего филиала; чужая запись сохранила CONFIRMED. Web: 6 unit-тестов PASS, типы/линт/формат/сборка PASS, 14 страниц. Ruff и mypy PASS, 123 Python-файла. Независимый reviewer подтвердил исправления и отсутствие новых существенных findings. Все результаты относятся к локальной технической проверке; промышленная эксплуатация не подтверждена.

Первоначальные проверки воспроизвел 403 для scoped staff, ValidationError legacy receipt, HTTP200 leakage при missing/weakened policy/function и viewport 418 вместо 390 px. Все соответствующие узкие проверки после исправления PASS. Документы проверены после последней правки; точный результат в реестре.

## Локальная тестовая база

Python 3.14: api/.venv/Scripts/python.exe; новое окружение установлено по прежнему uv.lock. Node 24 и web/node_modules настроены по прежнему package-lock.json. Chromium для новой машины проверять отдельно. Приложению новых dependencies не добавлено. Свежие 171 API unit/6 web unit, статические проверки и сборка новой копии описаны в отчете переноса; полная suite ниже остается прежним результатом. web содержит app/lib/components напрямую. Миграции api/src/gorgona_booking/db/migrations.

Изолированные PostgreSQL 18.6 binaries/data/log: `%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6`. Это собственный тестовый кластер, не service и не рабочая база. Нужны loopback 127.0.0.1, порт 51454, max_connections=250. Эти настройки ранее передавались при старте, поэтому не считать их сохраненными в postgresql.conf: без -o сервер однажды поднялся на 5432 и проверки истекли по timeout.

Поднимать detached Start-Process -WindowStyle Hidden, с явно проверенным datadir и аргументом pg_ctl `-o "-h 127.0.0.1 -p 51454 -c max_connections=250"`; проверять pg_ctl status и pg_isready именно на 51454. После приемки собственный сервер останавливается, данные сохраняются. Фактический финальный статус остановки фиксируется в реестре.

Приватное test-connection.json содержит port/password: никогда не выводить, не включать в repo/архив/сообщения. DSN формировать в памяти make_conninfo и передавать только pytest child environment. Роль admin gba_test_admin. Fixture создает одноразовую gba_test_* базу, применяет все миграции из каталога (сейчас десять) owner-ролью, проверяет runtime и удаляет свою базу. Не запускать две suites параллельно: имена fixture roles общие.

Порядок: web typecheck/lint/format/unit/build, затем `.venv/Scripts/python.exe -m pytest -q -rs --tb=short` в api с приватным GBA_TEST_ADMIN_DSN, GBA_REQUIRE_POSTGRES=1, GBA_REQUIRE_BROWSER=1. Focused: test_location_access.py и test_management_browser.py. Browser запускает Python harness с настоящим test-only OIDC и API; standalone npm test:management:location требует выданного harness окружения и не заменяет приемку.

## Следующая работа

1. Свежий Git/diff/реестр перед изменениями, сохранить все текущие файлы. Не снимать branch guard и не править исторические миграции.
2. Черновики юридических лиц и ограниченное делегирование (ADR-0016) проверены технически. Следующий связный пакет общей основы: подразделения и группы компаний; сводные отчеты читают только разрешенные наборы через делегирование и указывают владельца. Независимый перевозчик сохраняет свою компанию и владение данными. Несколько филиальных областей в членстве и в полномочии требуют собственных API/RLS/аудита/сценариев.
3. Draft→preview→validation→publication с readiness, затем единая занятость с безопасным переносом booking_allocations и CORE-04 до нового календаря TMS/аренды.
4. Далее финансы/смены/материалы и отраслевые циклы по master. Выбор отрасли не означает работающей TMS, рестораном или бухгалтерией.
5. Типизированные контракты, regression red→green, реальные focused/full gates, независимый review чувствительных изменений, обновление текущего evidence. Никаких fake providers, successful mocks или вымышленных бизнес-фактов.

В сохраненном локальном пакете контейнеры не проверялись; обязательные контейнеры/PG/браузеры GitHub CI `d97924f` PASS. Дополнительный внешний site gate остается skip и вне зависимости платформы. Реальные Stripe/DAT/Motive/Gusto/OIDC, Azure/staging, промышленная миграция, нагрузка/RPO/RTO и отраслевые пилоты не проверены. AI не менялся и не проверялся заново.

**Запрос следующему агенту:** Продолжи реализацию самостоятельной GORGONA по текущему master plan в указанном каноническом checkout и ветке. Сначала прочитай актуальный реестр и handoff, не удаляй uncommitted/untracked работу. Пакет филиальных операций уже технически реализован и проверен; не повторяй архивные TODO. Делегирование между компаниями уже реализовано на ветке `claude/keen-mayer-lg9ift`; начни с подразделений и групп компаний с сохранением владения, затем публикация и общая занятость. Сохрани все 39 отраслей, существующий движок записи и Azure ADR-0012. Другие проекты не разрабатывать и не включать в приемку платформы. Дай свежие проверенные результаты и границы по-русски; производственные действия отдельно.

## Сохраненные артефакты

Новый архив всех измененных файлов и patch: `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking\handoff\GORGONA_LOCATION_ACCESS_2026-10-04_CONTINUATION.zip`, рядом SHA256. Архив сверяется с MANIFEST.json; он не содержит credentials, окружение или PostgreSQL binaries и требует исходный Git HEAD выше. Прежний GORGONA_FOUNDATION_2026-10-04_CONTINUATION.zip сохранен без перезаписи. Снимки нового интерфейса: docs/plan/evidence/2026-10-04-location-access.

Собственный тестовый сервер после приемки остановлен; данные сохранены. Проверка документации после последней правки — git diff --check и проверка UTF-8/пробелов/локальных ссылок.
