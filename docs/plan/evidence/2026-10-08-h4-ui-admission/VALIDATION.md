# H4/UI и admission — доказательства реализации

Дата владельца: 2026-10-08 (America/New_York). Активный repository:
`alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`.
Integration branch: `codex/package-h4-ui-admission`, parent
`codex/h3-forward-corrections`, base `12875e826b58c752bf6068352f398ec388ed7c0a`
([Draft PR21](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/21)).
Новый Draft PR, конечный code SHA и exact-head CI будут записаны в PR после push.
Historical evidence соседних H slices не считается проверкой этого checkout.

## Изменения

- `/finance/`: invoice/manual accrual, обязательства A/P/C/R, settlement,
  вручную подтверждённый внешний платёж, correction/void, credit/refund/void.
  Используются существующие H API и единый G ledger; новая денежная логика
  backend не добавлена. Суммы проверяются через BigInt без float.
- Серверный read-only `financial-documents/overview` сообщает текущий gate.
  Он не включает workflow. Production `finance_documents` остаётся planned
  и non-enableable; положительная H конфигурация существует только в fixtures.
- `/provider-admission/`: versioned draft/submitted/withdrawn metadata,
  declared country/activity/operation, opaque account/evidence references,
  manually-provided-unverified evidence, assessment только
  `not_checked/suspended/unsupported`. Все operational capabilities — false.
  Нет provider SDK, network requests, webhooks или операционного approval.
- Новая forward-only `0031_provider_admission.sql`: пять insert-only таблиц,
  FORCE RLS, tenant/book FK, finite transitions, deferred consistency,
  receipts/cancellations и отдельный readiness guard. Метаданные не создают
  financial source, obligation или journal. SQL требует утверждённую 0030.
- Same-key retry финансового запроса сохраняет тело только в памяти;
  sessionStorage содержит actor/business/key и конечный command reference.
  После reload требуется повторная авторизация: токены остаются в существующем
  in-memory storage. Resolve/cancel сверяют actor/business/book/subject/revision.
- Навигация доступна company owner/manager. Branch member, delegate, support
  и другая компания не получают company finance access.

0031 SHA256: `c82e37a2589867cf5058cf347cb89fc3b2a990c841d866d2d999f618e85469d2`.
0001–0030 не изменены; утверждённая 0030 SHA256:
`e68611d3ef292f84257b0ed4b9c323cb33284c8f8786838d3ffe928b08a6cf4e`.
Новые dependencies, lockfile changes, Azure/provider/production изменения отсутствуют.
Подробнее: [architecture/reuse](ARCHITECTURE_REUSE.md).

### Изменённые файлы (42)

```text
api/src/gorgona_booking/api/app.py
api/src/gorgona_booking/api/financial_documents.py
api/src/gorgona_booking/api/provider_admission.py
api/src/gorgona_booking/business/financial_contracts.py
api/src/gorgona_booking/business/provider_admission.py
api/src/gorgona_booking/business/provider_admission_contracts.py
api/src/gorgona_booking/db/migrations/0031_provider_admission.sql
api/src/gorgona_booking/db/provider_admission_guard.py
api/tests/integration/test_financial_overview.py
api/tests/integration/test_h3_upgrade.py
api/tests/integration/test_h4_browser.py
api/tests/integration/test_location_access.py
api/tests/integration/test_provider_admission.py
api/tests/integration/test_provider_admission_upgrade.py
api/tests/unit/test_provider_admission_contracts.py
docs/plan/GORGONA_IMPLEMENTATION_STATUS.md
docs/plan/GORGONA_MASTER_PLAN.md
docs/plan/NEXT_AGENT_H4_UI_ADMISSION_2026-10-08.md
docs/plan/evidence/2026-10-08-h4-ui-admission/ARCHITECTURE_REUSE.md
docs/plan/evidence/2026-10-08-h4-ui-admission/H_ACCEPTANCE_MATRIX.md
docs/plan/evidence/2026-10-08-h4-ui-admission/INDEPENDENT_REVIEW.md
docs/plan/evidence/2026-10-08-h4-ui-admission/VALIDATION.md
web/app/finance/finance.css
web/app/finance/page.tsx
web/app/globals.css
web/app/provider-admission/page.tsx
web/app/provider-admission/provider-admission.css
web/components/financial-editors.tsx
web/components/financial-workspace.tsx
web/components/management-layout.tsx
web/components/provider-admission.tsx
web/lib/admission-api.ts
web/lib/admission-contracts.ts
web/lib/financial-api.ts
web/lib/financial-contracts.ts
web/lib/financial-recovery.ts
web/lib/management-contracts.ts
web/package.json
web/tests/admission-contracts.spec.ts
web/tests/admission.spec.ts
web/tests/finance.spec.ts
web/tests/financial-contracts.spec.ts
```

## Окружение и команды

Windows; Python 3.14 и имеющийся test environment, Node/Next 16.3.7,
Chromium/Playwright. PostgreSQL 18.6 — отдельный disposable cluster на
loopback:51472, `max_connections=250`; единственный исполнитель PG suite.
Admin DSN собирается внутри private local helper, не записывается в Git/log/argv.
`PYTHONPATH` явно указывает `api/src;api` этого checkout, чтобы не импортировать
другой editable checkout.

```text
python -m pytest -q -p no:cacheprovider <focused files> --tb=short
python -m pytest -q -p no:cacheprovider --tb=short
python -m ruff format --check .
python -m ruff check .
python -m mypy                         # cwd = api
npm run typecheck
npm run lint
npm run format:check
npm run test:unit
npm run build
git diff --check
git diff --cached --check
```

Полный PG/browser run использует `GBA_REQUIRE_POSTGRES=1` и
`GBA_REQUIRE_BROWSER=1`. Disposable fixtures обязательны; это не миграция
или аудит production data. Docker отсутствует локально: container proof
остаётся отдельным обязательным exact-SHA CI gate.

## Наблюдаемые результаты

| Проверка | Результат | Доказательство/граница |
|---|---|---|
| Новый overview на parent source | FAIL: 4 tests, HTTP 404, 4.55s | Реальный red до endpoint; после реализации 4 PASS/4.23s |
| Direct SQL Unicode credential probe | FAIL: 4 tests/30 deselected, 3.30s | API отвергал Bearer + Unicode space, SQL принимал; SQL helper исправлен |
| Тот же Unicode probe после исправления | PASS: 4/30 deselected, 3.17s | NBSP/U+2000/U+202F/U+3000, Python/SQL parity |
| Focused PG run до full-order diagnosis | PASS: 59 tests, 45.19s | Admission, nonempty 0030→0031, overview, H3 upgrade и migration unit tests |
| Окончательная focused regression | PASS: 63 tests, 48.53s | Те же 59 + все четыре legacy location-boundary damage/restore cases перед admission |
| Дополнительная SQL целостность | PASS в focused run | Same-count evidence replacement, late receipt xid, xid default drift, lexical key boundaries |
| C1 control parity под PostgreSQL C locale | PASS: 32 codepoints | Read-only aggregate для U+0080–U+009F: `[[:cntrl:]]` совпадает с Python rejection; данные не менялись |
| Расширенный H4 browser harness | PASS: 1 pytest test, 50.62s | Шесть Playwright flows: closed finance desktop/mobile, enabled finance desktop/mobile, admission desktop/mobile |
| Первый Full Python/PG/browser | FAIL: 19 failed / 1212 passed / 4 skipped, 679.77s | Admission readiness отказал после прежних tests; narrower focused run этого не выявил. Root cause и green rerun — обязательны |
| Ordered non-browser diagnosis | FAIL: 1 failed / 568 passed / 12 deselected, 397.72s | Остановлен на первом admission failure; пять scope policies отсутствуют, остальные семь guard fragments true |
| Full Python/PG/browser после восстановления scope | PASS: 1231 passed / 4 skipped, 667.92s | Обязательные PG/browser, весь порядок legacy/new tests; три local container SKIP и один optional tenant-site SKIP |
| Финальный H4 browser после same-book UI regression | PASS: 1 pytest test, 51.06s | Все шесть Playwright flows на обновлённом export; same-book сохраняет row/details на desktop/mobile; final CI повторяет весь suite |
| Python format/lint/type | PASS | 230 files formatting; Ruff check; mypy 230 source files |
| Web type/lint/format | PASS | tsc, ESLint и Prettier на окончательном UI source |
| Web unit contracts | PASS: 94 tests, 1.3s | Повторены после последнего same-book UI изменения; включая 22 financial и 3 admission |
| Web production build | PASS: 20 routes | Статический Next export содержит finance/provider-admission |
| Независимый money/state review | PASS в пределах scope | [Read-only review](INDEPENDENT_REVIEW.md); no confirmed blocker, 5460 pure arithmetic transitions PASS; не заменяет runtime gates |
| Exact-head CI + containers | PENDING | Проверить после code commit/push; final SHA/run URLs записать в Draft PR |
| Documentation checks | PASS | `git diff --check`, `git diff --cached --check` exit0; UTF-8/no replacement characters и relative links valid; повторены после финальных docs mutations |

### Реальные browser assertions

Harness выполняет loopback OIDC/PKCE/JWT, реальный API и PostgreSQL. Fake IdP,
company/party/account/evidence помечены FAKE и ограничены disposable fixture;
provider integration не симулируется и не заявляется.

На каждом desktop/mobile book: invoice 100, reserve 100, payment 70, loss of
response/re-authenticated reload и same-key retry; payment correction 60→70;
release 30; credit 50 = C30/refund20, untouched credit void с historical mirror;
второй credit 50 и выплата refund20 через его собственное обязательство;
последующий void требует `FINANCIAL_RECONCILIATION_REQUIRED` и остаётся issued.
Выбор текущего credit counteraccount явно пустой до действия оператора.
Void UI подписывает C/refund как historical split и отменённый refund claim.
На каждом book итог ровно 3 financial documents, 2 external payments и
10 journals; retry и отклонённый void не добавляют деньги.

Admission: draft с потерянным ответом → reload/re-authentication/resolve →
submit → revision 1 history → withdraw. Capabilities false, recovery storage
не содержит account/evidence/notes. На всех шести flows: Axe violations = 0,
document horizontal overflow = false.

Первое локальное подключение было к ошибочно запущенному порту; tests не
начались. Ошибка исходной SQL CASE syntax и operation namespace выявлена setup,
затем устранена до публикации. Stalled selector/re-auth browser attempts и
неправильный PYTHONPATH/cwd не считаются PASS. Итоговые обязательные commands
выполнены на указанном integration checkout; failing evidence не скрывается.

### Причина первого full failure и regression

`test_location_access.py::test_scoped_work_fails_closed_when_schema_boundary_is_missing`
удаляет `gba.current_location_id()` через CASCADE. Его старый finally восстанавливал
branch policies только до миграции 0028, оставляя все пять новых admission scope
policies удалёнными. Admission guard правильно отвечал 503; остальные семь
fragments guard оставались true. Это подтверждено ordered run и read-only
catalog query в той же disposable DB. `/health/ready` старого scope guard
не проверяет admission policies, поэтому ранее не ловил проблему cleanup.

Исправление только тестовое: восстановление извлекает пять CREATE POLICY из
trusted packaged 0031; admission readiness проверяется до повреждения и после
восстановления каждого из четырёх cases. Production SQL/guard не ослаблялись.
Независимый reviewer проверил diff/пять различных restrictive policies; root
последовательная regression дала 63 PASS. Первый FAIL сохранён как evidence;
итоговый full rerun проверяет весь порядок ещё раз.

### Same-book UI regression

После полного PASS дополнительный browser assertion воспроизвёл потерю
отображаемого admission draft при повторном выборе той же книги: 1 pytest FAIL,
42.93s, missing draft row. Финансовые browser flows этого run прошли; failure
возник в admission desktop, mobile остановлен max-failures=1. Простой handler
return сохраняет текущий список/выбор, если book не менялся. Backend/SQL не
изменялись. Web type/lint/format, 94 contracts и production build повторены;
новый H4 harness проверяет этот assertion на desktop и mobile. Полный local
1231 PASS предшествовал только этому UI delta; final exact-head CI выполняет
весь suite на окончательном source.

## Матрица и границы

[H-01–H-12 mapping](H_ACCEPTANCE_MATRIX.md) связывает критерии с конкретными
tests и review. Это локальная/CI engineering evidence, не разрешение
FIN-03/FIN-02 promotion или production operation.

NOT TESTED: production data/conflicts, production migration, deployed browser,
реальные provider accounts/eligibility, provider network/payment/refund/webhook,
живые деньги, production load/soak. Локальные credentials/fixtures не являются
production credentials. Обычные проводки на архивных счетах по-прежнему
запрещены; F4 permission для точных historical mirrors из 0030 не расширялась.
Merge, production deployment/migration и CodeRabbit не запускались.
