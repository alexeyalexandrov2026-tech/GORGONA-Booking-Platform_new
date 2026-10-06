# Пакет G — актуальная передача, 2026-10-06

## Где продолжать

- Ветка: `codex/package-g-ledger-review`, база `151472a68d736ef21f68550ec36674eb36efc23c`.
- Checkout: `C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking`.
- Репозиторий: `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`.
- Прежний `gorgona-e2-documents` сохранен; его незакоммиченный вариант G не подменять.

Прочитать [приемку и границы](evidence/2026-10-06-ledger/ACCEPTANCE.md),
[ADR-0023](../adr/0023-ledger-foundation.md),
[план этапа 2](STAGE2_PLAN_2026-10-06.md), AGENTS и мастер-план.
Сверить свежий Git status и exact-SHA CI; старый green CI плана не подтверждает G.

## Реализация

Финансовая основа FIN-01, миграция 0020; данные и настройки юридического лица,
нейтральный план счетов, точные суммы 0/2/3 minor units, двойная запись, сторно,
история закрытия/открытия месяцев и ведомость в выбранной валюте.
API и интерфейс `/ledger/` подключены к реальной БД. Карта прав v5,
owner/manager всей компании, без поддержки/делегирования/филиального доступа.
Новых зависимостей и изменений миграций 0001–0019 нет.

Главный исправленный дефект: ранний SET CONSTRAINTS больше не позволяет
дописать несбалансированную строку; проверяются и заголовок, и строки.
После сторно исходная проводка не получает новых строк. Все мутации требуют
READ COMMITTED, чтобы ожидание lock не сохраняло устаревший снимок периода.
Guard точно проверяет утвержденные определения из поставляемой 0020; порча
RLS/module/integrity controls ведет к 503. SQL-тесты наблюдают настоящее
ожидание lock при обоих порядках close/post.
После потери ответа минимальная ссылка в sessionStorage переживает reload/nav.
Resolve сверяет фактический результат, cancel сохраняет постоянный запрет
поздней исходной команды; обе операции доступны при отключении finance.
Токены/суммы/описания/тело в storage не записываются. Новая вкладка/браузер
вне этой гарантии; source_id хозяйственной операции решает дедупликацию намерения.

Модуль и FIN-01 пока **implemented**. Для окончательной технической приемки
нужны полный свежий прогон, независимый обзор, exact-SHA CI и коммит приемки.
В обычном реестре finance нельзя включить. Только clearly test-only fixtures
повышают его readiness для проверок реальных API/БД/browser flows.
Не переносить этот override в runtime и не объявлять промышленную готовность.

## Проверки

Точные результаты — в приемке. Focused: 57 Python (22 contracts, 34 SQL/API,
1 browser harness с 4 desktop/mobile сценариями), контролируемые SQL-гонки;
68 web-unit; Ruff/format/mypy 197 файлов; production web build.
Полный прогон окончательного дерева выполняется в этой сессии.
Последний browser harness: оба viewport + Axe + OIDC/PKCE + реальная БД,
retry ответа PUT, reload recovery, safe cancel/delayed request, сторно и периоды PASS.
Первичный независимый обзор: 2 P1 + 3 P2, все исправлены; повторный выполняется.
Первый полный прогон имел только устаревший configuration locator; он исправлен
и проверен в обоих viewport. Результат итоговой suite не брать из старого прогона.

Существующие lockfiles: `uv sync --frozen` в api и `npm ci` в web.
Тесты выполняются **последовательно**; fixture имена ролей общие в одном сервере.
У этой сессии отдельный disposable PostgreSQL 18.6: 127.0.0.1:51456,
`%LOCALAPPDATA%\GorgonaBookingTests\ledger-review-20261006`.
Секреты находятся только вне checkout; их нельзя выводить или включать в архив.
Игнорируемый helper `handoff/package-g-review/check.py` передает DSN только
дочернему процессу и принудительно требует PostgreSQL/browser.

Полная команда: `api/.venv/Scripts/python.exe handoff/package-g-review/check.py pytest -q -rs --tb=short`.
Перед browser checks нужен `npm run build`. Новые тесты:
`test_ledger_contracts.py`, `test_ledger.py`, `test_ledger_browser.py`,
`ledger-contracts.spec.ts`, `ledger.spec.ts`.

## Следующий шаг

Закончить оставшиеся gates G и зафиксировать доказанный статус; не повышать
readiness автоматически от наличия кода. Затем план/ADR пакета H в пределах
этапа 2: счета и внешний платеж, подтвержденный человеком, без провайдера до
его допуска. Не начинать H вместо незавершенной приемки G.

Без merge/deploy/production migration/Azure/provider activation. Не подменять
checksum прежней 0020 в уже мигрировавшей БД; сначала выяснить фактическую историю.
KA Nails и камера Local Gateway вне этого репозитория.
