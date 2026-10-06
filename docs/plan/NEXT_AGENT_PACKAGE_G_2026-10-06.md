# Пакет G — актуальная передача, 2026-10-06

## Где продолжать

- Ветка: `codex/package-g-ledger-review`, база `151472a68d736ef21f68550ec36674eb36efc23c`.
- Checkout: `C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking`.
- Репозиторий: `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`.
- Draft [PR #12](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/12)
  в `claude/stage2-finance-plan`; проверенный код `95a0de4ac9f5aa3c96b054c5504f59115b0e4b69`.
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

Модуль и FIN-01 **technically_verified** отдельным коммитом приемки на evidence
`95a0de4`: полный local PASS, независимый обзор PASS в своих пределах, exact-SHA
CI PASS. Finance включается только новой публикацией конфигурации; старые
настройки сами не меняются. Положительный promotion override удален из API/browser
fixtures. Отрицательный тест временно снимает technical acceptance и доказывает
запрет публикации. Промышленная готовность/развертывание не заявляются.

## Проверки

Точные результаты — в приемке. `95a0de4`: полный local **858 passed / 4 skipped /
358.82 s**, CI **861 passed / 1 skipped / 223.29 s** с обязательными Docker gates.
После повышения реестра: focused **68 Python**, включая 4 desktop/mobile browser,
без положительного promotion override. Web unit 68; Ruff/format/mypy 197 файлов;
production web build PASS. Свежий CI приемочного HEAD проверять в PR #12 Checks.
Последний browser harness: оба viewport + Axe + OIDC/PKCE + реальная БД,
retry ответа PUT, reload recovery, safe cancel/delayed request, сторно и периоды PASS.
Всего независимые обзоры нашли 3 P1 + 4 P2, все закрыты. Финальный guard diff
проверен новым агентом статически/21 unit, без самостоятельного PG rerun;
runtime guard proof — отдельные full local/CI. Все отчеты сохранены рядом с приемкой.
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

Сверить exact-SHA CI последнего приемочного HEAD, затем план/ADR пакета H в пределах
этапа 2: счета и внешний платеж, подтвержденный человеком, без провайдера до
его допуска. Не переносить техническую приемку G на H или production.

Без merge/deploy/production migration/Azure/provider activation. Не подменять
checksum прежней 0020 в уже мигрировавшей БД; сначала выяснить фактическую историю.
KA Nails и камера Local Gateway вне этого репозитория.
