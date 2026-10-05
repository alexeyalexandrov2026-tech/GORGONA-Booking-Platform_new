# GORGONA — пакет E: контрагенты, документы, договоры (+ шаг E0)

> Source snapshot received 2026-10-04. Original preserved in the owner's handoff777 archive. E0 now has independent fresh evidence in [the current handoff](NEXT_AGENT_AUDITED_E0_2026-10-04.md). E1–E3 remain planned; no such migrations are applied. Statements below about prior tests/approval are the supplied record, not a new execution.


## Контекст

Ветка `codex/universal-business-foundation`, HEAD `2f16380`, полный GitHub CI PASS (push 37245076876, PR 37245079640), рабочее дерево чистое. Пакеты юрлиц, CORE-03 A–C и D (CORE-02, ADR-0019) приняты. По мастер-плану §13 этап 1 включает «контрагенты, документы»; START_HERE требует до кода план и ADR-0020, согласованные с владельцем. Сейчас в коде нет ни модели контрагента/договора/документа, ни хранилища файлов; модули `counterparties` и `documents` в `business/modules.py:97,114` — `planned`. Клиенты в записях — вычисляемый список по строкам `gba.booking_customers` без дедупликации.

**Решения владельца (2026-10-04):** файлы в PostgreSQL до 10 МБ без антивируса (статус «не проверен», в staging/production загрузка 503); клиентов из записей связывать только ручным подтверждением; доступ — только owner/manager всей компании; найденные дефекты изоляции исправить первым шагом E0.

**Одобрение этого плана = согласование ADR-0020 и разрешение на реализацию по шагам** с коммитом и push в рабочую ветку после каждого шага. Без merge, deploy, промышленных миграций. Один исполнитель, тестовый кластер `claude-cluster` 127.0.0.1:51455 (кластер 51454 не трогать — владелец неизвестен).

## Порядок работы

E0 → ADR-0020 (только docs) → E1 (миграция 0015) → E2 (0016) → E3 (0017).

Каждый шаг: код + тест red→green → web typecheck/lint/format/unit/build → Ruff/format/mypy → полная suite PostgreSQL 18.6 + браузеры (`GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1`, DSN только в окружении дочернего процесса) → независимый review чувствительных изменений → коммит → push → CI точного SHA (публичный API Actions) → коммит приемки: `docs/plan/evidence/<дата>-<шаг>/ACCEPTANCE.md`, обновление NEXT_AGENT_START_HERE, handoff, GORGONA_IMPLEMENTATION_STATUS, аудита, DEVELOPMENT.md, статуса ADR. Красный CI → причина, тест red→green, новый SHA.

## Шаг E0 — дефекты изоляции (без миграции)

Причина: permissive-политики `tenants_member_read`/`tenants_platform_admin_read` и `memberships_self_read` (0004_identity.sql:98, 322-331) складываются с tenant-политикой, поэтому запрос без фильтра видит строки других компаний вызывающего.

- `api/setup.py:79` `_booking_state` → `where id = %s` (передать salon_id; 3 вызова: `_after_edit`, `put_fact`, `_readiness_view`). **Эксплуатируемо.**
- `onboarding/readiness.py:105` подсчет владельцев → `tenant_id = gba.current_tenant_id()`. **Эксплуатируемо** (go-live компании без владельца).
- Фильтр компании добавить также: `identity/invitations.py:112-113, 307, 323-324, 331, 336`; `onboarding/service.py:277, 294, 307`; `tenancy/resolver.py:33`, `customer/queries.py:46-47`, `onboarding/fake_seed.py:137`, `db/provisioning.py:116` (сейчас не эксплуатируемы — защита на будущее).
- Web: `web/lib/management-contracts.ts:177-182` — схема readiness по фактическому API `{salon_id, ready, booking_state, items[{fact, status, detail}]}`, добавить `GET /readiness`; типы `savePolicies/saveBusinessHours/saveFact` (`management-api.ts:1076-1117`).

Тесты:
- red→green: новый `api/tests/integration/test_cross_company_reads.py` (readiness двух компаний одного менеджера и поддержки платформы; правка часов в не-live компании → `unconfirmed`; `unconfirmed` факт не дает `SALON_IS_LIVE`; факт owner не засчитывает членства в другой компании; регрессии suspend/duplicate invite); `test_onboarding.py::test_go_live_ignores_owner_memberships_elsewhere` (сейчас 200, должно быть 409 `NOT_READY`).
- Статический guard `api/tests/unit/test_cross_tenant_queries.py` (ast по `src/**`): SQL к `gba.tenants/memberships/tenant_hosts` обязан содержать фильтр компании; явный allowlist намеренных межкомпанейских чтений (`/v1/me`, поиск host, сервисный поиск делегирования).
- `web/tests/management-contracts.spec.ts`: настоящий `ReadinessView` проходит для PUT `/policies`, `/business-hours`, `/facts/x` и GET `/readiness` (сейчас падает).

## ADR-0020 (`docs/adr/0020-counterparties-documents-and-contracts.md`)

Коммит только документации до E1, в формате ADR-0019 (Context / Decision / Acceptance / Consequences); содержание — решения ниже, решения владельца и вне-рамок. Также ссылка в START_HERE.

## Общие механизмы (вводятся в E1)

- **Права:** `counterparties.read/manage`, `documents.read/manage` только в `_MANAGER` (owner наследует), `PERMISSIONS_VERSION` 3→4 (`auth/permissions.py`). Не в `DELEGABLE_PERMISSIONS`, не в `PLATFORM_SUPPORT_PERMISSIONS`. Маршруты без `allow_location_scope`/`allow_delegation` → филиальные, делегаты, поддержка платформы получают 403 существующими путями `tenancy/authorization.py`. Договоры используют `counterparties.*`.
- **Шлюз модуля в БД:** одна функция `gba.require_enabled_module()` (аргумент — id модуля), `BEFORE INSERT FOR EACH ROW` на **каждой** таблице модуля (включая версии и связи). Shared advisory lock `gba:business-configuration:{tenant}` как у бронирования; **семантика обратная бронированию**: нет строки в `business_module_states` или `enabled=false` → SQLSTATE `GBM01`. Публикация уже пишет строки всех optional-модулей (`configurations.py:425-433`) — без изменений. Новый `business/module_gate.py`: маппинг GBM01 → `ModuleDisabledError` (409 `MODULE_DISABLED`) и ранняя проверка `require_module` поверх `module_enabled` (`configurations.py:452-463`). Порядок команды: авторизация → claim ключа → `require_module` → запись; повтор после отключения возвращает сохраненный результат. Чтение, история, скачивание при отключенном модуле работают. Таблица связи двух модулей получает два триггера.
- **Schema guard (`db/schema_guard.py`):** каждая новая таблица — restrictive `<table>_unrestricted_scope` через `_company_only(..., "*")`; эталонный исходник `_MODULE_GATE_SOURCE`, список `(таблица, триггер, модуль)` с проверкой `tgtype=7`, `tgenabled='O'`, функции, `tgnargs=1`, `tgargs`; unit-тест числа плейсхолдеров = числа параметров. Счет: **29 → 34 (E1) → 38 (E2) → 40 (E3)** определений; триггеров модулей 5 → 10 → 12 плюс триггер бронирования.
- **Данные только вставками:** identity неизменяемы (клиентский UUID), версии append-only, связи — журналы событий с `sequence`. «Текущее» — последняя ревизия. Миграция заканчивается маркером и только restrictive-политиками (для `test_location_access.py:372-381`).
- **Квитанции идемпотентности хранят ссылки** (`{target_id, revision|sequence|file_id}`) через `business/commands.py` (`fingerprint/claim/complete/audit`), ответ при повторе перечитывается из неизменяемых версий → в `gba.idempotency_keys` нет ПДн и байтов файлов.
- **Аудит** в той же транзакции; в details только id, ревизии, состояния, роли, счетчики, даты, media type, размер, sha256 — без имен, email, телефонов, названий, имен файлов. Тесты проверяют allowlist ключей.
- **Блокировки:** `exclusive="counterparties"` (E1, E3), `exclusive="documents"` (E2).
- **Готовность модуля (правило ADR-0019):** в коммите кода модуль `planned → implemented` (с текстами `limits/stops`), включить нельзя. Тестовая фикстура `verified_modules(...)` (`tests/integration/module_support.py`) подменяет запись в `MODULES_BY_ID` → проходит **настоящий** путь draft→validate→publish; отдельный тест доказывает реальный отказ 422 `MODULE_NOT_READY` без подмены. После зеленого CI коммит приемки переводит модуль в `technically_verified` со ссылкой на evidence и обновляет `test_configuration_contracts.py:94`. `MODULE_REGISTRY_VERSION` не повышать (иначе все проверенные черновики получат `REGISTRY_CHANGED`).
- Вынести `Config` из `test_configurations.py:57-131` в `tests/integration/configuration_support.py`; обобщить текстовый тест делегируемых маршрутов `test_delegation_contracts.py:117-138` на все `api/*.py`.

## Шаг E1 — контрагенты, контакты, сопоставление (миграция `0015_counterparties.sql`, модуль `counterparties`)

Таблицы:
- `counterparties` — identity: `kind` person|organization (неизменен).
- `counterparty_versions` — `display_name`, `legal_name?`, `tax_id?`, `registration_number?` (формат без контрольных цифр, ничего не выдумывать), `email?` (lower/trim), `phone?` + генерируемые `phone_digits`, `name_key`; `roles` ⊂ {customer, supplier, contractor, partner}; `state` active|archived|merged + `merged_into`; частичные индексы для сопоставления.
- `counterparty_version_contacts` — контакты как дочерние строки версии (≤20; вставка только в транзакции версии): имя, должность, email, телефон. Одна карточка = одна ревизия = один expected_revision.
- `counterparty_match_decisions` — журнал: merged | distinct | separated (отмена слияния ссылкой на решение); уникальность пары distinct.
- `counterparty_booking_links` — журнал linked/unlinked по `booking_id` с `basis` ⊂ {email, phone}; FK на `booking_customers(tenant_id, booking_id)`; **`booking_customers` не меняется**.
- Триггеры неизменяемости, последовательности связей, 5 шлюзов модуля; маркер `-- Counterparty branch scope:`.

API `api/counterparties.py` (`/v1/businesses/{id}`; команды с `Idempotency-Key`):
- GET `/counterparties?q&state&after&limit` (keyset), GET `/counterparties/{cid}?revision`, `/versions`;
- PUT `/counterparties/{cid}` (`schema_version`, `expected_revision`, поля, `archived`, `contacts[]`);
- POST `/counterparties/match-check` (проверка до создания; ПДн в теле, не в URL);
- GET `/counterparties/{cid}/duplicates` — причины email/phone/tax_id/registration_number (сильные), name (слабая); **без автослияния**;
- POST `/counterparties/{cid}/match-decisions` — merge | distinct | separate; слияние только помечает дубликат `merged` и ничего не переносит (контакты, связи, документы, договоры остаются; карточка выжившего их агрегирует) → отмена дешева; цепочки слияний 409 `MERGE_NOT_ALLOWED`;
- GET `/counterparties/{cid}/booking-candidates` (нормализованные email/телефон контрагента и контактов; записи HOLD без контактов не участвуют), GET `/counterparties/{cid}/bookings`, POST `/counterparties/{cid}/booking-links` (link ≤50 подтвержденных вручную / unlink с `expected_sequence`; сервер под блокировкой перепроверяет, что запись все еще кандидат → иначе 409 `BOOKING_NOT_A_CANDIDATE`).

Файлы: `business/counterparty_contracts.py`, `business/counterparties.py`, `business/counterparty_matching.py`, `business/module_gate.py`, регистрация в `api/app.py`; ошибки в `api/errors.py` (`COUNTERPARTY_STATE_INVALID`, `MERGE_NOT_ALLOWED`, `BOOKING_ALREADY_LINKED`, `BOOKING_NOT_A_CANDIDATE`); аудит `counterparty.saved|merged|separated|marked_distinct|booking_linked|booking_unlinked`.

Web: `web/lib/counterparty-contracts.ts`, маршруты в `managementResponseSchema`, функции в `management-api.ts`, страница `web/app/counterparties/page.tsx` (выбор внутри страницы — static export), `web/components/counterparties.tsx` и `counterparty-matches.tsx` (повтор неопределенного результата тем же ключом, блок формы при 409), пункт навигации только для owner/manager всей компании без делегирования; при выключенном модуле — только чтение и объяснение.

Тесты: `api/tests/integration/test_counterparties.py` — жизненный цикл, повтор, чужой body с тем же ключом 422, история/пагинация; CORE-02 `[200, 409]` для создания, правки, встречных слияний, связи одной записи; шлюз (не опубликован → 409, чтение 200; отключение публикацией; гонка с публикацией; прямой SQL → GBM01); нормализация и слабость совпадения по имени; `booking_customers` побайтно неизменна; доступ (artist, front_desk, филиал, делегат, поддержка, чужая компания — отказ; отзыв блокирует следующую команду); откат без строк/аудита/квитанции; прямой SQL не меняет историю; порча политик/триггера/функции/`tgargs` → `/health/ready` 503; сценарии: малый бизнес (одна запись — клиент и поставщик), сеть/группа (участники не видят записи друг друга), гибрид (несколько профилей — один список). Unit: контракты, нормализация, права. Браузер: `web/tests/counterparties.spec.ts`, npm `test:management:counterparties`, функция harness в `test_management_browser.py` с SQL-проверками, мобильная ширина и axe. Обновить: `test_location_access.py` (маркер 15), `test_permissions.py`, `test_delegation_contracts.py`, `management-contracts.spec.ts`.

## Шаг E2 — документы и файлы (миграция `0016_documents.sql`, модуль `documents`)

Таблицы:
- `document_files` — неизменяемы: `sha256`, `size_bytes` 1..10 485 760 (= `octet_length(content)`), `media_type` ∈ {application/pdf, image/png, image/jpeg}, безопасное `file_name`, `validator_version`, `content bytea` (`storage external`). Статуса сканирования в таблице нет — API отдает `not_scanned`; будущий сканер добавит отдельную таблицу результатов.
- `documents` (identity) + `document_versions` — `title`, `category` ∈ {agreement, certificate, invoice, report, other}, `valid_from?/valid_until?` («истек» вычисляется), `archived`, `file_id?`.
- `document_counterparty_links` — журнал связей (шлюзы обоих модулей).
- Маркер `-- Document branch scope:`.

API `api/documents.py`:
- GET `/documents`, `/documents/{did}?revision`, `/versions` (`file_uploads: enabled | scanner_not_configured`); PUT `/documents/{did}`; POST `/documents/{did}/counterparty-links`; GET `/counterparties/{cid}/documents`.
- **PUT `/document-files/{file_id}` — сырое тело** (без multipart и новых зависимостей): в staging/production сразу 503 `FILE_SCANNING_NOT_CONFIGURED`; проверка заявленного Content-Type (415) и Content-Length (413) → короткая авторизация + `require_module` до чтения тела → потоковое чтение с лимитом (413 и без Content-Length) → проверка в `business/file_validation.py`: сигнатура = заявленный тип (415 `FILE_TYPE_MISMATCH`); PDF — нормализация `#xx`, распаковка FlateDecode с бюджетом, отказ при `/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFile(s)`, `/RichMedia`, `/XFA`, `/SubmitForm`, `/ImportData`, `/GoToE` (422 `FILE_ACTIVE_CONTENT`), `/Encrypt` или нечитаемые потоки (422 `FILE_UNREADABLE`); `/OpenAction` сам по себе не отказ; имя файла: NFC, basename, без управляющих/bidi/`<>:"/\|?*`, без зарезервированных имен, ≤120, расширение по типу; sha256 → транзакция: claim (отпечаток без байтов), вставка через бинарный параметр psycopg, аудит `document_file.uploaded`, квитанция `{file_id}`.
- GET `/documents/{did}/versions/{rev}/file` — повторная проверка sha256 (иначе 500 `FILE_INTEGRITY_FAILED`), `Content-Disposition: attachment` (ASCII + `filename*`), `nosniff`, `Cross-Origin-Resource-Policy: same-origin`, CSP `default-src 'none'; sandbox; frame-ancestors 'none'`; аудит `document_file.downloaded`.
- **`api/framing.py:38-39` сейчас перезаписывает CSP** для `/v1/` — изменить на дополнение `frame-ancestors 'none'` к существующей политике, тест рядом с тестами framing.

Web: из `managementFetch` (`management-api.ts:665-760`) выделить общий `authorizedResponse` (allowlist, токен, таймаут, конверт ошибок); `managementUpload` (тип по проверенной сигнатуре, `X-File-Name`, `Idempotency-Key`, таймаут 60 с) и `managementDownload` (проверка типа, размера и sha256 через `crypto.subtle`, Blob + `download`, без предпросмотра). Бинарный маршрут намеренно не в `managementResponseSchema` (JSON-запрос к нему отказывает). `web/lib/document-contracts.ts`, `web/app/documents/page.tsx`, `web/components/documents.tsx` (и в карточке контрагента), пункт навигации.

Тесты: `api/tests/unit/test_file_validation.py` (матрица: hex-имена, JS в сжатом object stream, бомба сжатия, `/Encrypt`, PNG под видом PDF, имена `../`, U+202E, `CON`, длина); `api/tests/integration/test_documents.py` (ровно 10 МБ принято, +1 байт — отказ с Content-Length и без; staging 503; квитанции без содержимого; заголовки скачивания и объединенный CSP; подмена содержимого → ошибка целостности; шлюзы обоих модулей; одинаковый `file_id` с разными байтами `[200, 409]`; доступ и порча → 503 как в E1); `web/tests/document-files.spec.ts` (unit), `web/tests/documents.spec.ts` (setInputFiles, download + sha256) с harness; маркер 16.

## Шаг E3 — договоры (миграция `0017_agreements.sql`, модуль `counterparties`)

В коде имя `agreements` (суффикс `*_contracts.py` уже означает схемы API), в UI — «Договоры». Записать в ADR-0020.
- `agreements` — identity: `counterparty_id`, `legal_entity_id?` (свое юрлицо).
- `agreement_versions` — только вставки: `state` draft|agreed|terminated, `title`, `number?`, `summary?` ≤2000, `effective_from?/until?`, для agreed/terminated — `signed_on` и `attestation = 'signed_outside_platform'` (электронной подписи нет), необязательная ссылка на версию документа (`document_id`+`document_revision`), `terminated_on`. Триггер: `revision = max+1`, переходы ∅→draft, draft→draft|agreed, agreed→draft (дополнение) | terminated; terminated финален и несет содержание последней agreed без изменений. **Согласованная версия никогда не переписывается** (§8 L365); «истек» вычисляется.
- 2 шлюза `counterparties`, маркер `-- Agreement branch scope:`.
- API: GET `/counterparties/{cid}/agreements`, `/agreements/{aid}?revision`, `/versions`; PUT `/agreements/{aid}`; POST `/agreements/{aid}/agree` (`signed_on` ≤ сегодня, attestation, документ?), POST `/agreements/{aid}/terminate`. Контрагент merged/archived → 409 `COUNTERPARTY_STATE_INVALID`; `AGREEMENT_STATE_INVALID` 409, `ATTESTATION_REQUIRED` 422. UI не показывает «подписан» до ответа сервера (§12.8).
- Аудит `agreement.drafted|agreed|terminated`. Тесты `test_agreements.py` (включая побайтную неизменность согласованной строки после дополнения, гонки, подделку SQL, шлюзы, доступ, порчу), `web/lib/agreement-contracts.ts`, `web/components/agreements.tsx`, `web/tests/agreements.spec.ts` + harness, маркер 17. Обновить `limits` модуля `counterparties`.

## Вне рамок пакета E (записать в ADR-0020 и `limits` модулей)

Согласия, обращения, шаблоны, провайдер электронной подписи, пользовательские поля, ограничение доступа к отдельному документу, хранение/удаление ПДн (неизменяемые версии требуют будущей процедуры редактирования; ПДн в старых квитанциях бронирования), импорт по source+external id, Azure Blob и антивирус (требуются до staging/production загрузки файлов), квота хранения, офлайн-кэш документов, экспорт кроме постраничного JSON, доступ ресепшена/мастеров. Память: до двух копий 10 МБ на загрузку/скачивание — ограничение записать.

## Проверка (end-to-end)

1. По каждому шагу: focused (`test_cross_company_reads.py`, `test_counterparties.py`, `test_documents.py`, `test_agreements.py`, `test_file_validation.py`, браузерные функции harness), затем полная suite на 127.0.0.1:51455 и web-проверки; ожидаемые 4 skipped (3 container gate без Docker, внешний site gate).
2. Красный тест виден до исправления (E0, framing CSP, шлюз модулей), зеленый после.
3. SQL после браузерных сценариев подтверждает версии, журналы связей, аудит без ПДн, неизменность `booking_customers`.
4. CI точного SHA каждого коммита — PASS через `api.github.com/.../actions/runs?branch=codex/universal-business-foundation`.
5. Отчет владельцу по-русски: PASS/FAIL/NOT TESTED; Azure/staging, антивирус, реальные провайдеры и пилоты — NOT TESTED.
