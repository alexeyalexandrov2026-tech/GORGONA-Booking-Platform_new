# Независимый повторный обзор исправлений I4 — 2026-10-12

**Обзор выполнен. Проверка исправлений — FAIL: две средние находки и одна
низкая. Пакет I не принят.** Критических или высоких находок в данном объёме
не выявлено; это не полный аудит всей платформы. WORK-01/CORE-04 остаются
`planned`, workforce закрыт вне фикстур. Продуктовый код не исправлялся в этом
обзоре: зафиксированы воспроизводимые дефекты для следующего среза.

Рецензент не писал проверяемые исправления продуктового кода. Ранее он подготовил
документы приёмки; это не делает его автором исправлений a806380..b66eb41.
Обзор выполнен в своей рабочей копии и на своих одноразовых кластерах.

## Исходная точка и границы

| Поле | Проверено |
|---|---|
| Репозиторий | alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new |
| Ветка | codex/package-i4-review-2, локальная |
| Рабочая копия | C:/Users/alexa/.codex/worktrees/package-i4-review-2/Gorgona Booking |
| База обзора | 0356eb564ca645ea2c6e50aa3f5844b738d45276, документы приёмки поверх c6b8e34 |
| Код | b66eb4140c1101d78e1bd4068eac537aab922b38; diff a806380..b66eb41 — 16 файлов |
| Удалённая I4 | c6b8e341a7e88957ee5011e54e9aa06453b31b49; проверено заново до записей |
| CI удалённой базы | completed/success, push run 38204334830, head_sha=c6b8e34 |
| PR I4 | API state=all с точным head вернул 0 |
| SHA256 таблицы ответа автора | PASS: 16/16 Git blobs; рабочие файлы также совпали с HEAD |
| Кластеры PostgreSQL 18.6 | собственные data и data-extra, порты 54378 и 55504; оба остановлены |
| Публикация / готовность | push/PR/merge и повышение готовности не выполнялись |

Прочитаны [первый обзор](INDEPENDENT_REVIEW.md),
[ответ автора](AUTHOR_RESPONSE.md),
[подготовка приёмки](../2026-10-12-i-acceptance/ACCEPTANCE.md), ADR-0025,
актуальная передача, AGENTS и действующие границы архитектуры. Устаревшие
предложения из памяти не заменяли текущую передачу или разрешение владельца.
Использованы skill evidence-engineering, Git/GitHub, штатный PostgreSQL,
pytest, Playwright, Ruff/mypy и npm. Новых зависимостей нет: npm ci --ignore-scripts
установил существующий lockfile в новой копии. CodeRabbit не запускался.

## Находки

### R2-1 — medium / P2 — F1 обходится после повторного приглашения в тот же филиал

- **Где:** api/src/gorgona_booking/business/shift_changes.py:139 и :253–258;
  дополнительный признак — business/workforce_desk.py:145–150.
- **Причина:** home() требует профиль, связанный с действующим членством.
  Повторное приглашение создаёт новое членство; прежний профиль/назначения
  сохраняют стабильного пользователя. До создания нового профиля home()=None,
  а `location is not None and ...` пропускает проверку скрытых смен. SQL проверяет
  владельца исходного назначения по стабильному user_id, поэтому запрос проходит.
- **Воспроизведение:** сотрудник A держит смену, B — другую; скрыть смены филиала,
  подтвердить 403 при обычном чтении B, отозвать A и снова пригласить его как
  artist в тот же филиал. Не создавать новый профиль. От имени A отправить новый
  swap с известным id смены B, затем прочитать `/my-changes/{id}/shifts`.
- **Ожидалось:** новый обмен отказан, скрытая смена не возвращается.
- **Получено:** desk.profile=null, desk.colleague_shifts=visible; swap 200;
  чтение запроса 200 и staff_profile_id скрытого держателя B. Новая API-проба
  ожидала 403 и упала. Это действительное состояние жизненного цикла, без порчи
  политик или функций и без передачи пользовательского контекста в HTTP.
- **Предел:** это утечка скрытой смены в своей компании/филиале; утечка между
  компаниями этой пробой не обнаружена. Обмен мог ещё не получить согласие или
  утверждение — скрытая смена уже прочитана.
- **Следующая правка:** проверять безопасный домашний филиал стабильного
  пользователя либо отказать новому swap при невозможности его определить,
  до поиска чужой смены. Сохранить чтение собственной истории/старого запроса,
  повтор уже записанного обмена и отдельные правила передачи/открытой смены.

### R2-2 — medium / P2 — F9 ограничивает последовательные отмены, но не гонку разных ключей

- **Где:** api/src/gorgona_booking/business/workforce_desk.py:304–318.
- **Причина:** COUNT и INSERT выполняются без исключительной секции на
  actor/business. Общий механизм квитанций сериализует один ключ, но не разные
  ключи. Членство берётся FOR SHARE, что тоже не сериализует такие запросы.
- **Воспроизведение:** создать 19 маркеров отмены; на своём кластере удержать
  SHARE на gba.idempotency_keys и одновременно отправить два cancel разных
  ключей от того же человека. SELECT проходит, INSERT ожидает. Дождаться в
  pg_locks двух конкретных RowExclusiveLock-ожидающих INSERT этой таблицы,
  затем освободить барьер.
- **Ожидалось:** [200,429], ровно 20 маркеров.
- **Получено:** [200,200], ровно 21 маркер. Три независимых случая FAIL:
  workforce open, module off и readiness not accepted. В каждом действительно
  наблюдались два ожидающих INSERT; гонка не засчитана по одному запуску задач.
- **Барьер:** только управляет порядком настоящих транзакций в тестовом
  кластере. Он не является предлагаемым production-механизмом.
  Совместимость SELECT/SHARE и конфликт INSERT/SHARE проверены по
  [официальной документации PostgreSQL 18](https://www.postgresql.org/docs/18/explicit-locking.html)
  на 2026-10-12; исполнение — PostgreSQL 18.6.
- **Следующая правка:** одна сериализация на человека/компанию вокруг выдачи
  нового маркера и проверки счётчика, с повторной проверкой после ожидания.
  Не ограничивать resolve, известный повтор и уже совершённую реальную команду;
  сохранить безопасный порядок блокировок. Не ослаблять закрытый модуль.

### R2-3 — low / P3 — N3 скрывает настоящий пользовательский текст по совпадению строки

- **Где:** web/components/timesheets.tsx:56–63, :356 и :701.
- **Причина:** given(reason) исключает четыре строковых значения независимо
  от происхождения. Причина исправления/решения может законно равняться
  `Clock-in`, `Break start`, `Break end` или `Recorded clock-out`.
- **Воспроизведение в браузере:** в существующем I4-сценарии заменить обычную
  причину исправления и её ожидаемый текст на `Clock-in`. Отправить исправление
  и ожидать этот текст в своей карточке, как обычную причину.
- **Получено:** реальный desktop-браузер подтвердил отправку, версия стала
  pending, но карточка не содержит причины; expect(...).toContainText('Clock-in')
  упал на временной строке 927. Отдельная API-проба PASS: action=correct,
  persisted reason=Clock-in. Запись сохранена, скрыт её текст в интерфейсе.
- **Предел:** браузерная отрицательная проба остановилась на desktop из-за
  штатного --max-failures=1; mobile и последующие фазы в ней не выполнены.
  History использует ту же функцию, но этот путь подтверждён чтением, не
  отдельной браузерной пробой. В журнале раннера также есть ошибка завершения
  после остановки на первом падении; основное падение — указанная проверка текста.
- **Следующая правка:** различать системный и человеческий текст по событию/
  происхождению, а не значению строки. Проверить корректировки и решения,
  в том числе копирование причин при последующих версиях.

## Соответствие шестнадцати пунктам первого обзора

PASS чтением не заменяет отдельную браузерную проверку. В этой таблице указан
способ проверки; неподтверждённые пути перечислены ниже.

| Пункт | Итог повторного обзора |
|---|---|
| F1 | FAIL: обычные hidden/probe/replay проверки PASS, но R2-1 обходит правило после повторного приглашения |
| F2 | PASS: SQL вычисляет признак по утверждённой версии, DTO/строгая web-схема требуют поле, экран использует effective; две API-ситуации проходят. Целевые браузерные ситуации не запускались |
| F3 | PASS: действующие ключи 200/201/255 символов, отказ прежней команды и ограниченный SHA256 audit target; штатный тест пройден |
| F4 | PASS воспроизведения документированной границы: до expiry исходная команда 422; после выставления expiry в прошлом — 200/committed. Постоянная защита не заявлена; решение владельца остаётся |
| F5 | PASS: выбор Privacy связан с location; обычный и дополнительный браузер прошли обе ширины |
| F6 | PASS чтением: текст признаёт незавершённую операцию; точный UI-путь ongoing отдельно не проверялся |
| F7 | PASS: Schedule реально показывает 2026-10-11 при UTC 2026-10-12 в Pacific/Honolulu на обеих ширинах; My shifts default — чтением, отдельное ожидание его default не добавлялось |
| F8 | PASS: оба добавляемых человека в дополнительной фикстуре имеют company-wide членство без домашнего профиля; реальный сценарий добавления проходит на desktop/mobile. Выбор другого, не начального филиала отдельно не проверен |
| F9 | FAIL: последовательные проверки PASS; пара разных ключей проходит за предел 20 — R2-2 |
| N1 | PASS: directory исключает disabled account, штатный API-тест пройден |
| N2 | PASS чтением: declined без effective явно ничего не вводит в действие; отдельная целевая браузерная проба не запускалась |
| N3 | FAIL: системные строки скрыты, но вместе с ними допустимая человеческая причина — R2-3 |
| N4 | PASS: audit setting содержит revision и выбранный bool; штатная проверка пройдена |
| N5 | Без правки: лимит окна 62 дня, даты не ограничены; API/код прочитан, новая отдельная проба дат не добавлена. Решение владельца |
| N6 | PASS: Draft отсутствует для published/cancelled по коду; published проверен браузером. Cancelled отдельно не упражнялся |
| N7 | PASS: 2 receipt-race теста и visibility race прошли; идентифицируется верхняя транзакция писателя, не xmin. Plain-staff маршрут использует artist headers; SQL-комментарий не обещает SQL-client auth |

## Архитектура и повторное использование

Исправления переиспользуют _access/authorized_tenant, штатную квитанцию
IdempotencyScope/claim/complete, audit, workforce._writes и существующую схему.
Новых таблиц, миграций, зависимостей или самостоятельной таблицы занятости нет.
Типизированные версии контрактов и HTTP-границы сохраняются. Проверка
shifts_visible общая для desk/read и propose, но отсутствие безопасного home
ломает использование этой проверки в R2-1. COUNT R2-2 находится вне общего
ключевого механизма взаимного исключения.

Privacy запрещает новый swap в API, а не в SQL-триггере. SQL-client с доверенной
runtime-ролью/контекстом находится внутри существующей границы доверия, и это
ограничение прямо описано автором; данный обзор не объявляет его JWT-аутентификацией.
Пути handover/pickup и чтения собственных старых запросов сохранены; в нормальном
состоянии их штатные проверки PASS. R2-1 использует именно разрешённый HTTP API.

## Собственные команды и результаты

Все API-команды — из api собственной копии, PYTHONPATH=api/src;api,
PYTHONDONTWRITEBYTECODE=1, GBA_REQUIRE_POSTGRES=1, для browser также
GBA_REQUIRE_BROWSER=1. Подключение/пароль только в памяти дочернего процесса;
не выводились и не сохранены в Git. Node 24.18.0 первым в PATH, Python 3.14.6.
Пакетные версии, точные argv, JUnit counts, SHA256 и наблюдения — в
[INDEPENDENT_REVIEW_2_CHECKS.json](INDEPENDENT_REVIEW_2_CHECKS.json).

| Прогон | Результат |
|---|---|
| quota-reproduction | FAIL: 3 failed / 10.70s; ожидаемые отрицательные проверки реального дефекта |
| focused, восемь штатных файлов | PASS: 86 passed / 104.38s |
| browser-baseline, без изменений тестов | PASS: 1 passed / 150.78s; три фазы × desktop/mobile |
| browser-timezone-companywide, временная фикстура | PASS: 1 passed / 149.74s; три фазы × desktop/mobile; location day != UTC day |
| browser-human-reason, временная проверка текста | FAIL: 1 failed / 72.26s; desktop, последующие случаи не засчитываются |
| privacy-lifecycle-probes | FAIL: 1 failed, 2 passed / 7.99s; R2-1 red, expiry и сохранённая причина green |
| Ruff check, format, mypy после восстановления проб | PASS: exit 0; format/mypy 264 файла |
| Web typecheck/lint/format/unit/build | PASS: exit 0; unit 102, build 23 страницы |
| Production npm audit --omit=dev --json | FAIL: exit 1, 2 high (next, source-map-js), унаследовано |

Ни один отрицательный тест не заменён успешным. Product source не менялся;
следовательно, исправление R2-1/R2-2/R2-3 и новый зелёный результат не заявляются.

Точные команды текущего исполнителя (длительность здесь — внешнего процесса,
поэтому отличается от времени, напечатанного pytest):

| ID | argv | Итог |
|---|---|---|
| web-build | `"C:\Program Files\nodejs\npm.cmd" run build` | exit 0; 14.98 s |
| quota-reproduction | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m pytest -p no:cacheprovider --basetemp C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\quota-reproduction-tmp -q -s --tb=short --junitxml=C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\quota-reproduction.xml tests/integration/test_review2_repro.py` | exit 1; 12.56 s |
| focused | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m pytest -p no:cacheprovider --basetemp C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\focused-tmp -q -s --tb=short --junitxml=C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\focused.xml tests/integration/test_workforce_review_fixes.py tests/integration/test_workforce_visibility.py tests/integration/test_workforce_desk.py tests/integration/test_workforce_desk_races.py tests/unit/test_workforce_desk_contracts.py tests/integration/test_timesheets.py tests/integration/test_timesheet_guards.py tests/integration/test_shift_changes.py` | exit 0; 105.66 s |
| browser-baseline | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m pytest -p no:cacheprovider --basetemp C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\browser-baseline-tmp -q -s --tb=short --junitxml=C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\browser-baseline.xml tests/integration/test_i4_browser.py` | exit 0; 152.09 s |
| browser-timezone-companywide | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m pytest -p no:cacheprovider --basetemp C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\browser-timezone-companywide-tmp -q -s --tb=short --junitxml=C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\browser-timezone-companywide.xml tests/integration/test_i4_browser.py` | exit 0; 151.18 s |
| browser-human-reason | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m pytest -p no:cacheprovider --basetemp C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\browser-human-reason-tmp -q -s --tb=short --junitxml=C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\browser-human-reason.xml tests/integration/test_i4_browser.py` | exit 1; 73.3 s |
| ruff-check | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m ruff check src tests` | exit 0; 0.24 s |
| ruff-format | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m ruff format --check src tests` | exit 0; 0.17 s |
| mypy | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m mypy src tests` | exit 0; 18.42 s |
| web-typecheck | `"C:\Program Files\nodejs\npm.cmd" run typecheck` | exit 0; 7.67 s |
| web-lint | `"C:\Program Files\nodejs\npm.cmd" run lint` | exit 0; 19.62 s |
| web-format | `"C:\Program Files\nodejs\npm.cmd" run format:check` | exit 0; 2.9 s |
| web-unit | `"C:\Program Files\nodejs\npm.cmd" run test:unit` | exit 0; 3.31 s |
| web-audit | `"C:\Program Files\nodejs\npm.cmd" audit --omit=dev --json` | exit 1; 1.59 s |
| privacy-lifecycle-probes | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m pytest -p no:cacheprovider --basetemp C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\privacy-lifecycle-tmp -q -s --tb=short --junitxml=C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i4-review2-20261012-0356eb5\privacy-lifecycle.xml tests/integration/test_review2_privacy.py` | exit 1; 9.8 s |

Процессы запускали private run_review.py и затем run_privacy.py из
C:/Users/alexa/AppData/Local/GorgonaBookingTests/i4-review2-20261012-0356eb5.
MSIX перенаправляет LocalAppData в LocalCache; точные разрешённые пути — в JSON.
Временные api/tests/integration/test_review2_repro.py и test_review2_privacy.py
удалены из рабочей копии после сохранения их копий вне Git. Исходные байты
test_i4_browser.py и workforce.spec.ts восстановлены. До записи обзора Git status
чист, все 16 рабочих файлов совпали с Git blobs. Роль owner использована только
для допустимой подготовки фикстур/барьера своего кластера; HTTP остаётся обычным
авторизованным приложением. Данные — явно FAKE, не данные клиентов.

## NOT TESTED и решения владельца

- Полный pytest не запускался повторно в этом обзоре; свежий полный прогон
  предыдущей подготовки приёмки остаётся отдельным доказательством, а не нашим
  новым результатом. Он не содержит новых отрицательных проб и не опровергает их.
- Новые R2-1/R2-2/R2-3 не исправлены и не перепроверены после исправления.
- Целевые browser-ситуации F2, F6/N2; default My shifts при UTC≠local;
  смена Privacy с потерей ответа, 5xx/unreadable recovery, длинные/страничные
  списки, >20 версий/запросов, смена часов внутри смены, настоящий screen reader.
- В отрицательной пробе R2-3 не выполнены mobile и последующие фазы;
  History для совпадающей человеческой причины подтверждён чтением.
- Новые прямые пробы delegate/support по каждому тонкому маршруту не добавлялись;
  общий _access прочитан, штатные права/изоляция в focused проходят.
- Containers локально, external tenant site, HawkScan, load/soak, deployment,
  production, Azure/providers/funds/credentials не выполнялись. CI c6b8e34 PASS
  прочитан, но CI нового локального коммита обзора NOT TESTED.
- npm ci сообщил 7 high во всём дереве зависимостей; production-only аудит —
  отдельно 2 high. Никакого npm audit fix/update не выполнялось.

План/ADR-0025, принятие пакета, WORK-01/CORE-04, видимость по умолчанию компании,
даты чтения смен, срок отменённого ключа и роль в directory остаются решениями
владельца. Новый обмен при скрытой настройке нельзя считать защищённым, пока
R2-1 не закрыт. I-09 и I-12 в текущем плане FAIL с учётом новых проб; сохранённые
исторические C1-числа обозначают только случаи того прогона. Публикация любых
новых веток/PR, merge и production-действия по-прежнему не разрешены.

## Проверки документов

Своя validate_review_docs.py через тот же Python: **PASS, exit 0: 7 UTF-8 файлов,
6 Markdown/1 JSON, 179 существующих локальных ссылок, 16 исходных SHA256,
3 находки и все 5 отрицательных падений сохранены; runtime changes 0;
git diff --check от базы 0356eb5 exit 0; оба своих postmaster.pid отсутствуют.**
Ограниченная проверка plaintext DSN/private-key patterns: 0 совпадений, не полный
аудит безопасности. Весь конечный diff и классификация read/run/NOT TESTED
проверены. Эти проверки повторяются после последней записи и локального коммита.
Коммит документа читать из Git: документ не может записать собственный SHA.
