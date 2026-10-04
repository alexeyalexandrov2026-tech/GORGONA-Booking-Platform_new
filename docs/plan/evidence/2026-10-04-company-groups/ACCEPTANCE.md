# Приемка — группы компаний с независимым согласием, 2026-10-04

## Результат и проверенная версия

Реализован ограниченный пакет этапа 1: группы оператора, версии названия,
приглашение самостоятельной компании, отдельное согласие ее владельца и сводное
чтение количества записей только через действующие полномочия.
CORE-03 и ENTERPRISE-01 остаются частичными; это не финансовая консолидация,
закрытие этапа 1, отраслевой пилот или промышленная приемка.

Checkout: C:\Users\alexa\.codex\worktrees\booking-state-isolation\Gorgona Booking.
Ветка codex/company-groups. База 161509f0e3a298cef9d2929576a023a6dd2e93c3
(PR #4, подразделения). На этой базе неизмененная реализация дала 512 passed,
4 skipped, 170.80 с. Проверки реализации ниже относятся к текущему diff; точный
опубликованный SHA и GitHub CI добавляются после публикации.
PR #4 при текущей проверке открыт, draft, не слит; базовая ветка PR #3.
Ни PR merge, ни production migration/deployment не выполнялись.

## Observable acceptance and actual flow

| Требование | Доказательство |
|---|---|
| Одна группа оператора, версии без переписывания | Создание/история, stale expected revision, replay, стабильный code, audit, rollback и чужой tenant проверены API/PostgreSQL |
| Только владелец без branch/delegation scope | group.manage только owner; платформенный и филиальный/делегированный доступ не заменяют владельца; FORCE RLS проверяется непосредственно |
| Независимый участник | Оператор приглашает; только владелец получателя принимает. Подделка согласия 403; duplicate active invitation 409; terminal withdrawal и старый receipt не восстанавливают согласие |
| Согласие не является доступом к данным | Принятый участник без report.booking.read/назначения дает пустые counts с исключенным источником |
| Явная текущая цепочка полномочий | Владелец участника → grant оператору → designation сотруднику; direct owner обеих компаний, wrong operator, expiry, suspended operator membership, missing designation и withdrawn consent не обходят проверку |
| Ограничение филиала | Отчет возвращает только назначенный филиал, называет его в source coverage. report.booking.read не открывает booking.read |
| Одновременный отзыв | Shared invitation lock отчета блокирует отзыв оператором/участником до завершения запроса; следующий запрос исключает данные. READ COMMITTED обязателен, старый snapshot отклоняется |
| Защита базы и guard | 4 FORCE RLS таблицы, 65 точных определений; removed/widened/extra policy дают 503 и readiness unavailable; восстановление возвращает готовность |
| Результат и владение | Ряд называет business/location/status/count; legal_entity_id null, assignment unassigned; у оператора нет скопированных bookings; клиентов, платежей, цен и выручки в отчете нет |
| Рабочий интерфейс | Реальный OIDC/PKCE test harness + API + PostgreSQL; desktop/mobile: lost response/retry, версия/история, UUID uppercase, приглашение, принятие, отчет, отзыв, Axe WCAG2 A/AA и отсутствие горизонтального overflow |
| Совместимость | Полная suite включает старые salons/customer booking, филиалы, делегирование, юридические лица, подразделения и миграции |

Одна транзакция проходит страницы не более 25 приглашений. Сначала авторизуется
оператор, затем под shared invitation lock заново читаются приглашение/согласие,
потом существующая трехэтапная авторизация ADR-0016 принудительно выбирает grant
именно этому оператору. Каждая компания читается последовательно на том же
соединении. После count query контекст оператора восстановлен. Доступ аудируется
у участника-владельца. Отчетные копии не сохраняются.

## Точные локальные проверки

| Проверка | Результат |
|---|---|
| База до изменения production source | PASS: 512 passed, 4 skipped, 170.80 с, exit 0 |
| Начальная red-регрессия двух отсутствующих workflows | FAIL: 2 failed, 1.93 с; 404 на новых group routes |
| После реализации: focused group/contracts/delegation/migration files | PASS: 76 passed, 8.96 с, exit 0 |
| Полный откат и защита истории | PASS в focused наборе: принудительный abort удаляет identity/version/audit/receipt целиком; SQL update/delete истории и consent отклонены, пропуск номера версии отклонен |
| Новые проверки группы | 20 PostgreSQL/API + 13 unit контрактов/прав + 1 real pytest browser scenario; browser содержит 2 desktop/mobile Playwright tests |
| Независимый review: UUID case red | FAIL: 1 pytest browser scenario, 19.31 с; оба viewport отклонили подтвержденный ответ из-за uppercase UUID |
| UUID case green после нормализации и свежей сборки | PASS: 1 pytest browser scenario, 12.49 с, exit 0 |
| Web typecheck / lint / format:check / build | PASS, каждый exit 0; 14 static pages |
| Web unit | PASS: 23 passed, 868 мс, exit 0 |
| Ruff format / check | PASS, exit 0; 147 Python files |
| strict mypy | PASS, exit 0; 147 source files |
| Полная итоговая API suite с обязательными PostgreSQL 18.6 и браузерами | **PASS: 546 passed, 4 skipped, 191.85 с, exit 0** |
| Локальные пропуски | 3 container checks: нет обязательного контейнерного окружения; 1 optional external-site gate. Пропуски не PASS |
| GitHub CI опубликованного SHA | NOT TESTED до публикации; свежий результат добавляется отдельным разделом |
| Документация и final diff | PASS: git diff --check, exit 0; 8 UTF-8 документов и 96 локальных ссылок; целевые шаблоны секретов отсутствуют в 34 измененных текстовых файлах. Повторяются после последней правки |

Команды: web — npm run typecheck, lint, format:check, test:unit, build.
API — uv run ruff format --check ., uv run ruff check ., uv run mypy;
локальный приватный runner запускает pytest -q -rs --tb=short с
GBA_REQUIRE_POSTGRES=1 и GBA_REQUIRE_BROWSER=1. DSN/пароль не печатались,
не переносились и не коммитились. Наборы PostgreSQL выполнялись последовательно.

## Инструменты и review

Использованы чтение исходников/документов, Git, официальный GitHub connector,
PostgreSQL 18.6, pytest/httpx, Ruff/mypy, Next/TypeScript/ESLint/Prettier,
Playwright desktop/mobile и Axe; новых зависимостей нет.
Применен skill Riqor evidence-engineering: наблюдаемая приемка, red→green,
свежие gates и независимый review. Reviewer читал код без мутаций и запуска suite.
Его конкретное P2 по uppercase UUID исправлено и проверено браузерной регрессией;
Reviewer повторно подтвердил исправление регистра UUID по текущим исходникам; дополнительных существенных находок в проверенном пакете нет. Сам review не является отдельным запуском тестов.
Решение изоляции и блокировок сверено с официальной документацией PostgreSQL18
([transaction isolation](https://www.postgresql.org/docs/18/transaction-iso.html),
[advisory locks](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS)).
[ADR-0018](../../../adr/0018-consented-company-groups.md) фиксирует решение.

## Границы и дальнейшая работа

NOT TESTED: production/staging/Azure, промышленное применение 0013, реальный IdP,
Stripe/DAT/Motive/Gusto, нагрузка 1000 компаний/100–200 RPS и p95, RPO/RTO,
отраслевые пилоты, финансовая консолидация и AI. Контейнерные проверки отдельно
подтверждаются точным CI; текущий локальный PASS их не заменяет.

Не реализованы: несколько филиалов в одной области доступа, SSO/SCIM,
межфирменные финансовые документы, assignment legal entity для bookings,
офлайн-синхронизация, configuration publication и единая occupancy CORE-04.
Полные beauty/TMS/restaurants/rental/construction/finance/WMS workflows
сохраняют статус planned. Согласие группы не дает общего доступа сотрудникам.
Оператора можно включить в будущий собственный отчет отдельным разрешенным
сценарием; текущий отчет содержит только приглашенных участников.

Сохраняются ранее зарегистрированные release gates: staging не требует зеленый
CI выбранного SHA, branch protection не подтверждена, ai/ не проходит текущий CI.
HawkScan DAST и Codeflash не проверены здесь (Docker/key/network ограничения
предыдущего аудита); этот пакет не меняет облако, права репозитория и интеграции.

## Измененные файлы

- CLOUD_CODE_HANDOFF.md
- api/src/gorgona_booking/api/app.py
- api/src/gorgona_booking/api/groups.py
- api/src/gorgona_booking/auth/permissions.py
- api/src/gorgona_booking/business/company_groups.py
- api/src/gorgona_booking/business/delegation_contracts.py
- api/src/gorgona_booking/business/group_contracts.py
- api/src/gorgona_booking/business/group_membership.py
- api/src/gorgona_booking/business/group_reports.py
- api/src/gorgona_booking/db/migrations/0013_company_groups.sql
- api/src/gorgona_booking/db/schema_guard.py
- api/src/gorgona_booking/tenancy/authorization.py
- api/tests/integration/test_company_groups.py
- api/tests/integration/test_delegation_browser.py
- api/tests/integration/test_location_access.py
- api/tests/unit/test_delegation_contracts.py
- api/tests/unit/test_group_contracts.py
- docs/DEVELOPMENT.md
- docs/adr/0018-consented-company-groups.md
- docs/plan/GORGONA_IMPLEMENTATION_STATUS.md
- docs/plan/GORGONA_MASTER_PLAN.md
- docs/plan/GORGONA_PLAN_AUDIT_2026-10-04.md
- docs/plan/NEXT_AGENT_HANDOFF_2026-10-04.md
- docs/plan/evidence/2026-10-04-company-groups/ACCEPTANCE.md
- web/app/business/page.tsx
- web/components/company-groups.tsx
- web/components/management-layout.tsx
- web/lib/delegation-contracts.ts
- web/lib/group-api.ts
- web/lib/group-contracts.ts
- web/lib/management-contracts.ts
- web/package.json
- web/tests/company-groups.spec.ts
- web/tests/group-contracts.spec.ts
