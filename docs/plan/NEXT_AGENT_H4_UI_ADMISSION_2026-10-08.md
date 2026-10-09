# Продолжение H4/UI и admission

Активный repository: `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`.
Integration checkout:
`C:\Users\alexa\.codex\worktrees\package-h4-ui-admission\Gorgona Booking`.
Branch `codex/package-h4-ui-admission`; parent `codex/h3-forward-corrections`
на `12875e826b58c752bf6068352f398ec388ed7c0a` (Draft PR21).
Новый Draft PR должен иметь эту parent branch. Перед продолжением прочитать
actual HEAD/status/remotes/PR/checks: immutable evidence не заменяет refresh.

Начать с [architecture/reuse](evidence/2026-10-08-h4-ui-admission/ARCHITECTURE_REUSE.md),
[validation](evidence/2026-10-08-h4-ui-admission/VALIDATION.md) и
[H acceptance matrix](evidence/2026-10-08-h4-ui-admission/H_ACCEPTANCE_MATRIX.md).

## Реализованный flow

Company owner/manager видит Financial documents и Provider admission в том же
management workspace. Финансовый UI использует существующий H API; единственный
ledger — G. Новый overview честно сообщает disabled/not_ready; production H
registry остаётся planned/non-enableable. Положительные H browser/PG fixtures
не разрешают включать H в production registry.

Admission registry — только вручную заявленные метаданные. Draft/submitted/
withdrawn immutable revisions; assessment not_checked/suspended/unsupported;
all capabilities false; evidence unverified. Нет чтения provider credentials,
проверки eligibility, сетевой integration или реальных переводов.
Новая 0031 проверяет baseline 0030; 0001–0030 не редактировать. Следующая
опубликованная migration должна быть forward-only с новым номером.

Recovery references хранят только actor/business/book/subject/revision/key/
operation; bodies/money/PII остаются в памяти, OIDC tokens in-memory.
Reload означает повторную авторизацию и resolve/cancel. Unknown external sent
outcome по-прежнему требует фактической attestation, timeout/OFF не освобождает
деньги. Current credit counteraccount выбирается явно; historical default
не подставляется автоматически.

## Следующие gates

1. Проверить final Draft PR SHA и CI URLs/counts в PR description.
2. Перед любым deployment/migration — отдельное решение владельца, target
   inventory и read-only проверка фактических данных/конфликтов; локальные
   disposable upgrade tests не проверяли production.
3. FIN-03/FIN-02 остаются planned. Их acceptance/promotion не входит в этот PR.
4. Provider integration, test_access/approved capabilities, webhook authenticity,
   ordering/dedup и live payments требуют отдельного утверждённого этапа.

Нельзя merge, force-push/rebase/amend published history, deploy/production
migration, автоматически исправлять/объединять финансовые facts, работать
с реальными провайдерами/деньгами/credentials, повышать FIN-03/FIN-02 или
запускать CodeRabbit без прямого разрешения. Сохранить unrelated checkout work.
PG suite запускать последовательно; только disposable test environment.
