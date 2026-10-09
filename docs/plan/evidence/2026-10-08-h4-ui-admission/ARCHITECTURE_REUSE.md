# H4/UI — архитектура, повторное использование и критерии

Owner authorization: после рекомендации H4/UI и общей приёмки H владелец ответил
`ok`. Это разрешает локальную реализацию и отдельный Draft PR. Ранее заданные
границы merge, production, provider operations и FIN-03/FIN-02 сохраняются.

База: `12875e826b58c752bf6068352f398ec388ed7c0a`, Draft PR21 с F1–F5.
Ветка интеграции: `codex/package-h4-ui-admission`. Каждый исполнитель использует
свой checkout/branch; единственный PostgreSQL executor — основной агент.

## Проверенный flow и reuse

| Существующее основание | Использование в H4/UI |
|---|---|
| `api/financial_documents.py`, financial/settlement contracts | Те же invoice/accrual/credit/settlement/payment API; UI не создаёт второй monetary service |
| `business/ledger.py`, `gba.lock_ledger`, journal v2 | Единственный источник проводок и балансов; shared transaction/lock boundaries сохранены |
| `business/financial_commands.py`, insert-only domain references | Same-key retry и resolve/cancel; после reload хранятся только конечные reference metadata |
| `web/lib/management-api.ts`, OIDC/PKCE и ManagementLayout | Тот же API/auth transport, роль и активная company; нет отдельного сайта или session token store |
| `web/lib/ledger-contracts.ts` `minorUnits` | BigInt проверки P/C/R/A и сумм allocations без Number/float money |
| ledger accounts/books + counterparty API | Явный выбор книги, версии контрагента и счетов; текущий credit counteraccount не выбирается по historical default |
| Module registry и published configuration | Новый read-only financial overview сообщает фактический gate; чтение не включает модуль |
| Insert-only version/receipt/cancellation patterns | Реестр provider admission с forward 0031; отдельный finite metadata protocol без финансовых effects |
| `test_management_browser.py`, `live_server`, fake IdP | Реальные loopback OIDC/PKCE, Chromium, API и PostgreSQL для desktop/mobile; provider responses не подменяются |
| Packaged SQL readiness guards | 0031 проверяет baseline 0030; provider endpoints проверяют свои policies, grants, defaults, predicates/functions/triggers |

Новые dependencies/SDK, gateways, сетевые Stripe requests, cloud changes, второй
ledger и автоматическая recognition не нужны. Azure architecture не меняется.
KA Nails и внешний tenant website не входят в требования Booking.

## Наблюдаемые критерии

1. UI сохраняет/редактирует только drafts, выпускает точную ожидаемую версию,
   показывает separate invoice, obligation, manually attested payment и credit.
2. UI показывает principal A, effective P/C/R и available; BigInt response schema
   отвергает несогласованные суммы, чужую company/book/subject и неизвестную версию.
3. Settlement prepare/approve/reserve/sent/partial confirm/release/cancel,
   payment corrections/void и credit/refund/void используют существующий backend.
4. Неопределённый результат блокирует новые mutations; retry имеет тот же key
   и только body в памяти. Reload использует minimal reference, не восстанавливает
   суммы/PII/body. Resolve/cancel/history и non-money release доступны OFF.
5. Credit требует явного текущего counteraccount; другое значение требует reason
   и может иметь supporting journal reference. Refund требует явного control account.
6. Admission содержит declared country/activity/operation/account/evidence,
   draft/submitted/withdrawn history и только not_checked/suspended/unsupported.
   Эти сведения не являются подтверждением provider eligibility или ownership.
7. SQL/API/UI никогда не предоставляют положительный provider capability;
   recognizable credentials и неизвестные credential fields отвергаются.
8. Tenant/book/FK, branch/delegate/platform permissions, history immutability,
   idempotency/cancellation/expiry, concurrent versions и damaged controls
   проверяются на PostgreSQL. 0030→0031 не меняет ранее записанные domain rows.
9. Desktop/mobile сценарии выполняются через real OIDC/API/PostgreSQL с Axe,
   keyboard/labels и overflow проверками. Production registry проверяется closed
   отдельно; positive H override существует только в disposable fixtures.
10. Новая migration только 0031; 0001–0030/checksums сохранены. Focused checks,
    full local gates, independent review и successful exact-head CI предшествуют
    завершению отдельного Draft PR.

## Статус доказательств

Source/design inspection, focused/full PostgreSQL, browser, static и independent
review evidence записаны в [VALIDATION](VALIDATION.md). [H-01–H-12 mapping](H_ACCEPTANCE_MATRIX.md)
связывает критерии с конкретными tests. Exact-head CI после push — отдельный
delivery gate, его финальный SHA/run URLs/counts фиксируются в Draft PR.
FIN-03/FIN-02 остаются planned; production data/provider verification — NOT TESTED.
