# План слияния веток в `main` — на согласование, 2026-10-12

**Статус: владелец принял решения 2026-10-12 — см. раздел «Решения владельца».** Текст
плана ниже сохранён в том виде, в каком он был предложен. Данные для проверки:
[STACK.json](evidence/2026-10-12-merge-plan/STACK.json).

## Решения владельца, 2026-10-12

Исполнитель задал два вопроса с готовыми вариантами; владелец выбрал:

1. «Should I move main to the verified head of the stack now?» — «Yes, fast-forward main
   (Recommended)». Условия этого ответа: исполнитель публикует ветку с планом, ждёт
   зелёный CI её точного коммита, одним обычным push без force переносит на него `main`
   и ждёт CI на `main`. PR не открываются, ничего не развёртывается. Откат потребует
   force-push и отдельного разрешения.
2. «How should the old parallel line (pull requests #2-#5) be treated?» — «Superseded,
   keep branches (Recommended)». PR #2–#5 считаются заменёнными основной линией и не
   сливаются; их ветки сохраняются. Страницы этих PR на GitHub закрывает владелец.

Не решено: пункты 4–6 раздела «Что нужно решить» и нужен ли отчёт по записям для групп
компаний.

Где сейчас `main`, читать из `git ls-remote origin main`. Запись о выполнении
добавляется следующим коммитом на ветку `codex/merge-plan`.

## Коротко

- Вся платформа лежит вне `main`: 111 коммитов, 719 файлов. В `main` один файл
  `README.md`.
- Эти 111 коммитов — одна прямая линия без ответвлений и merge-коммитов, и `main` —
  её начало. Перенести `main` на вершину линии можно одним действием и без конфликтов.
- Рекомендация: **перемотать `main` на проверенную вершину `79115a5` (fast-forward), а не
  сливать 22 PR по одному.** Все идентификаторы коммитов сохраняются; на них ссылаются
  реестр готовности в коде и документы (87 из 111 коммитов названы в
  документах по идентификатору).
- Старую параллельную линию (PR #2–#5) не сливать: это ранняя реализация тех же функций с
  другой нумерацией миграций.
- Слияние ничего не развёртывает и не меняет статусы готовности.

## Что есть сейчас

### Основная линия

`main` — `46cd866` от 2026-10-04. Вершина — `79115a5`, ветка `codex/web-dependency-audit`. Разница:
719 файлов, 171699 добавленных строк, миграции 0001–0035. Каждая строка таблицы
включает всё, что выше неё.

| № | Ветка | Голова | Коммитов от `main` | PR | Содержание |
|---|---|---|---|---|---|
| 1 | `codex/universal-business-foundation` | `2f16380` | 15 | [#1](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/1) | Build universal business foundation and versioned legal-entity drafts |
| 2 | `codex/package-e-isolation-audit` | `bbe6ecd` | 17 | [#6](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/6) | Fix selected-company readiness and membership queries (Package E0) |
| 3 | `codex/package-e1-counterparties` | `3983dd4` | 20 | [#7](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/7) | Add versioned counterparties, contacts and manual matching (E1) |
| 4 | `codex/package-e2-file-validation` | `4a6f63b` | 22 | [#8](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/8) | Prepare bounded file validation and preserve API CSP (E2 prerequisite) |
| 5 | `claude/package-e2-documents` | `c5a3908` | 24 | [#9](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/9) | Add versioned documents, verified files and counterparty links (E2) |
| 6 | `claude/package-e3-agreements` | `b8834fb` | 26 | [#10](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/10) | Add versioned contracts with counterparties (E3) |
| 7 | `claude/package-f-occupancy-plan` | `b4c8563` | 28 | нет | план пакета F; входит в PR #11 |
| 8 | `claude/package-f-occupancy` | `ed7884e` | 32 | [#11](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/11) | Add shared resource occupancy and staff reservations (package F, CORE-04) |
| 9 | `claude/stage1-closure` | `de5fada` | 34 | нет | закрытие этапа 1 |
| 10 | `claude/stage2-finance-plan` | `151472a` | 36 | нет | план этапа 2; служит основой PR #12 |
| 11 | `codex/package-g-ledger-review` | `5be6e7a` | 41 | [#12](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/12) | Package G: technically verified ledger foundation (FIN-01) |
| 12 | `codex/package-h-finance-plan` | `925ae02` | 43 | [#13](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/13) | docs: propose Package H invoices and settlement rules |
| 13 | `codex/package-h-invoices` | `18e3f5e` | 48 | [#14](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/14) | H1 foundation: strict finance contracts and closed workflow gate |
| 14 | `codex/package-h1-persistence` | `75e809b` | 51 | [#15](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/15) | H1 backend: atomic invoice accruals behind the closed workflow gate |
| 15 | `codex/package-h2-settlements` | `e93ca5c` | 61 | [#16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16) | feat(finance): H2 manual accruals, settlement reserves and attested confirmations |
| 16 | `codex/package-h3-settlement-guards` | `c6c5d89` | 64 | [#17](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/17) | H3: settlement guards after the independent H2 money review (F1–F4) |
| 17 | `codex/package-h3-credits` | `807ed59` | 66 | [#18](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/18) | H3: issue credit notes and track separate refund obligations |
| 18 | `codex/package-h3-payment-corrections` | `1d96a64` | 68 | [#19](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/19) | H3: correct and void payment attestations with immutable revisions |
| 19 | `codex/package-h3-credit-voids` | `785fb7f` | 71 | [#20](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/20) | H3: void issued credits and cancel untouched refund obligations |
| 20 | `codex/h3-forward-corrections` | `12875e8` | 72 | [#21](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/21) | fix(finance): resolve H3 review F1–F5 with forward-only 0030 |
| 21 | `codex/package-h4-ui-admission` | `319f144` | 73 | [#22](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/22) | H4: financial workspaces and provider admission metadata |
| 22 | `codex/package-h-acceptance` | `9ef3734` | 77 | нет | приёмка пакета H (FIN-03) |
| 23 | `codex/package-i4-workforce-screens` | `c6b8e34` | 98 | нет | пакет I: срезы I0–I4 и настройка видимости смен |
| 24 | `codex/package-i4-review-corrections` | `4630ca3` | 108 | нет | исправления обзоров и приёмка пакета I (WORK-01, CORE-04) |
| 25 | `codex/web-dependency-audit` | `79115a5` | 111 | нет | обновление next и source-map-js |

На линии 18 PR (#1 и #6–#22) и 7 веток без собственного PR. Все 22 PR репозитория —
черновики. Только PR #1 направлен в `main`; остальные направлены в предыдущую ветку
линии. Два участка линии не входят ни в один PR: от `claude/package-f-occupancy` до
`claude/stage2-finance-plan` и от `codex/package-h4-ui-admission` до вершины.

### Старая линия: PR #2–#5

| PR | Ветка | Голова | Содержание |
|---|---|---|---|
| [#2](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/2) | `claude/keen-mayer-lg9ift` | `ef423f3` | Add limited delegation between independent businesses |
| [#3](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/3) | `codex/booking-state-isolation` | `b864789` | Scope readiness and member lists to the selected business |
| [#4](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/4) | `codex/company-departments` | `161509f` | Add versioned company departments with a tenant-safe hierarchy |
| [#5](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/5) | `codex/company-groups` | `1542b70` | Add consented company groups and restricted booking reports |

- Она отходит от основной линии на коммите `eaa6233` и содержит 9 коммитов,
  которых в вершине нет.
- Делегирование, отделы, группы компаний и исправление выбора компании позже сделаны
  заново на основной линии. Пробное слияние старой линии в вершину даёт 40 конфликтов.
- Номера миграций расходятся: в старой линии `0011_delegation_grants.sql`, `0012_departments.sql`, `0013_company_groups.sql`;
  на основной линии под этими номерами другие миграции. Опубликованные миграции
  0001–0035 менять нельзя, поэтому слить старую линию как есть невозможно.
- Файлы старой линии, которых на основной нет под этими именами: `company_groups.py`, `group_membership.py`, `group_reports.py`, `0011_delegation_grants.sql`, `0012_departments.sql`, `0013_company_groups.sql`, `company-groups.tsx`, `group-api.ts`.
  Группы компаний на основной линии есть, но в другом виде. Одной функции там нет
  совсем: отчёта по записям для групп компаний (`group_reports.py`, счётчики по
  участникам группы). По записи от 2026-10-04 в старой линии также другая версия прав
  доступа.
- Документы проекта от 2026-10-04 и 2026-10-05 уже требуют не смешивать эти линии.

### Настройки репозитория

Прочитано из открытого API GitHub.

- Репозиторий публичный, основная ветка — `main`, защита `main` выключена.
- CI запускается на каждый push и на каждый PR.
- `deploy-staging` и `promote-production` запускаются только вручную и требуют
  подтверждения и настроенных сред GitHub. На слияние они не реагируют. Сейчас их файлов
  в `main` нет; после слияния они появятся в списке Actions как ручные.
- На страницах PR 23 комментария: 22 автоматических от CodeRabbit, по одному на каждом
  PR, и один от владельца на PR #17. Комментариев к строкам кода нет. Содержание
  комментариев для плана не разбиралось.

### Локальные копии на этом компьютере

- Локальных веток 57. Вне основной линии — только старая линия
  (в том числе её локальная копия `codex/readiness-validation`) и один коммит-запись
  обзора `codex/package-i4-review`, файл которого уже есть в вершине байт в байт.
- Рабочих копий 28. В 7 из них есть незакоммиченные изменения:

| Рабочая копия | Коммит | Изменённых путей |
|---|---|---|
| `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking` | `2f16380` | 19 |
| `C:/Users/alexa/.codex/worktrees/package-g-independent-review/Gorgona Booking` | `151472a` | 40 |
| `C:/Users/alexa/.codex/worktrees/package-i4-corrections-review/Gorgona Booking` | `490652b` | 9 |
| `C:/Users/alexa/Documents/ChatGPT/gorgona-e2-documents` | `151472a` | 9 |
| `C:/Users/alexa/Documents/ChatGPT/gorgona-package-i1-review` | `1419073` | 23 |
| `C:/Users/alexa/Documents/ChatGPT/gorgona-package-i2-review` | `69270cc` | 16 |
| `C:/Users/alexa/Documents/ChatGPT/gorgona-package-i3-review` | `49276bf` | 14 |

Слияние на GitHub эти копии не трогает. Что именно в них изменено, для этого плана не
разбиралось; чистить их нельзя.

## Варианты

| | A. Перемотка `main` | B. PR по очереди | C. Один PR с вершины |
|---|---|---|---|
| Действий | один push | 18 слияний и не меньше двух новых PR | один новый PR и одно слияние |
| Идентификаторы коммитов | сохраняются | сохраняются только при способе «Create a merge commit» | сохраняются только при способе «Create a merge commit» |
| Конфликты | невозможны: `main` — начало линии | не ожидаются | не ожидаются |
| Новые коммиты в `main` | нет | merge-коммит на каждый PR | один merge-коммит |
| Запусков CI на `main` | один | на каждое слияние, по 12–20 минут | один |
| CodeRabbit | новых PR нет, вызова не ожидается | ожидается вызов при выводе PR из черновика и на новых PR | ожидается вызов на новом PR |
| Кто выполняет | исполнитель одним `git push`, по прямому разрешению | владелец в интерфейсе GitHub | владелец в интерфейсе GitHub |
| След на GitHub | ожидается: PR #1 отметится как слитый, остальные закрываются вручную | каждый PR отмечается как слитый | новый PR отмечается как слитый, старые закрываются вручную |

**Рекомендация — вариант A.** Вершина включает все пакеты, и её CI с полным набором
тестов зелёный; записи о приёмке пакетов лежат в репозитории. Слияние по одному PR не
добавляет проверки, но добавляет 18 мест, где можно ошибиться со способом слияния. В
варианте B каждый PR нужно вывести из черновика, перенаправить в `main` после слияния
предыдущего и слить способом «Create a merge commit». Варианты B и C создают или
открывают PR, а CodeRabbit подключён к репозиторию и отвечает на каждый PR; запускать его
без отдельного разрешения владелец запретил.

**Чего не делать ни в одном варианте:** «Squash and merge» и «Rebase and merge». Оба
создают новые коммиты с другими идентификаторами, и ссылки реестра готовности и
документов перестанут указывать на историю `main`.

## Что нужно решить

1. **Способ:** A, B или C. Рекомендация — A.
2. **До какого коммита.** Рекомендация — вершина линии с зелёным CI на точном коммите.
   Сейчас это `79115a5`: с приёмкой пакета I и обновлением зависимостей. Коммит с этим
   планом — документы поверх неё; если он опубликован и его CI зелёный, целью становится он.
   Можно остановиться раньше, например на `9ef3734` (приёмка пакета H), если пакет I
   должен ждать пилота.
3. **Старая линия #2–#5.** Рекомендация — закрыть четыре PR как заменённые, ветки
   сохранить. Отдельно решить, нужен ли отчёт по записям для групп компаний: если нужен,
   это новая задача на текущей основе, а не слияние старого кода.
4. **Страницы PR.** Кто закрывает оставшиеся PR и с каким пояснением. У исполнителя нет
   входа в GitHub для действий с PR; `git push` у него работает.
5. **Защита `main` после слияния.** Рекомендация — включить: изменения только через PR
   и только при зелёном CI. Это настройка владельца.
6. **Ветки.** Рекомендация — пока не удалять: документы называют их по именам.

## Порядок для варианта A

1. Перед действием заново прочитать удалённые головы. Если `main` уже не `46cd866` или
   вершина изменилась — остановиться.
2. Убедиться, что CI точного коммита-цели зелёный.
3. Выполнить `git push origin <коммит-цель>:refs/heads/main` без `--force`. Если это не
   перемотка, Git сам отклонит push.
4. Проверить, что удалённый `main` равен цели, и дождаться CI на `main`.
5. Посмотреть, что стало со страницами PR, и закрыть оставшиеся по решению из пункта 4.
6. Записать результат и обновить передачу: новые ветки начинаются от `main`.

Шаги 1–4 и 6 исполнитель может выполнить сам после прямого разрешения владельца.

## Чего слияние не делает

- Не развёртывает: оба workflow развёртывания ручные, Azure не затрагивается.
- Не меняет статусы готовности: `pilot_accepted` и `production_approved` остаются
  отдельными решениями владельца.
- Не трогает локальные рабочие копии и незакоммиченные изменения в них.
- Не закрывает открытые вопросы: независимая проверка `ec39622` (пакет H), непроверенные
  ситуации экранов «Персонала», 5 high в аудите инструментов разработки, отсутствие пилота.

## Риски и откат

- **Откат.** Вернуть `main` на `46cd866` можно только через force-push; это отдельное
  разрушающее действие и требует отдельного разрешения. Пока от `main` никто не начал
  новую работу, такой откат ничего не ломает.
- **Ручные workflow.** После слияния кнопки `deploy-staging` и `promote-production`
  появятся в Actions. Без настроенных сред и подтверждения они остановятся на первой
  проверке; запускать их без отдельного решения по Azure нельзя.
- **Страницы PR.** Что GitHub отметит PR #1 как слитый, а остальные оставит открытыми, —
  ожидание, а не проверенный факт. Это проверяется на шаге 5.
- **Публичность.** Код уже публичен в ветках; после слияния его будет показывать главная
  страница репозитория.

## Что проверено для этого плана

| Проверка | Результат |
|---|---|
| `main` — начало линии: `git merge-base --is-ancestor` | PASS |
| Линия прямая: 111 коммитов, merge-коммитов 0 | PASS |
| Все 25 веток линии лежат на ней по порядку; головы 22 PR совпадают с головами веток | PASS |
| Идентификаторы из реестра готовности (5) достижимы из вершины | PASS |
| Пробное слияние старой линии в вершину (`git merge-tree`, без записи): 40 конфликтов | FAIL — ожидаемо; поэтому старая линия не сливается |
| CI вершины `79115a5`: [run 38317477223](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38317477223) | PASS |
| Оба workflow развёртывания запускаются только вручную | PASS |
| Единственный локальный коммит вне обеих линий: его файл уже есть в вершине байт в байт | PASS |
| Поведение страниц PR после слияния | NOT TESTED |
| Разрешённые способы слияния и правила репозитория: без входа в GitHub не читаются | NOT TESTED |
| Содержимое незакоммиченных изменений в 7 рабочих копиях | NOT TESTED |
| CI каждой промежуточной головы PR заново не перечитывался | NOT TESTED |

## Основание

2026-10-12 исполнитель в отчёте о срезе аудита зависимостей рекомендовал следующим
подготовить план слияния. Владелец ответил: «Continue». Исполнитель понял это как
согласие подготовить план и сказал об этом в начале работы. Согласия на само слияние
этот ответ не содержит; оно дано отдельно — см. «Решения владельца».
