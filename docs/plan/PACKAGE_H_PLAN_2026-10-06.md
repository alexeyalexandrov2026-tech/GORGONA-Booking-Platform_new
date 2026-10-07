# Пакет H — счета, обязательства и подтвержденные внешние расчеты

**Implementation checkpoint 2026-10-07:** H2 is implemented locally on
`codex/package-h2-settlements` through forward 0022–0024: manual accruals as
new obligations, settlement reserves and externally attested partial
confirmations; [current handoff](NEXT_AGENT_H2_2026-10-07.md) and
[direct evidence](evidence/2026-10-07-h2-settlements/VALIDATION.md). The branch
is in [draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16), target H1 PR15. Checkpoint75c36da
[CI37573680437](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37573680437) PASS:1044 passed/1 skipped/381.36s with all3 Docker/image.
Final docs are a successor; inspect current-head CI. Independent review still
NOT DONE; H3/H4 continue through new forward migrations.
ADR0024 remains formally Proposed; all twelve COMPLETE criteria below remain
NOT TESTED and FIN-03/02 planned.

**Earlier checkpoint (H1):** owner continuation authorized local H work and
draft publication. Source2d5a8f9 implements the bounded H1 invoice backend on
forward0021, with a closed feature gate; [H1 handoff](NEXT_AGENT_H1_BACKEND_2026-10-06.md)
and [direct evidence](evidence/2026-10-06-h1-backend/VALIDATION.md).
H2/H3/H4 continue through new forward migrations without changing published
checksums. ADR0024 remains formally Proposed; all twelve COMPLETE criteria
below remain NOT TESTED and FIN-03/02 planned. Older approval-pending text is
historical context, not a new action request.


Статус: **план на согласование, H не реализован**. Дата: 2026-10-06.
Объем этапа 2 согласован ранее; новые правила H ниже остаются предложением.
База: `5be6e7abd7b552903a4f4b2884b150c62532c17d`, технически принятый G.
Ветка: `codex/package-h-finance-plan`. Владелец реализации/приемки не назначен.

[ADR-0024](../adr/0024-invoices-obligations-and-external-settlements.md),
[архитектура и reuse evidence](evidence/2026-10-06-package-h-plan/ARCHITECTURE_REUSE.md),
[этап 2](STAGE2_PLAN_2026-10-06.md), мастер-план §7.5, §11.1–11.2.1,
§12.4 и FIN-03. Этот документ не означает принятия H или разрешения на production.

## Наблюдаемый результат

Владелец/менеджер всей компании выпускает внутренний счет на получение или
оплату, видит обязательство с тем же источником, готовит расчетный документ,
резервирует часть остатка и записывает фактически подтвержденный внешний платеж.
Два расчетных документа не могут использовать одну сумму дважды. Все денежные
эффекты поступают в существующий ledger G в той же транзакции.

Выставленный счет, подтвержденные деньги, признанный доход/расход и обязательство
показываются отдельно. Выручка не выводится из booking status или факта выдачи счета.
Последующее автоматическое recognition по invoice/fulfillment в H не создается.
Если бухгалтер сделал разрешенную manual G reclassification, credit требует
явного выбора текущего counter-account и подтверждения treatment; исторический
invoice counter-account показывается только как контекст, без default.
Для отличающегося счета нужен reason и ссылка на соответствующую G-entry того же
book/currency, если она существует. Ссылка не превращает произвольную G-entry
в машинно подтвержденное recognition конкретного invoice. H не обещает invoice-
level recognized revenue report без отдельной lineage-модели; фактический
общий результат остается в ledger/trial balance G.
Счета учета выбираются явно; выбор revenue/expense требует отдельного подтверждения
момента признания пользователем. Это внутренние финансовые документы, не обещание
налогового счета или соблюдения требований неизвестной юрисдикции.

## Предлагаемый объем H

| Часть | Результат | Критерий |
|---|---|---|
| H1 | Внутренние счета продажи/покупки с неизменяемыми версиями, строками, ссылкой на версию контрагента, книгой, валютой и отдельным обязательством | Основа FIN-03 |
| H2 | Ручные обязательства с устойчивым source/component, расчетные документы, согласование, резерв, частичные подтверждения внешних оплат, release неиспользованного резерва | FIN-03 reserve/payout |
| H3 | Кредитовые документы, корректировки подтверждений, отдельное встречное обязательство на возврат уже оплаченной части и его частичные внешние расчеты | FIN-03 history/storno |
| H4 | Реестр запросов допуска Stripe Connect, страна/деятельность/операция/account reference/evidence; все оперативные capabilities отключены | Только основа FIN-02; FIN-02 остается planned |
| Приемка | API/UI desktop/mobile, SQL-инварианты/гонки, полноценный G regression, независимый обзор, exact-SHA CI, отдельный acceptance commit | FIN-03 technically_verified только целиком |

Stripe charges/refunds/webhooks, зарплата, налоги, FX, нераспределенные авансы,
сводная отчетность и интеграция с booking checkout вне H. Выплата/поступление
здесь является записью подтвержденного человеком внешнего факта. Программа не
отправляет деньги и не возвращает поддельный ответ провайдера.

## Данные и источники

Новые названия таблиц/API ниже — **предлагаемые**, их еще нет в checkout.

- `financial_documents` + insert-only versions/lines: invoice или credit note,
  направление receivable/payable, книга/юрлицо, версия контрагента, валюта,
  даты, номер внутреннего документа, creator и expected revision.
- `financial_obligations`: неизменяемый principal и устойчивый ключ
  `(tenant, book, counterparty, source_kind, source_id, component)`.
  Источник invoice, manual или credit_refund; ни booking price, ни memo не
  становятся источником обязательства автоматически.
- `settlement_documents` + allocations/events: одно юрлицо, контрагент,
  направление и валюта; несколько обязательств одного контрагента допускаются.
- `external_payments` + immutable allocations: один реальный внешний source
  identity и несколько распределений; точная сумма распределений равна
  подтвержденной сумме. Частичные платежи сохраняют невыплаченный резерв.
- `financial_operation_entries`: связь ровно одного хозяйственного эффекта с
  journal G. Операция, событие, документ и команда имеют разные идентификаторы.
- `provider_admission_requests` + versions/evidence references: намерение
  подключения и доказательства; положительный оперативный допуск не выдается
  H по произвольному тексту владельца.

FK включает tenant/book во всех финансовых связях. Ни чужой контрагент, ни другая
книга, ни валюта другого обязательства не могут попасть в расчет. Версии источников
и строк после выпуска сохраняются; архивирование карточки не переписывает историю.
Подтвержденная запись платежа содержит actor, recorded_at, actual_external_date,
source account alias, external reference, направление, сумму и признак manual
attestation. Внешняя ссылка хранится приватно; секреты/ключи не принимаются.

## Главные инварианты

Пусть A — исходный principal обязательства, P — подтвержденные распределения
денег, C — зачет кредитового документа в еще неоплаченную часть, R — активные
резервы. После каждой транзакции: `P >= 0`, `C >= 0`, `R >= 0`, `P + C + R <= A`.
Это суммы только одной книги и валюты, вычисляемые из истории событий.
P — действующие подтвержденные allocations, с учетом разрешенных corrections,
а не сумма каждого исторического confirmation/replacement. C — действующий
неоплаченный credit; отмена кредитового документа сохраняет его историю, но
не считает отмененный зачет действующим.

Manual obligation в H — **новое начисление**, не свободная строка с лимитом:
его создание атомарно записывает источник obligation, выбранные control/counter
accounts и новую сбалансированную проводку G. Receivable: Dr control asset /
Cr явно выбранный revenue или liability; payable: Dr явно выбранный expense
или asset / Cr control liability. Последующие выплаты используют зафиксированный
control account. Ни новый расход, ни деньги не создаются из одного текстового
source/memo. Подключение уже проведенной manual/opening G-entry к новому
обязательству и импорт начальных obligation balances не входят в первый H:
не дублировать начисление и не угадывать legacy allocation. Такой запрос
возвращает reconciliation-required и требует отдельного принятого процесса.

Резерв не создает денежной проводки. Подтверждение оплаты одновременно уменьшает
R, увеличивает P, фиксирует внешний source identity и создает сбалансированную
проводку G. Платеж больше выбранного резерва/остатка отклоняется. Одна команда,
тот же external source с другим ключом или другая расчетная форма не повторяет эффект.
Для наличных тоже нужен устойчивый receipt reference; новый browser tab не дает
права придумать новый ID для уже записанного факта.

Внешний платеж в полном объеме распределяется на выбранные обязательства.
Нераспределенная часть/аванс не создается автоматически: отдельный будущий процесс.
Документ может подтверждаться частями с разными внешними references; ранее
подтвержденные allocations не редактируются. Неиспользованный reserve освобождается
явным release/cancel, а не фоновым таймером.

Если кредит выдан до оплаты, он закрывает неоплаченную часть C без увеличения P.
Если часть уже оплачена, неоплаченная часть закрывается C, а оплаченная часть
создает отдельное встречное `credit_refund` обязательство. Старые денежные записи
и A не переписываются. Например, invoice 100, получено 70, credit 50: C=30,
встречный возврат=20; исходное обязательство закрыто 70+30, выручка/деньги/возврат
видны отдельно. Возврат 20 не означает, что его отправил провайдер.

Credit issue требует отсутствия активных резервов по исходному обязательству.
Пользователь сначала явно освобождает неподтвержденный резерв или выясняет
неопределенный внешний результат. Credit нельзя выдать больше неотмененного
остатка исходных строк. Расчеты встречного возврата имеют тот же cap-инвариант.
Свободное ledger reverse не исправляет H-confirmation. Для correction H
предлагаются отдельные состояния effective payment: confirmed, corrected,
voided, с immutable version/event history. External identity
`(book,direction,source_account_alias,external_reference)` сохраняется навсегда
за тем же payment_id; изменение identity или второй payment_id с тем же source
отклоняется. Ни corrected, ни voided не освобождают source key.

При отсутствии credit/refund зависимостей разрешена явная correction ошибочной
attestation. Она одной транзакцией сторнирует прежнюю проводку и allocations,
возвращает прежнюю распределенную сумму в тот же reserve, затем создает
replacement version/journal и его allocations. P/R вычисляются по effective
версии, не удваивая старые события; replacement не больше восстановленного
резерва. Каждый journal component/revision имеет собственный once-only effect ID.
Для полного void нужен явный факт ошибочного подтверждения/отсутствия денег;
не фактический внешний refund. Reserve остается до отдельного безопасного release.

Если есть issued credit, реально confirmed refund, sent/unknown dependent
operation, исходная payment correction получает FINANCIAL_RECONCILIATION_REQUIRED.
H не предлагает отменить реальный refund или изменить источник, чтобы обойти
этот отказ. Разрешенный credit void возможен только без фактических/sent/unknown
расчетов встречного refund и без reserves: mirror credit, undo effective C,
cancel незатронутого refund claim выполняются атомарно, сохраняя A/history.
Исправление сложного графа после реального refund требует отдельного принятого
reconciliation/counter-claim процесса; H до этого честно отказывает. Этот отказ
не изменяет деньги/историю и сам является проверяемым acceptance case.

## Транзакция и совместимость с G

READ COMMITTED и существующая `gba.lock_ledger(tenant)` сериализуют issue,
reserve, confirmation, credit и закрытие периода. Ledger lock берется перед
membership share; дополнительные locks вводятся только с фиксированным порядком.
Деньги не проверяются перед отдельной транзакцией вставки. SQL контролирует тот же
cap и source uniqueness, что и API; deferred checks проверяют завершенное состояние.

В H предлагается только forward migration `0021_*`. Миграции 0001–0020 и их
checksums не меняются. Уже существующая БД с иной незакоммиченной 0020 требует
отдельного обследования/разрешения; этот план ее не исправляет.

G сейчас допускает только manual/opening/reversal в SQL, Pydantic и Zod.
Источники invoice, credit, payment добавляются согласованно; не маскировать их
как manual. Для расширенных journal views вводится явный schema v2 и согласованное
чтение клиентом. G write contract v1 manual/opening и существующие v1 записи
остаются доступными. Legacy read с H-источниками возвращает явное требование
обновления/выбора v2, не скрывает финансовые записи из ответа/ведомости.
Обычное G reverse отказывает для H-owned entries; исправление идет через H.
Ведомость G продолжает учитывать все проводки, без второго cash/balance storage.

Reference-only receipts и minimal session recovery распространяются на H с
новой конечной версионированной схемой commands. После потери ответа, reload,
navigation или истечения обычного receipt проверяется неизменяемый результат.
Отмена unresolved key сериализуется и запечатывает поздний исходный запрос.
Денежное тело, source reference, memo и токен в browser storage не записываются.
Расширение recovery не меняет семантику шести существующих G-команд.

## Права, модули и честные состояния

Предлагаются существующие finance.read/manage для owner/manager всей компании;
FINANCE_CLOSE остается для периодов. Front desk/artist, филиальный member,
delegate, platform support и другая компания не получают H-доступ.
Требование двух разных людей для prepare/approve в мастер-плане не установлено;
на первом H подтверждение одного авторизованного человека явно отображается.
Новый money/send permission без решения владельца не вводится.

Finance уже technically_verified для G; это **не** включает неподготовленный H.
Новый server feature gate по FIN-03 запрещает H-mutating endpoints до его
приемки, не понижая FIN-01 и не переписывая опубликованные configs. Сначала
FIN-03 implemented; тестовый override только в fixtures и отдельный negative gate.
После приемки обычные fixtures используют реальную production registry.

Отключенный finance сохраняет историю, чтение и command recovery. Новые issue,
reserve и денежные confirmations блокируются; non-money release разрешен.
Неопределенный внешний перевод нельзя считать неуспешным и освобождать только
из-за отключения модуля, закрытия вкладки или отсутствия HTTP-ответа.

H admission registry не выполняет сетевых проверок провайдера и не активирует
capabilities. not_checked/suspended/unsupported доступны как честные состояния;
test_access/approved требуют отдельной подтвержденной проверки соответствующей
среды, аккаунта и операции. Произвольная owner assessment не становится машинным
разрешением payment action. FIN-02 остается planned до K/подписи/dedup/order tests.

## Выполнение по фазам

1. Согласовать этот объем и ADR, включая paid-credit/refund и явное признание по
   выбранным счетам. Независимо проверить equations, lifecycle и границы reuse.
2. H1: typed contracts, migration, invoice draft/issue и journal bridge; red→green
   для атомарного source link и запрета редактирования issued history.
3. H2: обязательства/расчетные docs/резерв/частичные external confirmations;
   реальные SQL races двух docs, source dedup и unknown-result recovery.
4. H3: credits/refund obligations, corrections и dependency guards; проверить
   исторические деньги и все варианты paid/unpaid/mixed, ledger v2 compatibility.
5. H4/UI: admission без activation, desktop/mobile, Axe, honest labels/states.
6. Полная suite, независимый обзор, exact-SHA CI, отдельный acceptance commit.

Не объявлять FIN-03 technically_verified после одной H1/H2 фазы и не подменять
незавершенные состояния mock provider response. Никаких новых библиотек без
подтвержденной необходимости; текущий stack покрывает этот план.

## Минимальная матрица приемки

| ID | Требуемая фактическая проверка | Результат до кода |
|---|---|---|
| H-01 | Invoice/manual accrual + obligation + balanced journal/control-account link + minimal receipt атомарны; rollback не оставляет частичный эффект; legacy G-entry не привязывается/не начисляется повторно автоматически | NOT TESTED |
| H-02 | История issued invoice/credit/payment неизменяема; draft versions используют expected revision | NOT TESTED |
| H-03 | Два документа одновременно резервируют 70 из A=100: ровно один принимает 70, второй отказывается; ожидание lock наблюдается в pg_locks | NOT TESTED |
| H-04 | Два concurrent partial confirmations, release/confirm и credit/reserve сохраняют P+C+R<=A и не дают отрицательные counters | NOT TESTED |
| H-05 | Idempotency replay, другой ключ с тем же external identity, reload/24h receipt expiry/cancel-before-late-original не повторяют деньги | NOT TESTED |
| H-06 | Credit 100/paid70/credit50 дает C30/refund20; correction сохраняет external identity и effective P/C/R; реальный refund не отменяется ради correction; deferred→manual recognition→credit по явно выбранному счету дает согласованный G balance | NOT TESTED |
| H-07 | Закрытый период запрещает все money effects H; права scope/tenant/book/currency/FK не смешиваются; H-owned ledger reverse запрещен | NOT TESTED |
| H-08 | Direct SQL не обходит budget/source/history; повреждение утвержденных controls/readiness дает 503 | NOT TESTED |
| H-09 | Finance OFF/FIN-03 unverified блокируют новые effects; read/recovery/non-money release остаются допустимыми | NOT TESTED |
| H-10 | Admission metadata не включает capabilities; без проверенной интеграции нет network charge/refund/webhook handling | NOT TESTED |
| H-11 | Desktop/mobile + real OIDC/API/PostgreSQL: invoice, reserve/partial pay, response loss/reload, credit/refund, truthful states, Axe/overflow | NOT TESTED |
| H-12 | G regression + old/new journal contracts + full Python/web/build/container CI точного code SHA и независимый review | NOT TESTED |

Baseline G свежо проверен через connected GitHub: CI
[37499485016](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37499485016)
для 5be6e7a PASS. Его 861 passed/1 skipped не являются проверкой H.
Реальные результаты H фиксировать в своей evidence directory после запуска.
