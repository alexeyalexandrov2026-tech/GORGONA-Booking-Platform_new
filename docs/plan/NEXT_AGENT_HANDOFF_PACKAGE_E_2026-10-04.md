# GORGONA — полная передача: пакет E (контрагенты, документы, договоры) и шаг E0

> Source snapshot received 2026-10-04. Original preserved in the owner's handoff777 archive. E0 now has independent fresh evidence in [the current handoff](NEXT_AGENT_AUDITED_E0_2026-10-04.md). E1–E3 remain planned; no such migrations are applied. Statements below about prior tests/approval are the supplied record, not a new execution.


Дата: 2026-10-04, поздний вечер. Исполнитель: Claude (сессия Claude Code). Документ самодостаточен: следующий агент начинает отсюда и ничего не теряет. Краткая версия — раздел 0 [NEXT_AGENT_START_HERE.md](NEXT_AGENT_START_HERE.md).

---

## 1. Где проект и что в Git

| Что | Значение |
|---|---|
| Рабочая копия | `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking` |
| Репозиторий | `https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new` |
| Ветка | `codex/universal-business-foundation` (draft PR #1; `main` только README; merge не делать) |
| HEAD | `2f16380` «Record configuration package acceptance on green CI» |
| CI HEAD | **PASS**: push 37245076876, PR 37245079640 (проверено через публичный API Actions) |
| Незакоммичено | всё из раздела 3 ниже — **не удалять, не reset/clean/restore** |

Проверка CI без `gh`: `https://api.github.com/repos/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs?branch=codex/universal-business-foundation` (статусы видны без авторизации, логи — нет).

Незакоммиченные файлы на момент передачи (`git status --short`):

```
 M api/src/gorgona_booking/api/setup.py
 M api/src/gorgona_booking/customer/queries.py
 M api/src/gorgona_booking/db/provisioning.py
 M api/src/gorgona_booking/identity/invitations.py
 M api/src/gorgona_booking/onboarding/fake_seed.py
 M api/src/gorgona_booking/onboarding/readiness.py
 M api/src/gorgona_booking/onboarding/service.py
 M api/src/gorgona_booking/tenancy/resolver.py
 M api/tests/integration/test_onboarding.py
 M web/lib/management-api.ts
 M web/lib/management-contracts.ts
 M web/tests/management-contracts.spec.ts
?? api/tests/integration/test_cross_company_reads.py
?? api/tests/unit/test_cross_tenant_queries.py
 -- выше: шаг E0 (код + тесты) --
?? docs/adr/0020-counterparties-documents-and-contracts.md        (ADR-0020, отдельный docs-коммит)
?? docs/plan/PACKAGE_E_PLAN_2026-10-04.md                          (утвержденный план)
?? docs/plan/NEXT_AGENT_HANDOFF_PACKAGE_E_2026-10-04.md            (этот файл)
 M docs/plan/NEXT_AGENT_START_HERE.md                              (раздел 0)
 M docs/plan/NEXT_AGENT_HANDOFF_2026-10-04.md                      (указатель на раздел 0)
```

Вне Git (каталог `handoff/` в `.gitignore`): `handoff/package-e-drafts/` — непроверенные черновики E1 (раздел 6) и `run_pytest.py`.

---

## 2. Решения владельца (2026-10-04) — обязательны

1. **Файлы** документов — в PostgreSQL (отдельная таблица `bytea`), до 10 МБ. Проверки: размер, тип PDF/PNG/JPEG по сигнатуре = заявленный Content-Type, sha256, отказ PDF с активным содержимым. Антивируса нет → статус `not_scanned`; в staging/production загрузка 503 `FILE_SCANNING_NOT_CONFIGURED`, пока не подключен сканер. Без новых зависимостей.
2. **Клиенты из записей** (`gba.booking_customers`) связываются с контрагентами только ручным подтверждением; кандидаты по нормализованным email/телефону; `booking_customers` не меняется; история связей сохраняется; автослияния нет.
3. **Доступ**: новые права `counterparties.read/manage`, `documents.read/manage` (PERMISSIONS_VERSION 3→4) только owner/manager с доступом ко всей компании. Филиальные, делегаты (ADR-0017) и поддержка платформы — нет.
4. **Шаг E0 первым**: исправить дефекты изоляции.
5. Одобрение плана = согласование ADR-0020 и разрешение на реализацию по шагам с коммитом и push в рабочую ветку после каждого шага. Без merge, deploy, промышленных миграций.

Порядок: **E0 → ADR-0020 (docs) → E1 (миграция 0015) → E2 (0016) → E3 (0017)**. Полный план: [PACKAGE_E_PLAN_2026-10-04.md](PACKAGE_E_PLAN_2026-10-04.md). Решения ADR: [ADR-0020](../adr/0020-counterparties-documents-and-contracts.md).

Постоянные правила (AGENTS.md, START_HERE §3): самостоятельная GORGONA, KA Nails вне работы; 39 отраслей и 28 критериев сохраняются; `business_id == tenant_id == salon_id`; не выдумывать бизнес-факты; исторические миграции не менять; типизированные версионированные контракты; idempotency + expected revision; FORCE RLS + schema guard; атомарный аудит; red→green; focused и полные проверки; CI точного SHA; evidence; без fake providers/успешных моков; после каждого шага обновлять handoff, реестр, аудит, DEVELOPMENT, ADR/evidence; один исполнитель на рабочую копию и тестовый кластер; отчет по-русски PASS/FAIL/NOT TESTED; секреты не выводить.

---

## 3. Что сделано

### 3.1 Шаг E0 — дефекты изоляции (код готов, НЕ закоммичен)

Причина: permissive-политики `tenants_member_read`, `tenants_platform_admin_read` (0004_identity.sql:322-331) и `memberships_self_read` (0004:98-99) складываются с tenant-политикой, поэтому SQL без явного фильтра компании видел строки других компаний вызывающего.

Эксплуатируемые дефекты (воспроизведены):
- `api/setup.py` `_booking_state` читал `select booking_state from gba.tenants` без фильтра → менеджер двух компаний / платформенный админ получал состояние чужой компании: readiness показывал неверный `booking_state`, правка часов в не-live компании записывалась `confirmed`, `unconfirmed` факт отклонялся `SALON_IS_LIVE`. Исправлено: `_booking_state(conn, salon_id)` с `where id = %s`, три вызова.
- `onboarding/readiness.py` `_SNAPSHOT`: подсчет владельцев без фильтра → платформенный админ, владеющий другой компанией, мог перевести в live компанию без владельца. Исправлено: `tenant_id = gba.current_tenant_id()`.

Защитные фильтры (сейчас не эксплуатируемы): `identity/invitations.py` (проверка «уже участник», выбор/обновление/чтение членства по id, проверка последнего владельца, join `gba.tenants` в принятии приглашения — `t.id = gba.current_tenant_id()`), `onboarding/service.py` (`_owner_invitation`, `_FINGERPRINT_QUERIES` — отпечаток не меняется, owner-путь без user context), `tenancy/resolver.py`, `customer/queries.py` `live_name`, `onboarding/fake_seed.py`, `db/provisioning.py` `set_membership_status`.

Web: `web/lib/management-contracts.ts` — `readinessSchema` (strictObject) = API `ReadinessView` `{salon_id, ready, booking_state: not_live|live, items[{fact, status: confirmed|unconfirmed|missing, detail}]}`; маршрут GET `/readiness`; PUT `/business-hours`, `/policies`, `/facts/*` только для PUT. `web/lib/management-api.ts`: `savePolicies/saveBusinessHours/saveFact` возвращают `Readiness` (UI-вызовов этих функций нет).

Тесты:
| Тест | Результат |
|---|---|
| `api/tests/integration/test_cross_company_reads.py` | 7 тестов: 5 падали до исправления (readiness менеджера и поддержки, правка часов, unconfirm, факт owner), 2 регрессии (suspend членства другой компании → 404; проверка дубля приглашения только в своей компании) были зелеными и до — **не считать воспроизведением** (review) |
| `test_onboarding.py::test_go_live_ignores_owner_memberships_elsewhere` | до: 200 (go-live прошел), после: 409 `NOT_READY`, missing = [owner] |
| `api/tests/unit/test_cross_tenant_queries.py` | статический guard (AST + текстовый анализ): SQL к `gba.tenants/memberships/tenant_hosts` обязан иметь фильтр компании на том же уровне выражения; OR на уровне — подозрение; регистр не важен; кавычки и динамические имена `gba.{}` сообщаются; allowlist исключает только фрагмент. До исправления: 14 находок |
| `web/tests/management-contracts.spec.ts` «salon readiness responses match the API ReadinessView» | до: падал (Unrecognized contract), после: PASS |

Результаты локально (PostgreSQL 18.6, кластер 127.0.0.1:51455):
- Полная suite + браузеры (`GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1`): **538 passed, 4 skipped, 387.64 с** (skips: 3 container gate без Docker, внешний site gate). Это было ДО двух последних правок (фильтр в принятии приглашения, усиление guard).
- После последних правок: Ruff check/format PASS, strict mypy PASS (153 файла), API unit **271 passed**, focused integration (`test_cross_company_reads`, `test_invitations_api`, `test_onboarding`) **27 passed**.
- Web: typecheck, ESLint, Prettier, unit **42 passed**, build PASS.
- Независимый review (subagent в той же сессии): дефектов корректности/безопасности нет; подтверждено, что эксплуатируемы только два места; замечания по guard учтены; отмечено, что strictObject даст INVALID_RESPONSE на уже закоммиченный PUT, если API добавит поле (допустимо, PUT идемпотентен); опционально — типизировать `ReadinessView.booking_state` и `ReadinessItemView.status` как `Literal` в `api/setup.py`.

### 3.2 ADR-0020 — написан, не закоммичен

`docs/adr/0020-counterparties-documents-and-contracts.md` — Context/Decision/Acceptance/Consequences по шагам E1–E3, решения владельца, вне-рамок. Статус: accepted by the owner 2026-10-04 вместе с планом. После каждого шага вписывать точный SHA и ссылку на приемку.

### 3.3 Черновики E1 — `handoff/package-e-drafts/` (НЕ проверены, НЕ запускались)

| Файл | Назначение | Куда перенести |
|---|---|---|
| `0015_counterparties.sql` | 5 таблиц + функции + триггеры + политики (см. 6.1) | `api/src/gorgona_booking/db/migrations/0015_counterparties.sql` |
| `module_gate.py` | `require_module`, `module_writes(*module_ids)` (GBM01 → 409 `MODULE_DISABLED`) | `api/src/gorgona_booking/business/module_gate.py` |
| `counterparty_contracts.py` | Pydantic-контракты (вход, представления, квитанции, решения, связи) | `business/counterparty_contracts.py` |
| `counterparty_matching.py` | SQL дубликатов, проверки до создания, кандидатов из записей | `business/counterparty_matching.py` |
| `counterparties.py` | сервис: загрузка, список, история, сохранение, merge/distinct/separate, link/unlink, связанные записи, история связей | `business/counterparties.py` |
| `run_pytest.py` | запуск pytest с приватным DSN только в окружении дочернего процесса | оставить вне repo |

---

## 4. Ближайшие шаги (чек-лист)

### 4.1 Завершить E0
1. `git status` — убедиться, что файлы раздела 1 на месте.
2. Поднять кластер (раздел 8), `cd web && npm run build`, полная suite с браузерами. Ожидается ≈538 passed / 4 skipped.
3. Коммит **только E0**: 8 файлов `api/src`, `api/tests/integration/test_onboarding.py`, `test_cross_company_reads.py`, `test_cross_tenant_queries.py`, 3 файла `web`. Сообщение, например: «Filter cross-company reads on tenants and memberships; align readiness web contract» + строка `Co-Authored-By` по требованию среды.
4. `git push`, дождаться CI точного SHA (push и PR) через публичный API.
5. Коммит приемки: `docs/plan/evidence/2026-10-04-isolation-fixes/ACCEPTANCE.md` (формат как `evidence/2026-10-04-groups/ACCEPTANCE.md`: Direct evidence таблица, Boundaries), строка в `GORGONA_IMPLEMENTATION_STATUS.md`, `GORGONA_PLAN_AUDIT_2026-10-04.md` (BASE/изоляция), `NEXT_AGENT_START_HERE.md` (§2 таблица, §6 — убрать два исправленных открытых вопроса: memberships без фильтра и readiness `missing/items`), handoff, при необходимости `DEVELOPMENT.md`.

### 4.2 ADR-0020
Отдельный docs-коммит: ADR-0020 + `PACKAGE_E_PLAN_2026-10-04.md` + этот файл + ссылки в START_HERE. Push (CI для docs тоже запускается).

### 4.3 E1, E2, E3 — по разделам 5–7. Для каждого: код + red→green → focused → web проверки → полная suite → review → коммит → push → CI → коммит приемки (evidence + перевод модуля в `technically_verified` + обновление `test_configuration_contracts.py:94` + все документы).

---

## 5. Общие механизмы (вводятся в E1)

### 5.1 Права (`api/src/gorgona_booking/auth/permissions.py`)
- `PERMISSIONS_VERSION = 4`; в `Permission`: `COUNTERPARTIES_READ = "counterparties.read"`, `COUNTERPARTIES_MANAGE`, `DOCUMENTS_READ`, `DOCUMENTS_MANAGE`.
- Добавить только в `_MANAGER` (owner наследует). НЕ в `DELEGABLE_PERMISSIONS`, НЕ в `PLATFORM_SUPPORT_PERMISSIONS`.
- Маршруты без `allow_location_scope`/`allow_delegation` → отказы существующими путями `tenancy/authorization.py` (филиал: `require_unrestricted_membership`; делегат: `_delegated_access` → None; поддержка: read-only/нет права).
- Тесты: `api/tests/unit/test_permissions.py` (четыре права только у manager/owner, не делегируемы, не у платформы); `test_delegation_contracts.py:86-96` (список «никогда не делегируются») и обобщить текстовый тест `:117-138` на все `api/*.py`.

### 5.2 Шлюз модуля в БД
- Функция `gba.require_enabled_module()` (в черновике 0015): shared advisory lock `hashtextextended('gba:business-configuration:' || tenant, 0)` (тот же ключ, что `authorized_tenant(exclusive="business-configuration")` → `f"gba:{exclusive}:{salon_id}"`), затем `not exists (... business_module_states ... module_id = tg_argv[0] and enabled)` → `raise ... errcode = 'GBM01'`.
- **Семантика обратная бронированию**: нет строки состояния = выключено (`module_enabled` в `business/configurations.py:452-463` возвращает baseline только для `booking_resources`). Публикация уже пишет строки всех optional-модулей (`configurations.py:425-433`).
- Триггер `BEFORE INSERT FOR EACH ROW` на каждой таблице модуля (tgtype = 7); таблица двух модулей — два триггера.
- Порядок в команде: авторизация (exclusive lock модуля) → `commands.claim` → `require_module` → запись внутри `module_writes(...)`. Повтор после отключения возвращает сохраненный результат.
- Нет deadlock: команда берет `gba:<module>:{b}` → membership FOR SHARE → shared config lock; публикация — exclusive config lock → membership FOR SHARE.

### 5.3 Schema guard (`api/src/gorgona_booking/db/schema_guard.py`)
- Таблицы: добавить имена в кортеж company-only (`_company_only(table, f"{table}_unrestricted_scope", "*")`, строки ~82-101). Счет: **29 → 34 (E1) → 38 (E2) → 40 (E3)**.
- Функция шлюза: константа `_MODULE_GATE_SOURCE` (тело функции, сравнение без пробелов как `_BOOKING_MODULE_SOURCE`), проверка `not prosecdef`, `proconfig is null`, язык plpgsql.
- Триггеры: список `_MODULE_TRIGGERS = [(table, trigger_name, module_id), ...]`; в `_ACCESS_BOUNDARY` CTE `required_triggers(table_name, trigger_name, module_id) as (values ...)` и `not exists (select 1 from required_triggers r left join pg_trigger t on t.tgrelid = to_regclass('gba.'||r.table_name) and t.tgname = r.trigger_name where t.oid is null or t.tgtype <> 7 or t.tgenabled <> 'O' or t.tgisinternal or t.tgfoid <> to_regprocedure('gba.require_enabled_module()') or t.tgnargs <> 1 or t.tgargs <> convert_to(r.module_id, 'UTF8') || '\x00'::bytea)`.
- **Порядок параметров** = порядок `%s` в SQL (сначала VALUES определений, затем новые VALUES триггеров если CTE стоит рядом, затем исходники функций). Добавить unit-тест: число плейсхолдеров = `len(parameters)`.
- Документы: новый счет определений в ADR, DEVELOPMENT, START_HERE.

### 5.4 Миграция: правила
- Имя `NNNN_name.sql`, непрерывная нумерация (`db/migrate.py`, `tests/unit/test_migration_files.py`).
- Каждая `create table X` — оба `alter table X enable/force row level security`; нет `security definer`, `bypassrls`, `disable row level security`.
- Файл заканчивается маркером `-- <Name> branch scope: ...` и **только** restrictive-политиками — `api/tests/integration/test_location_access.py:372-381` повторно выполняет всё после маркера: добавить `(15, "-- Counterparty branch scope:")`, затем 16, 17.
- Не менять исторические миграции.

### 5.5 Команды, квитанции, аудит
- Общие помощники `business/commands.py`: `fingerprint`, `claim(conn, scope, request_hash, Model)`, `complete`, `audit`. `IdempotencyScope(business_id, actor, operation, key)` из `booking/idempotency.py`.
- **Квитанции хранят только ссылки** (`CounterpartyReceipt{counterparty_id, revision}`, `BookingLinkReceipt{counterparty_id, link_ids}`; `MatchDecisionView` без ПДн можно хранить целиком); повтор перечитывает неизменяемые строки. Байты файлов и ПДн в `gba.idempotency_keys` не попадают (строки там не удаляются).
- Аудит в той же транзакции; details: только id, ревизии, состояния, роли, счетчики, даты, media type, размер, sha256. Тесты проверяют allowlist ключей details.
- Блокировки: `exclusive="counterparties"` (E1, E3), `exclusive="documents"` (E2).
- Ошибки-подклассы `ConflictError` получают 409 по MRO (`api/errors.py` `status_for`); новые коды задаются атрибутом `code`.

### 5.6 Готовность модулей (правило ADR-0019 «статус меняется только в коммите с доказательством»)
- В коммите кода: `business/modules.py` — модуль `planned → implemented` с текстами `limits`/`stops` (включить нельзя).
- Тестовая фикстура `verified_modules(monkeypatch, *ids)` в новом `api/tests/integration/module_support.py`: заменяет `MODULES_BY_ID[id]` на `model_copy(update={"readiness": TECHNICALLY_VERIFIED, "enableable": True})` → настоящий путь draft → validate → publish (`selection_problems` читает `MODULES_BY_ID` при вызове). Браузерный harness запускает uvicorn в потоке того же процесса (`tests/integration/live_server.py`) — фикстура действует и там.
- Отдельный тест: без подмены публикация модуля дает 422 `MODULE_NOT_READY` тогда и только тогда, когда реальный `enableable` ложен (работает и после перевода).
- Коммит приемки после зеленого CI: модуль → `technically_verified` (ссылка на evidence), `api/tests/unit/test_configuration_contracts.py:94` — `["counterparties", "booking_resources"]` после E1; `["counterparties", "booking_resources", "documents"]` после E2 (порядок `MODULES`). При необходимости запись в `business/readiness_registry.py`.
- **`MODULE_REGISTRY_VERSION` не повышать** (иначе все проверенные черновики получат `REGISTRY_CHANGED`, `configurations.py:179-186`).
- Публикация требует профиль (FK `profile_revision`): в тестах сначала `Config.profile(...)`, затем `Config.publish(...)`. Хелпер `Config` вынести из `api/tests/integration/test_configurations.py:57-131` в `tests/integration/configuration_support.py`.

---

## 6. E1 — контрагенты (миграция 0015, модуль `counterparties`)

### 6.1 Черновик миграции (`handoff/package-e-drafts/0015_counterparties.sql`)
- `gba.require_enabled_module()` (общая для всех optional-модулей).
- `counterparties` (tenant_id, id клиентский UUID, kind person|organization, created_by/at; PK (tenant_id, id)).
- `counterparty_versions`: revision; display_name 1..200; legal_name 1..300; tax_id/registration_number `^[A-Za-z0-9][A-Za-z0-9 ./-]{0,63}$`; email (`= lower(btrim(email))`, при вставке `lower(btrim(%s))` в SQL); phone `^[+]?[0-9 ().-]{7,32}$`; generated `phone_digits`, `name_key` (`lower(regexp_replace(btrim(display_name), '[[:space:]]+', ' ', 'g'))`); roles ⊂ {customer, supplier, contractor, partner}; state active|archived|merged; merged_into (FK `counterparty_versions_merged_into_fk`, check `(state='merged') = (merged_into is not null)`); created_transaction xid8; индексы по email/phone_digits/tax_id/registration_number/name_key/merged_into.
- `counterparty_version_contacts` (≤20 на версию; вставка только в транзакции версии — guard-триггер по `created_transaction`).
- `counterparty_match_decisions` (merged | distinct | separated; `reverses_decision_id` для separated; уникальная пара distinct; одна отмена на решение).
- `counterparty_booking_links` (id uuidv7, booking_id, sequence, action linked|unlinked, counterparty_id, basis ⊂ {email, phone}; FK `counterparty_booking_links_booking_fk` на `booking_customers(tenant_id, booking_id)`; триггер чередования и `sequence = last + 1`).
- Триггеры: неизменяемость (`reject_counterparty_mutation`), `enforce_counterparty_version` (revision = max+1), guard контактов, enforce связей, 5 шлюзов модуля. Маркер `-- Counterparty branch scope:` + 5 restrictive-политик.
- Проверить при переносе: синтаксис generated-колонок, `'\x00'`/tgargs в guard, гранты только колоночные insert, отсутствие update/delete грантов.

### 6.2 Черновики Python
- `counterparty_contracts.py`: `CounterpartyInput` (Versioned: expected_revision, kind, display_name, legal_name, tax_id, registration_number, email, phone, roles (уникальные, сортируются), archived, contacts ≤20), `ContactInput`, `CounterpartyView` (+ `merged_from`), `CounterpartySummary`, `CounterpartyList` (next_cursor = UUID), `CounterpartyHistory`, `CounterpartyReceipt`, `MatchCheckInput` (emails/phones — кортежи, чтобы проверять и контакты), `MatchCandidate`/`MatchList` (strong: email, phone, tax_id, registration_number; weak: name), `MergeInput`/`DistinctInput`/`SeparateInput` (дискриминатор `decision`), `MatchDecisionView`/`List`, `LinkBookingsInput` (≤50) / `UnlinkBookingInput` (`expected_sequence`) (дискриминатор `action`), `BookingLinkView`, `BookingLinkResult`, `BookingLinkReceipt`, `BookingLinkHistory`, `BookingSummary`, `LinkedBooking`/`List` (`still_matches`), `BookingCandidate`/`List`.
- `counterparty_matching.py`: нормализация только в SQL (обе стороны одинаково): CTE `latest`, `keys` (emails/phones карточки и контактов), `probe` из ввода или из записи; исключены merged и пары distinct; `booking_matches` возвращает (summary..., by_email, by_phone, latest sequence, latest action); без явных id связанные записи исключаются.
- `counterparties.py`: ошибки `CounterpartyStateError` (409 `COUNTERPARTY_STATE_INVALID`), `MergeNotAllowedError` (409), `BookingAlreadyLinkedError` (409), `BookingNotACandidateError` (409); `load_counterparty`, `list_counterparties` (keyset по (name_key, id), курсор — только UUID, поиск `q` ILIKE + цифры телефона ≥3), `counterparty_history`, `save_counterparty` (kind неизменен; merged нельзя править), `decide_match` (merge ничего не переносит, запрещены цепочки; separate восстанавливает состояние ревизии до слияния), `change_booking_links` (под блокировкой перепроверка кандидатов; аудит на каждую связь `counterparty.booking_linked|booking_unlinked`, target `booking`), `linked_bookings` (запись + дубликаты, слитые в нее), `booking_link_history`.
- Известные места для проверки при переносе: `_KEYS` использует `l.tenant_id` из `v.*`; mypy-типы `row` (tuple[Any, ...]); `MatchDecisionView.counterparty_revision` в списках = None; `linked_bookings` курсор = id связи.

### 6.3 Чего еще нет для E1 (написать)
1. `api/src/gorgona_booking/api/counterparties.py` (prefix `/v1/businesses`), регистрация в `api/app.py` (рядом с остальными `include_router`):
   - GET `/{b}/counterparties?q&state&after&limit≤100` (read)
   - GET `/{b}/counterparties/{cid}?revision`, GET `…/versions?before&limit` (read)
   - PUT `/{b}/counterparties/{cid}` (manage, `MutationKey`, `exclusive="counterparties"`)
   - POST `/{b}/counterparties/match-check` (read; не команда)
   - GET `…/{cid}/duplicates`, GET `…/{cid}/match-decisions` (read)
   - POST `…/{cid}/match-decisions` (manage; тело `MatchDecisionInput`)
   - GET `…/{cid}/booking-candidates`, GET `…/{cid}/bookings?after&limit`, GET `…/{cid}/booking-links?after&limit` (read)
   - POST `…/{cid}/booking-links` (manage; тело `BookingLinkInput`)
   - Путь `match-check` объявить до `/{cid}` или он не конфликтует (POST vs GET) — проверить.
2. `api/errors.py`: ничего, если ошибки — подклассы `ConflictError`/`InvalidReferenceError` (MRO); при необходимости `register_domain_error`.
3. `business/modules.py`: `counterparties` → `Readiness.IMPLEMENTED`, `limits` («контрагенты, контакты, подсказки дубликатов, решения, связи с записями; договоры — шаг E3; согласия, обращения, импорт — позже»), `stops` («новые карточки, версии, решения и связи; чтение, история и экспорт продолжаются»).
4. `db/schema_guard.py` (раздел 5.3) и тест повреждения: политики, отключенный триггер, замена функции, неверный `tgargs` → `/health/ready` 503 (образец `test_configurations.py:615-677`, восстановление через `load_migrations()`).
5. Тесты `api/tests/integration/test_counterparties.py` (список в плане и ADR-0020 Acceptance), `api/tests/unit/test_counterparty_contracts.py`, `module_support.py`, `configuration_support.py`, обновления существующих (раздел 5).
6. Web: `web/lib/counterparty-contracts.ts` (zod strictObject; списки — та же компания, уникальные id), маршруты в `managementResponseSchema` (`web/lib/management-contracts.ts`) и тесты «recognizes»/«fails closed» в `web/tests/management-contracts.spec.ts`; функции в `web/lib/management-api.ts`; `web/app/counterparties/page.tsx` (static export — выбор внутри страницы, без динамических сегментов); `web/components/counterparties.tsx`, `counterparty-matches.tsx` (повтор неопределенного результата тем же ключом, блок формы при 409, образец `legal-entities.tsx`); `NAV_ITEMS` в `web/components/management-layout.tsx` (скрыть для делегатов и филиальных); при выключенном модуле — только чтение и объяснение (читать `/configuration`).
7. Браузер: `web/tests/counterparties.spec.ts`, npm-скрипт `test:management:counterparties` в `web/package.json`, функция в `api/tests/integration/test_management_browser.py` (образец 502-598, SQL-проверки версий, связей, аудита без ПДн, неизменности `booking_customers`), мобильная ширина + axe. Переходы только по ссылкам (`page.goto`/`reload` теряет сессию). Перед браузерными тестами `npm run build`.
8. Документы шага: DEVELOPMENT.md (раздел «Counterparties (stage 1)» в формате legal entities: маршруты, правила, web, focused acceptance), ADR-0020 (SHA), реестр, аудит, START_HERE, evidence.

---

## 7. E2 и E3 — ключевые детали и ловушки

### E2 — документы (0016, модуль `documents`)
- Таблицы: `document_files` (неизменяемые: sha256, size_bytes 1..10 485 760 = `octet_length(content)`, media_type ∈ {application/pdf, image/png, image/jpeg}, file_name, validator_version, content bytea `set storage external`; **без** scan_status), `documents`, `document_versions` (title, category ∈ {agreement, certificate, invoice, report, other}, valid_from/until, archived, file_id?), `document_counterparty_links` (журнал; шлюзы обоих модулей). Guard 34 → 38, триггеров 5 → 10.
- Загрузка `PUT /v1/businesses/{b}/document-files/{file_id}` — **сырое тело** (python-multipart НЕ установлен, новых зависимостей не добавлять): в staging/production сразу 503; проверить заявленный Content-Type (415) и Content-Length (413); короткая авторизация + `require_module` ДО чтения тела; `request.stream()` с лимитом (413 и без Content-Length); не держать соединение пула во время чтения (пул max 10, `db/pool.py`); валидация в `business/file_validation.py` (сигнатуры `%PDF-`, PNG 8 байт, JPEG `FFD8FF`; PDF: нормализация `#xx`, FlateDecode через `zlib.decompressobj` с бюджетом, отказ `/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFile(s)`, `/RichMedia`, `/XFA`, `/SubmitForm`, `/ImportData`, `/GoToE` → 422 `FILE_ACTIVE_CONTENT`; `/Encrypt`/нечитаемое → 422 `FILE_UNREADABLE`; `/OpenAction` сам по себе разрешен); имя файла (NFC, basename, без управляющих/bidi/`<>:"/\|?*`, без CON/PRN/..., ≤120, расширение по типу) в заголовке `X-File-Name` (percent-encoded UTF-8); вставка через бинарный параметр psycopg (`%b`); отпечаток идемпотентности без байтов; аудит `document_file.uploaded {size_bytes, media_type, sha256}`.
- Скачивание `GET …/documents/{d}/versions/{rev}/file`: `binary=True`, повторная проверка sha256 (иначе 500 `FILE_INTEGRITY_FAILED`), `Content-Disposition: attachment` (ASCII + `filename*`), `nosniff`, `Cross-Origin-Resource-Policy: same-origin`, CSP `default-src 'none'; sandbox; frame-ancestors 'none'`; аудит `document_file.downloaded`. Работает и при выключенном модуле.
- **Ловушка:** `api/framing.py:38-39` для `/v1/` **заменяет** заголовок CSP на `frame-ancestors 'none'` — исправить на дополнение существующей политики (red→green тест рядом с тестами framing: `test_embed_origins.py` / `test_management_booking_invariants.py`).
- **Ловушка web:** `managementFetch` (`web/lib/management-api.ts:665-760`) всегда JSON + схема + таймаут 15 с. Выделить общий `authorizedResponse(path, init, timeoutMs)`; `managementUpload` (тип по проверенной сигнатуре, не `file.type`; таймаут 60 с); `managementDownload` (проверка типа, размера, sha256 через `crypto.subtle`; Blob + `<a download>`; без предпросмотра). Бинарный маршрут намеренно не в `managementResponseSchema`.
- Тесты: `test_file_validation.py` (матрица), `test_documents.py` (ровно 10 МБ / +1 байт с и без Content-Length, staging 503, квитанции без content, заголовки и CSP, подмена содержимого, оба шлюза, один file_id с разными байтами [200, 409], доступ, порча → 503), web unit `document-files.spec.ts` (добавить в `test:unit`), Playwright `documents.spec.ts` (`setInputFiles` буфером, `waitForEvent('download')` + sha256), harness, маркер 16.

### E3 — договоры (0017, модуль `counterparties`)
- В коде `agreements` (суффикс `*_contracts.py` = схемы API), в UI «Contracts».
- `agreements` (counterparty_id, legal_entity_id? — свое юрлицо), `agreement_versions` только вставки: state draft|agreed|terminated, title, number?, summary ≤2000, effective_from/until, для agreed/terminated `signed_on` + `attestation = 'signed_outside_platform'`, ссылка на версию документа (document_id + document_revision, оба или ни одного), terminated_on. Триггер: revision = max+1; переходы ∅→draft, draft→draft|agreed, agreed→draft (дополнение)|terminated; terminated финален и несет содержание последней agreed. Согласованная строка никогда не переписывается (§8 L365). Guard 38 → 40, триггеров 10 → 12.
- API: GET `/counterparties/{cid}/agreements`, `/agreements/{aid}?revision`, `/versions`; PUT `/agreements/{aid}`; POST `/agreements/{aid}/agree` (signed_on ≤ сегодня), POST `/agreements/{aid}/terminate`. Merged/archived контрагент → 409 `COUNTERPARTY_STATE_INVALID`; `AGREEMENT_STATE_INVALID` 409; `ATTESTATION_REQUIRED` 422. UI показывает «подписан» только после ответа сервера.
- Обновить `limits` модуля `counterparties`.

### Вне рамок E (записано в ADR-0020)
Согласия, обращения, шаблоны, провайдер э-подписи, пользовательские поля, ограничение доступа к отдельному документу, хранение/удаление ПДн (неизменяемые версии → будущая процедура редактирования; ПДн в старых квитанциях бронирования), импорт по source+external id, Azure Blob и антивирус, квота хранения, офлайн-кэш документов, экспорт кроме постраничного JSON, доступ front_desk/artist, роль carrier.

---

## 8. Локальная среда и команды

- Python 3.14: `api/.venv/Scripts/python.exe`; Node 24, `web/node_modules` установлены. Docker нет (container gates только в CI).
- Тестовый кластер этой сессии: `%LOCALAPPDATA%\GorgonaBookingTests\claude-cluster` (data, postgres.log, приватный `test-connection.json` — **пароль никогда не выводить и не копировать в repo/архив**). Бинарники: `%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\pgsql\bin`. Сейчас **остановлен**.
- Запуск (PowerShell):
  ```powershell
  $base = Join-Path $env:LOCALAPPDATA 'GorgonaBookingTests'; $bin = Join-Path $base 'postgres-18.6\pgsql\bin'; $data = Join-Path $base 'claude-cluster\data'; $log = Join-Path $base 'claude-cluster\postgres.log'
  Start-Process -FilePath (Join-Path $bin 'pg_ctl.exe') -ArgumentList @('-D', "`"$data`"", '-l', "`"$log`"", '-o', '"-h 127.0.0.1 -p 51455 -c max_connections=250"', 'start') -WindowStyle Hidden
  & (Join-Path $bin 'pg_isready.exe') -h 127.0.0.1 -p 51455
  ```
  Остановка: `pg_ctl -D <data> stop -m fast`; проверить `pg_ctl status`.
- Кластер `postgres-18.6\data` на 51454 — чужой/неизвестный владелец; не использовать.
- Тесты с БД: `api/.venv/Scripts/python.exe handoff/package-e-drafts/run_pytest.py -q -rs --tb=short` (из корня repo; переменная `RUN_BROWSER=1` добавляет `GBA_REQUIRE_BROWSER=1`). Полная suite ≈ 6.5 мин. Никогда две suites параллельно (общие имена ролей fixture).
- Статика: `cd api && .venv/Scripts/python.exe -m ruff format src tests && .venv/Scripts/python.exe -m ruff check src tests && .venv/Scripts/python.exe -m mypy`.
- Web: `cd web && npm run typecheck && npm run lint && npm run format:check && npm run test:unit && npm run build`. Prettier: `npx prettier --write <files>`. Отдельный spec: `npx playwright test tests/<file>.spec.ts --project=desktop`.
- Окончания строк: `.gitattributes` `* text=auto eol=lf`; при правке скриптами писать с `newline=''`.
- Тестовые хелперы: `tests/integration/seed.py` (`seed_salon` — делает компанию **live**; `seed_user`), `gorgona_booking.db.provisioning` (`add_membership`, `grant_platform_admin`, `owner_tenant_transaction`), `tests/support/fake_idp.FakeIdp` (`idp.bearer(subject, email=...)`), `tests/integration/test_delegations.Parties` (активный грант), `tests/integration/test_configurations.Config`.

---

## 9. Открытые вопросы (кроме пакета E)

- Исправляются в E0 (после коммита убрать из START_HERE §6): запросы `gba.memberships` без фильтра компании; web-схема readiness (`missing` vs `items`).
- Остаются: ограничения ADR-0017/0018 (аудит на каждый делегированный запрос, `/me` не видит приостановку компании-владельца, пагинация членств групп, нет блокировки приглашающих, дублирование помощников команд в старых модулях — перенос на `business/commands.py`); ADR-0019 (customer bootstrap не сообщает об отключении записи; стоимость проверки триггера в guard); опционально `Literal` в `api/setup.py` ReadinessView; release-условия аудита (нет branch protection, staging deploy не требует зеленого CI, CI не покрывает `ai/`).
- NOT TESTED: Azure/staging, промышленные миграции, реальные провайдеры (Stripe/OIDC/DAT/...), нагрузка/RPO/RTO, отраслевые пилоты, антивирус.

---

## 10. Текст поручения следующему агенту

> Продолжи самостоятельную GORGONA в `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`, ветка `codex/universal-business-foundation`. Прочитай `docs/plan/NEXT_AGENT_HANDOFF_PACKAGE_E_2026-10-04.md` (полностью), `docs/plan/PACKAGE_E_PLAN_2026-10-04.md`, `docs/adr/0020-counterparties-documents-and-contracts.md`, раздел 0 `docs/plan/NEXT_AGENT_START_HERE.md`, AGENTS.md. Не удаляй незакоммиченную работу. План и ADR-0020 уже утверждены владельцем. Заверши E0 (полная suite, коммит только файлов E0, push, CI точного SHA, приемка), затем закоммить ADR-0020 и план, затем реализуй E1 → E2 → E3 по плану, перенеся и проверив черновики из `handoff/package-e-drafts/`. После каждого шага обновляй handoff, реестр, аудит, DEVELOPMENT, ADR/evidence. Без merge, deploy и промышленных миграций. Отчет по-русски с точными PASS/FAIL/NOT TESTED.
