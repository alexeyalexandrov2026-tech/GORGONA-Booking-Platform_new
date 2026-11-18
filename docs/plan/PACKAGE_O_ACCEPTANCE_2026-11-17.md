# Package O — технические проверки 17 ноября 2026

**Техническая приёмка O-01–O-10 — PASS, 18 ноября 2026.**
Все 100 тестов пакета прошли локально. Полный CI `3ea5d28`
прошёл после изменения тестового переключателя Workforce.

Рабочая копия `C:/Users/alexa/.codex/worktrees/package-o8-customer-answer`,
ветка `codex/package-o-acceptance`. Производственный код
`dc9ee75dbfb2c3cac0f5b29774f309ec59fe5519`. Дополнительные проверки
конкурентных ответов — `b0807b80dbda8b39bbcb0616b2ddcdd883e0355c`.
Проверка Workforce в этой ветке использует отдельное HTTP-соединение
для каждого переключения тестового пользователя.

## Свежие локальные результаты

| Проверка | Наблюдаемый результат |
| --- | --- |
| Все 33 файла O1–O9 с дополнительными гонками, обязательные PostgreSQL 18.7 и Chromium | PASS на `c4a9c67` — 100 тестов, без пропусков, 539,46 с, exit 0 |
| Все 33 файла O1–O9 на `dc9ee75`, до дополнительных гонок | PASS — 97 тестов, без пропусков, 605,29 с, exit 0 |
| Ответ делегата одновременно со служебным отзывом изменения | PASS — наблюдается ожидание блокировки проекта, остаётся одно решение |
| Две приёмки с разными ключами | PASS — один ответ 200, один 409, одна строка приёмки |
| Две приёмки с одинаковым ключом | PASS — два равных ответа 200, одна строка приёмки |
| Два файла клиентских решений с дополнительными гонками | PASS — 5 тестов, 19,41 с, exit 0 |
| API unit | PASS — 878 тестов, 25,82 с, exit 0 |
| Web unit | PASS — 190 тестов, 3,2 с, exit 0 |
| Ruff, формат и mypy | PASS — 571 файл, exit 0 |
| Web typecheck, ESLint, Prettier | PASS — exit 0 |
| Статическая сборка Next.js 16.4.6 | PASS — 33 страницы, exit 0 |
| Workforce и клиентские сценарии после изменения тестового соединения | PASS — 7 pytest за 194,39 с, exit 0. Все шесть проверок Workforce и два операторских сценария прошли в Chromium |

API выполнялся на Windows с настоящим PostgreSQL Debian 18.7 в одноразовом
локальном окружении. Браузерные сценарии используют тестовый OIDC с PKCE
и настоящее приложение, авторизацию и БД. Проверки production и реального
провайдера идентификации в этот результат не входят.

## Сопоставление критериев

| Критерий | Локальное доказательство |
| --- | --- |
| O-01 | Запрет включения до приёмки, отказ записи при выключенном модуле, чтение истории в разрешённой области и SQL-ограничения ([O1](../../api/tests/integration/test_o1_construction_estimates.py)) |
| O-02 | Неизменяемые версии, замороженное предложение и производные суммы ([O1](../../api/tests/integration/test_o1_construction_estimates.py)) |
| O-03 | Приёмка фиксирует исходный договор, текущая сумма равна исходной плюс принятые изменения ([O2](../../api/tests/integration/test_o2_construction_contract.py)) |
| O-04 | Два одобрения или одобрение и отзыв оставляют один исход после наблюдаемого ожидания блокировки ([O2](../../api/tests/integration/test_o2_construction_contract.py), [O9](../../api/tests/integration/test_o9_customer_change_answer.py)) |
| O-05 | Бюджет, обязательства и затраты по строке и этапу. У источника одна действующая привязка, сторнирование создаёт отдельную запись ([бюджет](../../api/tests/integration/test_o3a_construction_budget.py), [затраты](../../api/tests/integration/test_o3b_construction_costs.py)) |
| O-06 | Выполненный объём учитывается накопительно и ограничен договором. Конкурирующее утверждение уменьшения объёма не может оставить договор ниже уже учтённого объёма ([O4a](../../api/tests/integration/test_o4a_construction_execution.py)) |
| O-07 | Заявка рассчитывает стоимость выполненных работ за вычетом ранее выставленного. FIN-03 хранит черновик счёта и отдельное начисление удержания. Предел задаёт договор, на период одна заявка даже при гонке ([O5](../../api/tests/integration/test_o5_construction_billing.py)) |
| O-08 | Удержание освобождается после приёмки, один раз на акт. Повтор и конкурентные операции сохраняют одну запись ([O6a](../../api/tests/integration/test_o6a_construction_acceptance.py), [сверка](../../api/tests/integration/test_o6b_construction_warranty.py)) |
| O-09 | Отдельное право утверждения, связь с компанией клиента и доступ через действующий grant. Проверены область филиала, ответ, квитанция и отзыв ([привязка](../../api/tests/integration/test_o8_construction_customer_company.py), [предложение](../../api/tests/integration/test_o8_construction_customer_answer.py), [изменение](../../api/tests/integration/test_o9_customer_change_answer.py), [приёмка](../../api/tests/integration/test_o9_customer_acceptance.py)) |
| O-10 | Desktop/mobile, axe и действия клавиатуры прошли локально. Полный [повторный CI](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44242186256) на `3ea5d28` завершился успешно после изменения тестового соединения Workforce |

Уточнение O-01 следует принятому
[ADR-0035](../adr/0035-construction-projects-and-estimates.md).
История остаётся доступной авторизованным пользователям при отключении
записей. Формулировка плана согласована с этим решением.

## CI и границы

На `98e1064555232ac879b3a2a4acdbe8a4b874614d` полный CI дал
2941 PASS, 1 skip за 2962,34 с. Экран изменения договора
`917989cb75cd77996f6179a919759eb2aedbbc24` также прошёл свой полный CI.
Эти результаты относятся к указанным коммитам.
[CI API](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44159227568)
[CI экрана](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44161313505)

Полный CI кода операторского доступа `dc9ee75` прошёл —
2946 PASS, 1 skip за 2889,48 с. Полные CI API и экрана клиентской
приёмки также прошли на своих коммитах.
[CI операторского доступа](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44169518012)
[CI API приёмки](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44163133942)
[CI экрана приёмки](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44165183998)

Первый полный CI ветки приёмки `a3c5884` завершился с 1 FAIL,
2948 PASS и 1 skip за 4218,19 с. В мобильной проверке Workforce
соединение закрылось при POST в локальный тестовый маршрут переключения
личности `/fixture/user/owner`. Запросы тестового переключателя теперь
передают `Connection: close`, чтобы исключить повторное использование
сокета из пула между переключениями.
[Первый CI ветки приёмки](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44172458415)

Повторный CI на `3ea5d289d06f242b0754e85b4d60f78d35d61c7b`,
задание `134592488370`, завершился 18 ноября в 06:23 UTC —
2949 PASS, 1 skip за 4194,42 с, exit 0. Единственный пропуск —
`test_tenant_site_embedding.py`, которому нужна настройка
`GBA_REQUIRE_TENANT_SITE=1` для проверки внешнего сайта.
Веб-сборка, образ, PostgreSQL 18, Ruff и mypy прошли в том же задании.
[Повторный CI ветки приёмки](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44242186256)

Независимые обзоры новых клиентских API и экранов выполнялись чтением
исходников. Выявленные замечания исправлены и покрыты проверками.
Reviewer отдельно тесты не запускал. Это ограниченные обзоры изменённых
путей. Решение о readiness остаётся за владельцем.

В полном аудите web dev-зависимостей остаются 15 находок — 6 moderate,
9 high. Аудит production-зависимостей после обновления Next.js прошёл.
BUILD-01 сохраняет planned. Технически подтверждены 13 из 28 сценариев,
все 39 отраслевых профилей остаются planned. Production, включение модуля
и merge не выполнялись.
