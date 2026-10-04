# GORGONA — передача следующему агенту

**Текущий пакет 2026-10-04: группы компаний.** Ветка codex/company-groups
от 161509f0e3a298cef9d2929576a023a6dd2e93c3 (PR #4). Собственный checkout:
C:\Users\alexa\.codex\worktrees\booking-state-isolation\Gorgona Booking.
ADR-0018, миграция 0013, guard 65 определений; карта прав версии 4.
Группы с версиями принадлежат оператору. Участник принимает приглашение отдельной
командой своего владельца; ни приглашение, ни согласие не открывает чужие строки.

Первый отчет — количество записей по бизнесу, филиалу и статусу за явный период.
Участник выдает оператору report.booking.read; оператор назначает сотрудника.
Прямое владение обеими компаниями не дает обхода. Отчет использует одну транзакцию,
не более 25 приглашений на страницу, повторно проверяет согласие и действующее
делегирование, показывает владельца и покрытие филиалов. Юр. лицо unassigned,
поскольку в исходных записях нет этой связи. Клиентов, денег и копий данных нет.
Отзыв согласия, приглашения или полномочия убирает данные из следующего запроса;
общая блокировка защищает текущий запрос. Отчет и версии структуры/согласия
требуют READ COMMITTED. Общие записи групп закрыты в branch/delegation context.

Локально: базовая suite 512 passed / 4 skipped / 170.80 с; focused 76 passed /
8.96 с; реальный браузер групп 1 pytest scenario / 12.49 с (desktop/mobile);
web unit 23 passed / 868 мс; typecheck/lint/format/build14, Ruff/format/mypy147 PASS.
**Итоговая локальная suite: 546 passed, 4 skipped, 191.85 с, exit 0.**
Точный опубликованный SHA и CI см. в
[приемке групп](evidence/2026-10-04-company-groups/ACCEPTANCE.md).
Независимый review нашел регистр UUID в приглашении: browser red→green после
нормализации. Ни один прежний PASS не является проверкой нового SHA.
Код опубликован 1f199a2f198dbb89ef1f0c1177cf4668f1c344f4; draft [PR #5](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/5) поверх PR #4. **GitHub push CI PASS: 549 passed, 1 optional skip, 117.27 с**, [run 37228734875](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37228734875), job 111513719787; точный SHA 1f199a2f198dbb89ef1f0c1177cf4668f1c344f4. PostgreSQL/browser/container gates, сборка production image/web и статические проверки выполнены.
Рабочая копия владельца повторно проверена: чистая, eaa6233; отдельный тестовый PostgreSQL остановлен.

Следующая работа: несколько филиалов в областях данных членства и полномочия,
затем публикация конфигурации и единая занятость CORE-04. Финансовая консолидация,
SSO/SCIM, offline synchronization и все полные отраслевые циклы еще впереди.
Перед продолжением сверить PR и ветки; не перезаписывать checkout владельца.

**Предыдущий пакет 2026-10-04: подразделения.** Новая ветка `codex/company-departments`
поверх `b8647897cfa653e39f2e3188dbb9ad23c13e13fa` (PR #3). Собственный checkout:
`C:\Users\alexa\.codex\worktrees\booking-state-isolation\Gorgona Booking`.
Добавлены подразделения с версиями и опциональными ссылками своей компании:
родитель, один филиал, одно юридическое лицо. ADR-0017, миграция 0012, guard 49
определений, strict API/web и UI на странице бизнеса. Иерархия не допускает циклов;
запись требует READ COMMITTED, другие режимы отклоняются с откатом. Подразделение
не дает новых прав. Целевые проверки: 44 PASS с PostgreSQL и браузерами;
после защиты снимков транзакций 15 department tests PASS. Web: 20 unit PASS,
проверки типов, стиля и сборка PASS. Итоговая локальная suite: **512 passed,
4 skipped, 215.30 с, exit 0**, обязательные PostgreSQL 18.6 и браузеры.
Пропуски: три контейнерных gate и необязательный внешний site gate.
[Приемка](evidence/2026-10-04-departments/ACCEPTANCE.md).
Код подразделений опубликован: `931a11e5b1ecfcba770980565b2e78f88e58ab13`, draft [PR #4](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/4) в ветку PR #3.
GitHub CI кода: **515 passed, 1 optional skip, 107.96 с**,
[run 37224005256](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37224005256),
job `111499809655`; контейнерные gates выполнены. Рабочая копия владельца
осталась чистой на `eaa6233`; отдельный тестовый PostgreSQL корректно остановлен
после проверок, секреты не копировались в Git.
Следующий продуктовый пакет: группы компаний, явные согласия владельцев и сводные
чтения только по действующим полномочиям. Не копировать данные и не расширять
permissive-политики `gba.tenants`. Перед работой сверить все PR и SHA.

**Дополнение 2026-10-04: изоляция выбранной компании.** Продолжение находится в
`C:\Users\alexa\.codex\worktrees\booking-state-isolation\Gorgona Booking`,
ветка `codex/booking-state-isolation`, база `ef423f3c672bf2da219d6aef85f9a44cf1f37317`
(делегирование + документы). PR #1/#2 при проверке открыты и не слиты.
Исправлены три дефекта: `_booking_state`, подсчет владельцев перед публикацией,
список сотрудников. Восемь новых регрессий дали FAIL до исправлений и PASS после;
целевой набор вместе с onboarding: 14 PASS. Полная локальная suite: **479 passed,
4 skipped, 146.75 с, exit 0**; пропуски — три контейнера и дополнительный внешний
site gate. Детали, полные проверки и ограничения
в [приемке](evidence/2026-10-04-selected-company/ACCEPTANCE.md).
Опубликовано `951708af2b88b9436abf2ddadd6de608cbf9f99d`, draft [PR #3](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/3) поверх PR #2. GitHub CI этого SHA: **482 passed, 1 optional skip, 112.46 с**, [run 37221017342](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37221017342). Контейнерные gates выполнены. Этот пакет стал базой подразделений; текущая ветка указана выше.

**Актуально на 2026-10-04, после пакета групп компаний.** Этот документ самодостаточен: начните с него. Прежние версии сохранены без изменений: [checkpoint 3](NEXT_AGENT_HANDOFF_2026-10-04_CHECKPOINT_3.md), [checkpoint 2](NEXT_AGENT_HANDOFF_2026-10-04_CHECKPOINT_2.md), [checkpoint 1](NEXT_AGENT_HANDOFF_2026-10-04_CHECKPOINT_1.md). Их TODO и FAIL не считать актуальными без проверки.

> **English summary for agents.** Standalone GORGONA is one multi-tenant platform for 39 industries (FastAPI, PostgreSQL18 FORCE RLS, Next.js); business_id == tenant_id == legacy salon_id. Latest branch codex/company-groups builds on departments PR #4 / 161509f. Implemented: stage-0 fixes, hybrid industry profile, scoped workspace, legal drafts, delegation, departments and company groups with independent owner consent (ADR-0018, additive migration0013, guard65). Owner-only group.manage and separately delegable report.booking.read extend permissions map to version4. Participant grants to operator; a designated operator employee uses one transaction with current consent/grant/branch checks. Owning both businesses is no fallback. Counts are operational, legal entity unassigned; no clients, money or copies. READ COMMITTED and common invitation locks protect revocation. See group acceptance for exact fresh gates and SHA/CI. Next: multiple locations per membership/grant, configuration publication and shared resource occupancy CORE-04. Never overwrite owner work, rewrite applied migrations, bypass RLS or invent business facts. No merge, production migration or deployment without separate owner approval. Report PASS/FAIL/BLOCKED/NOT TESTED accurately.

## 1. Где находится работа

| Объект | Состояние |
|---|---|
| Репозиторий | [`alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new) |
| `main` | Только начальный README, `46cd866e059597aee75da4181dbb8c0928bbe57d` |
| `codex/universal-business-foundation` | Импорт исходников, аудит, юридические лица; `eaa62339cf82ea69b96f2e8ec346ede585729f02`. Draft [PR #1](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/1) → `main` |
| `claude/keen-mayer-lg9ift` | **База PR #3**: `eaa6233` + делегирование `bd1a138a11ebbe506010c243a5a02d9989bc1b52` + документы. Draft [PR #2](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/2) → `codex/universal-business-foundation` |
| `codex/booking-state-isolation` | Изоляция выбранной компании, `b8647897cfa653e39f2e3188dbb9ad23c13e13fa`; draft [PR #3](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/3) → ветка PR #2 |
| `codex/company-departments` | Подразделения: 161509f0e3a298cef9d2929576a023a6dd2e93c3 (код 931a11e + документация); draft [PR #4](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/4) → ветка PR #3 |
| codex/company-groups | Код 1f199a2, draft PR #5 → codex/company-departments; CI 549 PASS / 1 optional skip на 1f199a2; детали в [приемке групп](evidence/2026-10-04-company-groups/ACCEPTANCE.md) |
| CI | `.github/workflows/ci.yml` на push и PR: web проверки и сборка, PostgreSQL 18 в Docker, сборка production image, Ruff, mypy, pytest с обязательными PostgreSQL/браузерами/контейнерами |
| Исторический CI делегирования | [run 37212099717](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37212099717) на `bd1a138`: **474 passed, 1 skipped** (необязательный внешний site gate), 118.32 с |

Перед работой проверьте заново все PR цепочки и SHA веток (`git fetch`, `git log`). Продолжайте от codex/company-groups либо от ветки, в которую принят текущий пакет. PR #4 пока открыт и не слит на момент начала групп; main пока не содержит реализацию. Каждому агенту нужна своя ветка и свой checkout; общий checkout и общий тестовый кластер PostgreSQL одновременно использует один исполнитель.

Локальная рабочая копия владельца на Windows (`C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`, ветка `codex/universal-business-foundation`) могла содержать незакоммиченную работу. Не делать `reset`/`clean`/`restore` и не перезаписывать ее; после слияния PR сначала сохранить локальные изменения, затем `pull`.

## 2. Порядок чтения

1. `AGENTS.md` — правила для агентов.
2. [Master plan](GORGONA_MASTER_PLAN.md) — целевая спецификация, 39 направлений, 28 критериев приемки (§14.1.1).
3. [Реестр реализации](GORGONA_IMPLEMENTATION_STATUS.md) — фактические результаты; верхний раздел — текущий пакет.
4. [Аудит выполнения плана](GORGONA_PLAN_AUDIT_2026-10-04.md) — состояние всех критериев.
5. ADR: [0009](../adr/0009-tenant-context-derivation.md) (контекст компании), [0012](../adr/0012-azure-hosting.md) (Azure), [0014](../adr/0014-location-scoped-workspace.md) (филиалы), [0015](../adr/0015-tenant-owned-legal-entity-drafts.md) (юр. лица), [0016](../adr/0016-limited-cross-business-delegation.md) (делегирование), [0017](../adr/0017-company-department-drafts.md) (подразделения), [0018](../adr/0018-consented-company-groups.md) (группы).
6. `docs/DEVELOPMENT.md` — маршруты, разделы по пакетам, запуск проверок.
7. Доказательства: [юр. лица](evidence/2026-10-04-legal-entities/ACCEPTANCE.md), [делегирование](evidence/2026-10-04-delegation/ACCEPTANCE.md).

## 3. Намерение владельца и неизменяемые границы

- GORGONA — одна универсальная платформа для индивидуальных специалистов, малого бизнеса, сетей, франшиз и корпораций; все 39 направлений и их номера сохраняются. GORGONA — поставщик ПО и посредник: склады, товары, перевозки и недвижимость принадлежат клиентам.
- `business_id == tenant_id == legacy salon_id`. Не создавать вторую компанию, каталог или ресурсы для другой отрасли. Независимые перевозчики, франшизы и продавцы остаются самостоятельными компаниями; группы и делегирование не обходят RLS.
- Существующий движок записи, старый `/v1/salons/...` API и клиентский поток сохраняются.
- KA Nails — отдельный проект вне разработки и приемки этого репозитория. Исторические брендовые материалы — только наследие.
- Не выдумывать бизнес-факты: часы, длительности, цены, сотрудников, политики, регистрационные данные, валюты, налоги. В тестах — только явные FAKE-значения.
- Azure по ADR-0012 — целевое размещение. Local Gateway камер — другой продукт. Промышленные миграции, deployment, подключение провайдеров и платежей требуют отдельной приемки и явного разрешения владельца.
- Офлайн — только разрешенное чтение и черновики; значимые команды подтверждает сервер. Бизнес принимает деньги своих клиентов сам; подписка GORGONA отдельно; комиссии маркетплейса на первом этапе нет.
- Отчетность: PASS / FAIL / BLOCKED / NOT TESTED, точные числа, точный SHA. Зеленый CI одного SHA не переносится на другой.

## 4. Что реализовано

| Пакет | Миграция | Решение | Доказательство | Граница |
|---|---|---|---|---|
| Этап 0: ISO-дни, локальные даты/DST, стоимость записей ≠ оплата, филиальные права | — | реестр, checkpoint 1–2 | BASE-01…04 в аудите | Ledger оплат нет |
| Каталог 39 отраслей (20 секторов NAICS) и гибридный профиль бизнеса с версиями | 0008 | реестр | CORE-01/02 частично | Публикации конфигурации нет |
| Филиальный рабочий кабинет: одно членство — один филиал, restrictive RLS, guard | 0009 | ADR-0014 | реестр, снимки | Несколько филиалов на членство не реализованы |
| Закрытие development `/v1/holds` вне local/test/ci | — | аудит P1 | аудит | — |
| Черновики юридических лиц с неизменяемыми версиями | 0010 | ADR-0015 | приемка, CI `d97924f` | Регистрация, финансы не подтверждаются |
| **Делегирование между независимыми компаниями** | 0011 | ADR-0016 | приемка, CI `bd1a138` | Пакет 0011 не включает группы; см. 0013. Offline/TMS не реализованы |
| **Подразделения** | 0012 | ADR-0017 | [приемка](evidence/2026-10-04-departments/ACCEPTANCE.md) | Черновики структуры; назначения сотрудников и несколько филиалов на подразделение не реализованы |
| **Группы компаний** | 0013 | ADR-0018 | [приемка](evidence/2026-10-04-company-groups/ACCEPTANCE.md) | Независимые согласия и ограниченные отчеты записей; финансовой консолидации/SSO/нескольких областей нет |

Все полные отраслевые циклы (TMS, рестораны, аренда, строительство, финансы, склад) остаются `planned`. Выбор отрасли в профиле ничего не включает.

### Делегирование кратко (ADR-0016)

- Владелец выдает полномочие другой компании: цель, права из booking.read, booking.write, catalog.read, staff.read, report.booking.read (запись требует трех чтений), один филиал или все, `[valid_from, valid_until)` не более 366 дней на версию. Версии только добавляются; отзыв окончателен; обслуживающая компания неизменна. Право `delegation.manage` — только у владельца без филиального ограничения (карта прав версии 4).
- Обслуживающая компания назначает своих активных сотрудников (`delegation_designations`, принадлежат ей).
- 13 операционных обработчиков принимают делегированный доступ (`allow_delegation=True`): workspace, overview, availability, bookings (список, деталь, создание, перенос, отмена), clients, clients/history, services (GET), staff (GET), staff schedule (GET).
- Каждый запрос: этап A (контекст владельца) — кандидаты назначений; этап B (контекст обслуживающей компании) — `FOR SHARE` членства и назначения, компания активна; этап C (контекст владельца) — общая advisory-блокировка полномочия и повторная проверка текущей версии. Запись `delegation.access` в аудит владельца; `gba.actor = delegate:{user}@{serving}/grant:{grant}`; ключи идемпотентности остаются у пользователя.
- Ограничивающие политики не дают делегированной транзакции читать членства, других пользователей, приглашения, юр. лица, профиль, подтверждения фактов, домены, историю аудита и записи делегирования.

## 5. Карта кода

| Область | Файлы |
|---|---|
| Авторизация и контекст | `api/src/gorgona_booking/tenancy/authorization.py` (`authorized_tenant`, членство, филиал, делегирование, platform support), `auth/permissions.py`, `auth/principal.py` |
| БД | `db/migrations/0001…0013`, `db/schema_guard.py` (65 определений), `db/pool.py` (роль runtime, readiness), `db/provisioning.py` |
| Бизнес-основа | `business/{catalog,contracts,service}.py`, `business/legal_entit*.py`, `business/delegation*.py`, company_groups.py, group_membership.py, group_reports.py, group_contracts.py |
| API | `api/{salons,businesses,legal_entities,delegations,members,setup,platform,customer,health}.py`, ошибки — `api/errors.py` |
| Запись | `booking/*`, `customer/*`, `catalog/*` |
| Web | `web/lib/management-api.ts`, `management-contracts.ts` (центральная проверка ответов), `*-contracts.ts`, `web/components/management-layout.tsx`, `delegations.tsx`, `legal-entities.tsx`, страницы `web/app/*` |
| Тесты | `api/tests/unit`, `api/tests/integration` (`conftest.py`, `seed.py`, `customer_support.py`, `live_server.py`, `test_management_browser.py` — OIDC/PKCE harness), `web/tests/*.spec.ts` |

Семейства API: `/v1/salons/{id}/...` (сотрудники), `/v1/businesses/{id}/...` (новая основа: профиль, каталог, юр. лица, делегирование), `/v1/me`, `/v1/customer/...` (публичная запись), `/v1/platform/...`, `/v1/invitations/accept`, `/health/{live,ready}`.

## 6. Правила изменения кода

**Миграции.** Новый файл `NNNN_name.sql`, примененные не переписывать. Для каждой таблицы — `enable` и `force row level security` (это проверяет `tests/unit/test_migration_files.py`); в тексте миграции не должно быть строк `security definer` и `bypassrls`, даже в комментариях. Runtime получает минимальные права (часто по столбцам). Неизменяемость — триггерами.

**Guard.** Любая новая restrictive-политика филиала или делегирования и любая межкомпанейская permissive-политика добавляется в `DEFINITIONS` в `db/schema_guard.py` в канонической записи PostgreSQL 18: примените миграцию к временной базе и возьмите `pg_get_expr(polqual/polwithcheck)`. Для таблиц делегирования и групп guard требует точный набор политик. Тест `test_scoped_work_fails_closed_when_schema_boundary_is_missing` удаляет `gba.current_location_id()` каскадно и восстанавливает политики 0009/0010/0011/0012/0013 — добавляйте туда новые зависимые политики.

**Обработчики.** Доступ филиала (`allow_location_scope=True`) и делегирования (`allow_delegation=True`) включается только после проверки обработчика. В таких обработчиках: явные ссылки проверять через `access.require_location`, для аудита и `created_by` использовать `access.actor`, ключ идемпотентности — `principal.actor`. Делегированный обработчик не должен читать таблицы компании. Права, которые можно делегировать, перечислены в `DELEGABLE_PERMISSIONS`.

**Таблица `gba.tenants`.** Не добавлять permissive-политики на чтение: часть запросов читает ее без фильтра и полагается на одну строку (см. дефект в §8).

**Контракты.** Pydantic-модели с `extra="forbid"`, версия схемы, `expected_revision`, `Idempotency-Key`. В web каждый новый маршрут нужно добавить в `managementResponseSchema`, иначе он намеренно отклоняется; ответы проверяются строгими zod-схемами и на совпадение ID. Новые web unit-тесты добавлять в скрипт `test:unit` в `web/package.json`.

**Аудит и ошибки.** Изменения прав и полномочий записываются в `gba.audit_events` в той же транзакции. Новые доменные ошибки наследуют `DomainError`; HTTP-код задается в `api/errors.py`.

## 7. Среды и проверки

**Порядок проверок:** `web`: `npm run typecheck`, `lint`, `format:check`, `test:unit`, `build`; затем в `api`: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`, `uv run pytest -q -rs` с `GBA_TEST_ADMIN_DSN`, `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1`. Браузерные harness требуют свежей сборки `web/out`. Две suite параллельно не запускать: имена тестовых ролей общие.

**Focused-наборы:** группы — test_group_contracts.py, test_company_groups.py, test_delegation_browser.py (groups), test_location_access.py;  делегирование — `tests/unit/test_delegation_contracts.py`, `tests/integration/test_delegations.py`, `tests/integration/test_delegation_browser.py`; юр. лица — `test_legal_entity_contracts.py`, `test_legal_entities.py`; филиалы — `test_location_access.py`, `test_management_browser.py`; права — `test_authz_api.py`, `test_roles_and_migrations.py`, `test_tenant_isolation.py`.

**Облачный Linux-контейнер (так проверялся пакет делегирования):**

1. PostgreSQL 18: apt-репозиторий PGDG может быть закрыт сетью. Работает npm: `npm pack @embedded-postgres/linux-x64@18.4.0-beta.17`, распаковать, в папке пакета выполнить `node scripts/hydrate-symlinks.js`, скопировать `native/` вне репозитория (например, `/opt/pg18`). PostgreSQL не запускается от root: создать отдельного пользователя, `initdb -D <data> -U <admin> --pwfile=<временный файл> --auth=scram-sha-256 -E UTF8 --locale=C.UTF-8`, удалить файл пароля, затем `pg_ctl -D <data> -l <log> -o "-h 127.0.0.1 -p 55432 -c max_connections=250" -w start`. Пароль генерировать, не записывать в репозиторий и сообщения; DSN передавать только окружению pytest.
2. Python: нужен финальный 3.14 (uv 0.8 ставил 3.14.0rc2, на котором pydantic падает при сборе тестов). Свежий uv из PyPI: `uv python install 3.14`, затем в `api`: `uv sync --locked --python 3.14.8` (или новее).
3. Node 24 с nodejs.org с проверкой SHA256; в `web`: `npm ci --ignore-scripts`.
4. Chromium: Playwright 1.63 ожидает сборку 1243. Если CDN Playwright закрыт и установлена другая сборка, создайте локальную папку-прокладку вне репозитория (`chromium-1243/chrome-linux64` → установленная `chrome-linux`; `chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell` → `headless_shell`) и укажите ее в `PLAYWRIGHT_BROWSERS_PATH`. CI ставит совпадающую сборку и остается решающим.
5. Docker daemon в таком контейнере обычно недоступен: три контейнерных gate пропускаются локально и выполняются в CI.

**Windows (рабочая копия владельца):** собственный кластер PostgreSQL 18.6 в `%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6`, loopback, порт 51454, `max_connections=250`; эти параметры передавать при запуске через `pg_ctl -o`, они не сохранены в `postgresql.conf`. Приватный `test-connection.json` никогда не выводить и не коммитить. Подробности — в [checkpoint 2](NEXT_AGENT_HANDOFF_2026-10-04_CHECKPOINT_2.md).

**Стандарт доказательств.** Новое поведение — regression red→green; для защит безопасности полезны мутационные проверки (намеренно сломать защиту и увидеть падение теста, затем вернуть код). Снимки экрана — только FAKE-данные, сжимать (`pngquant`) и хранить в `docs/plan/evidence/<дата-пакет>/`. В реестр записывать точные числа, время, SHA, ссылку на CI и все пропуски. Пропуск не равен PASS.

## 8. Открытые проблемы и блокеры

| Проблема | Что известно | Что делать |
|---|---|---|
| **Исправлено: выбор компании** | `_booking_state`, подсчет владельцев и список сотрудников явно ограничены выбранной компанией; восемь red→green регрессий | Продолжать от `codex/booking-state-isolation` либо ветки, куда принят этот пакет; проверить свежие SHA/CI |
| Release gates из аудита | `deploy-staging.yml` не требует зеленый CI выбранного SHA; branch protection нет; пакет `ai/` не проверяется в CI | Решать перед staging с разрешения владельца |
| HawkScan DAST | Не запускался: нужен Docker daemon и `HAWK_API_KEY` | Окружение с Docker и ключом от владельца |
| Codeflash (плагин владельца) | Сервис `app.codeflash.ai` закрыт сетью, нет `CODEFLASH_API_KEY`, нет конфигурации в `web/package.json` | Владелец разрешает домен и ключ в настройках окружения и решает, добавлять ли конфигурацию |
| Dev dependency audit | Свежий полный npm audit: 5 high в цепочке ESLint/braces, patched braces version нет; production-only audit 0 | Не делать несовместимый downgrade Next/ESLint; проверить безопасное исправление отдельно, см. приемку групп |
| Не проверено | Реальный IdP, Stripe/DAT/Motive/Gusto, Azure/staging, промышленная миграция, нагрузка 1000 компаний/100–200 RPS, RPO/RTO, отраслевые пилоты, AI | Отдельные этапы master plan |

## 9. Следующая работа (порядок и приемка)

1. **Исправлено в ветке `codex/booking-state-isolation`:** `_booking_state`,
   подсчет владельцев и список сотрудников. Перед продолжением сверить PR и SHA;
   не повторять исправление и не считать локальный PASS проверкой другого SHA.
2. **Подразделения реализованы** (ADR-0017, миграция 0012; см. текущую приемку). Ниже исходный критерий пакета (master plan §4, §12.2). Сущность компании с версиями по образцу юр. лиц: внутренняя ссылка, название, при необходимости родитель (иерархия без циклов) и связи с филиалами/юр. лицами только через проверенные ссылки той же компании. FORCE RLS, политики `*_unrestricted_scope` и `*_delegation_scope` (+ guard), idempotency, expected revision, аудит, UI на странице бизнеса. Приемка: создание/история/конфликт/повтор без дубля, изоляция компаний, запрет для филиальных и делегированных пользователей, откат при ошибке.
3. **Группы компаний реализованы ограниченным пакетом** ADR-0018/0013 (CORE-03, ENTERPRISE-01 частично). Первый отчет — записи по филиалу/статусу, legal entity unassigned. Финансовая консолидация не реализована. Ниже исходная приемка: Группа принадлежит компании-оператору; компании-участники вступают только явным согласием своего владельца; членство в группе само не дает строк других компаний. Сводный отчет читает только данные, разрешенные действующими полномочиями (расширение ADR-0016 на отчетные права), и показывает владельца и юр. лицо каждой строки. Приемка: участник без полномочия не виден в отчете; отзыв согласия или полномочия убирает данные со следующего запроса; данные не копируются.
4. **Несколько областей данных** для членства и полномочия (несколько филиалов) — свои API, RLS, аудит, сценарии.
5. **Конфигурация draft → preview → validation → publication** с готовностью модулей (CORE-02 полностью): неизменяемая опубликованная версия, ожидаемая версия, повтор команды без новой версии.
6. **Единая занятость ресурсов и перенос `booking_allocations`** (CORE-04, master plan §12.2.1): расширить схему → перенести интервалы → сверить → один транзакционный механизм для старого API и новых модулей → конкурентные проверки → переключить чтение → совместимое представление и откат. Пока переход не принят, новые модули не резервируют ресурсы в отдельной таблице.
7. Далее этап 2: финансы (FIN-01…03), смены и табели (WORK-01), материалы (STOCK-01), реестр допуска провайдеров; затем отраслевые циклы по master plan.

## 10. Чек-листы

**Перед началом:** `git fetch` и статус PR; прочитать реестр и этот документ; поднять тестовую среду; прогнать базовую suite на неизмененном дереве и записать результат.

**Перед commit/push:** web и Python проверки полностью; focused и полная suite с обязательными PostgreSQL/браузерами; обзор своего diff на безопасность (RLS, авторизация, guard, идемпотентность, аудит); обновить реестр, handoff, аудит, `docs/DEVELOPMENT.md`, при необходимости ADR; `git diff --check`, UTF-8 и локальные ссылки; не коммитить секреты, `.env`, `test-connection.json`, `web/out`, `test-results`, данные PostgreSQL.

**PR:** отдельная ветка; draft PR в актуальную базовую ветку (пока предыдущие PR не слиты, использовать stacked PR поверх самого нового пакета, чтобы diff был отдельным); после push проверить CI точного SHA и записать его результат отдельным коммитом документации.

## 11. Запрос следующему агенту

**RU:** Продолжи реализацию самостоятельной GORGONA по актуальному master plan. Сначала прочитай `docs/plan/NEXT_AGENT_HANDOFF_2026-10-04.md`, реестр и ADR-0014/0015/0016/0017/0018, проверь состояние всей цепочки draft PR и продолжай от самой новой ветки. Не удаляй чужую незакоммиченную работу, не переписывай примененные миграции, не обходи RLS и не выдумывай бизнес-факты. Исправления `_booking_state`, подсчета владельцев и списка сотрудников уже в PR #3, подразделения в PR #4; группы со сводными counts по разрешенным записям добавлены по ADR-0018. Продолжай с нескольких филиалов в областях доступа, потом публикацией конфигурации и единой занятостью (CORE-04). Для каждого пакета: ADR, миграция с guard, типизированные контракты, regression red→green, полные проверки с PostgreSQL 18 и браузерами, обновленные реестр и handoff, точные результаты по-русски; производственные действия — только с отдельного разрешения владельца.

**EN:** Continue the standalone GORGONA platform per the current master plan. First read `docs/plan/NEXT_AGENT_HANDOFF_2026-10-04.md`, the implementation registry and ADR-0014/0015/0016/0017/0018, check every PR in the current stacked chain, and continue from the newest branch. Do not discard others' uncommitted work, never rewrite applied migrations, never bypass RLS, never invent business facts. The `_booking_state`, owner-count and member-list fixes are in PR #3; departments and consented company groups are implemented (ADR-0017/0018); continue with multiple locations per membership/grant, then configuration publication and shared resource occupancy (CORE-04). For each package: ADR, migration with guard updates, typed contracts, red→green regression tests, full gates with PostgreSQL 18 and browsers, updated registry and handoff, exact results in Russian; production actions only with the owner's separate approval.

## 12. История и источники

- [Отчет о переносе репозитория](REPOSITORY_TRANSITION_2026-10-04.md): сохранение исходной истории, архивы `handoff/` вне Git.
- [Аудит плана](GORGONA_PLAN_AUDIT_2026-10-04.md), реестр и его checkpoint-копии: [1](GORGONA_IMPLEMENTATION_STATUS_CHECKPOINT_1.md), [2](GORGONA_IMPLEMENTATION_STATUS_CHECKPOINT_2.md).
- Передачи: [checkpoint 1](NEXT_AGENT_HANDOFF_2026-10-04_CHECKPOINT_1.md), [checkpoint 2](NEXT_AGENT_HANDOFF_2026-10-04_CHECKPOINT_2.md), [checkpoint 3](NEXT_AGENT_HANDOFF_2026-10-04_CHECKPOINT_3.md).
