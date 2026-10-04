# GORGONA — начните здесь (передача следующему агенту, 2026-10-04 вечер)

Этот документ — единая точка входа. Он короче истории в [handoff](NEXT_AGENT_HANDOFF_2026-10-04.md) и ссылается на все нужные документы.

## 1. Где проект

- Рабочая копия: `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`.
- Репозиторий: `https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`, ветка **`codex/universal-business-foundation`** (draft PR #1). `main` содержит только начальный README; merge не выполнялся.
- **Первое действие — проверить GitHub CI последнего точного SHA** (`git log -3`; вкладка Actions или публичный API `https://api.github.com/repos/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs?branch=codex/universal-business-foundation` — `gh` на машине нет, логи требуют авторизации, статусы шагов читаются без нее).

## 2. Что сделано и чем подтверждено

| Пакет | ADR | Миграция | Состояние |
|---|---|---|---|
| Юридические лица (черновики) | [0015](../adr/0015-tenant-owned-legal-entity-drafts.md) | 0010 | CI PASS `d97924f` |
| CORE-03 A — подразделения | [0016](../adr/0016-tenant-owned-departments.md) | 0011 | CI PASS `5b3c00b`, [приемка](evidence/2026-10-04-departments/ACCEPTANCE.md) |
| CORE-03 B — межкомпанейское делегирование | [0017](../adr/0017-cross-company-delegation.md) | 0012 | CI PASS `ed370c6`, [приемка](evidence/2026-10-04-delegation/ACCEPTANCE.md) |
| CORE-03 C — группы компаний | [0018](../adr/0018-company-groups.md) | 0013 | CI PASS `6a81dfd`, [приемка](evidence/2026-10-04-groups/ACCEPTANCE.md). CI на `c9193b2` был FAIL: гонка remove→accept (404 вместо 409), исправлена с red→green тестом |

Подробные результаты каждого шага: [реестр реализации](GORGONA_IMPLEMENTATION_STATUS.md). Состояние всех 28 критериев: [аудит](GORGONA_PLAN_AUDIT_2026-10-04.md). Технические маршруты и поведение API: [DEVELOPMENT](../DEVELOPMENT.md).

Пакет CORE-03 (A–C) собран для существующих модулей. Диспетчерские операции TMS, офлайн-черновики и сводные отчеты групп появятся со своими модулями и должны использовать гранты ADR-0017. Членство в группе доступа не дает.

## 3. Обязательные правила

Читать [AGENTS.md](../../AGENTS.md) и [мастер-план](GORGONA_MASTER_PLAN.md) до кода. Кратко:

- Самостоятельная универсальная GORGONA; KA Nails — отдельный проект вне работы и приемки. 39 отраслей и 28 критериев сохраняются.
- `business_id == tenant_id == salon_id`; никаких копий компаний; не выдумывать бизнес-факты; исторические миграции не менять.
- Типизированные версионированные контракты; idempotency + expected revision; FORCE RLS + schema guard (сейчас **25** определений); аудит; тест red→green; focused и полные проверки; CI точного SHA; evidence; без fake providers и успешных моков.
- **После каждого завершенного шага обновлять handoff, реестр, аудит, DEVELOPMENT и ADR/evidence** — с SHA, состоянием CI, числами тестов и следующим шагом (требование владельца).
- Без merge, deploy и промышленных миграций без явного разрешения владельца. Коммит/push в рабочую ветку — по поручению владельца.
- Один исполнитель на рабочую копию и на тестовый кластер PostgreSQL (имена ролей fixture общие).

## 4. Как проверять локально

1. Web: в `web/` — `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run test:unit` (34), `npm run build` (14 страниц).
2. API статика: в `api/` — `.venv/Scripts/python.exe -m ruff check src tests`, `-m ruff format --check src tests`, `-m mypy`.
3. PostgreSQL 18.6 и браузеры: полная suite с `GBA_TEST_ADMIN_DSN` (передается только дочернему процессу, никогда не выводится), `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1`: `.venv/Scripts/python.exe -m pytest -q -rs --tb=short`. Последний результат после исправления гонки: **495 passed, 4 skipped** (три container gate без Docker, внешний site gate).
4. Тестовые кластеры на этой машине:
   - `%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\data` на **127.0.0.1:51454** — прежний кластер. Он работал, запущенный другим процессом в 15:58; этой сессией не использовался и не останавливался. Выяснить владельца перед использованием.
   - `%LOCALAPPDATA%\GorgonaBookingTests\claude-cluster` на **127.0.0.1:51455** — отдельный одноразовый кластер этой сессии из официального EDB PostgreSQL 18.6. Приватный `test-connection.json` лежит в той же папке; пароль не выводить. Запуск: `pg_ctl -D <data> -l <log> -o "-h 127.0.0.1 -p 51455 -c max_connections=250" start` через detached `Start-Process -WindowStyle Hidden`; после работы `pg_ctl stop -m fast`.
   - Скачанный архив EDB (~330 МБ) лежит рядом; удалить можно по решению владельца.
5. Браузерные harness (Python → настоящий test-only OIDC → API → PostgreSQL): компания, филиал, делегирование, группы — `tests/integration/test_management_browser.py`. Перед ними нужен `npm run build`. Переход между страницами в spec только по ссылкам: `page.goto`/`reload` теряет сессию.

## 5. План дальше

Детальная карта — [handoff](NEXT_AGENT_HANDOFF_2026-10-04.md) и раздел 13 мастер-плана. Следующий пакет этапа 1:

**D. Конфигурация: черновик → проверка → публикация → замена (CORE-02 полностью, мастер-план §4).** До кода: свой план и ADR-0019. Содержание:
- версии конфигурации компании с проверкой, неизменяемой опубликованной версией и сохранением предыдущей;
- реестр модулей и их зависимостей; сервер проверяет разрешенные модули; отключение модуля останавливает новые операции, сохраняя историю;
- записи готовности профиля/сценария (§14.3) отдельно от каталога отраслей;
- expected revision, idempotency, аудит, предпросмотр, UI, браузерный сценарий.

Затем **E** — контрагенты, контакты, договоры, документы с версиями и проверкой файлов, сопоставление без автослияния. Потом **F** — единая занятость ресурсов по §12.2.1 (расширение → перенос `booking_allocations` → сверка → общий механизм → переключение чтения → откат; критерий CORE-04). После этапа 1 — этапы 2–9 по мастер-плану (FIN/WORK/STOCK → BEAUTY/TMS → BUILD/RENT/PROPERTY → REST/PRO → SUPPLY → MARKET/ENTERPRISE → специализированные отрасли → OPS/Azure ADR-0012).

## 6. Открытые вопросы и известные ограничения

- **Отдельная задача:** запросы к `gba.memberships` без фильтра компании видят собственные членства вызывающего в других компаниях (permissive policy `memberships_self_read`). Исправлен только `list_members`. Остаются `onboarding/readiness.py` (подсчет владельцев при go-live), `onboarding/service.py`, проверка последнего владельца в `identity/invitations.py`. Нужны тест red→green и явный фильтр.
- Записаны в ADR-0017/0018: аудит на каждый делегированный запрос (объем); `/me` не видит, приостановлена ли компания-владелец; пагинация членств групп; нет блокировки приглашающих; дублирование помощников idempotent-команд в модулях этапа 1; хрупкий текстовый тест списка делегируемых маршрутов.
- **Отдельная задача (не проверена):** web-схема `readiness` в `web/lib/management-contracts.ts` требует поле `missing`, а API `ReadinessView` (`api/setup.py`) возвращает `items`; ответы сохранения `/business-hours`, `/policies`, `/facts/{key}` в web, вероятно, не проходят проверку. Нужен тест red→green.
- Docker на машине нет: контейнерные gates проверяются только в CI.
- Azure/staging, промышленная миграция, реальные провайдеры, нагрузка/RPO/RTO и отраслевые пилоты не проверялись.

## 7. Текст поручения следующему агенту

> Продолжи самостоятельную GORGONA в `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`, ветка `codex/universal-business-foundation`. Сначала прочитай `docs/plan/NEXT_AGENT_START_HERE.md`, AGENTS.md, мастер-план, реестр и handoff; не удаляй чужую незакоммиченную работу. Проверь GitHub CI последнего коммита. Если он красный — исправь причину с тестом red→green. Шаг C принят (evidence `evidence/2026-10-04-groups`). Продолжи пакет D по ADR-0019 (когда он появится — по его плану и состоянию в реестре); новый пакет — свой план и ADR, согласованные с владельцем до кода. После каждого шага обновляй handoff, реестр, аудит, DEVELOPMENT и ADR/evidence. Без merge, deploy и промышленных миграций. Отчет по-русски с точными PASS/FAIL/NOT TESTED.
