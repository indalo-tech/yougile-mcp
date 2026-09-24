# YouGile MCP

[![Release](https://img.shields.io/github/v/release/indalo-tech/yougile-mcp?label=release)](https://github.com/indalo-tech/yougile-mcp/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/yougile-mcp)](https://pypi.org/project/yougile-mcp/)
[![CI](https://github.com/indalo-tech/yougile-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/indalo-tech/yougile-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[Русский](#русский) · [English](#english) · [Changelog](CHANGELOG.md)

MCP server for [YouGile](https://ru.yougile.com) · MCP-сервер для YouGile

---

## Русский

MCP-сервер, через который Claude и другие AI-ассистенты работают с YouGile вашей компании:
задачами, досками, колонками, чатами, сотрудниками, стикерами. Основа — официальный REST API v2.

### Возможности

- **Работа с задачами по-человечески.** Названия досок и колонок, имена исполнителей, номера
  задач и даты вместо UUID и меток времени. Перенос карточки сам проходит цепочку Workflow.
- **Весь API.** 65 операций в 10 доменных инструментах плюс справочный `yougile_help`.
- **Задачи по номеру.** Сквозной `ID-123` или проектный `DEV-12`.
- **Готовые сценарии.** Стендап, отчёт по часам, разбор очереди — одной командой.
- **Общий лимит запросов.** YouGile пропускает 50 запросов в минуту на всю компанию, включая
  тех, кто работает в интерфейсе. Сервер держит лимит сам: один счётчик на все сессии,
  запущенные на компьютере. При ответе 429 все сессии ждут вместе.
- **Ответы по размеру.** Слишком большой ответ (тысяча задач, длинная переписка) урезается
  аккуратно: хвост списков и длинные тексты, с пометкой, что показано и как сузить запрос.
- **Права поверх прав YouGile.** Можно ограничить сессию чтением, выбранными проектами, запретить
  отдельные операции, требовать подтверждения человека перед записью в проекты, которые видят
  клиенты.
- **Безопасные повторы.** При сбое сети повторяются только запросы, которые нельзя выполнить
  дважды по ошибке: чтение, изменение и создание с ключом идемпотентности. Ключ идемпотентности
  сервер добавляет сам.
- **Ключ — только из переменной окружения.** Он не попадает ни в файлы настроек, ни в модель.
  Эндпоинты входа по логину и паролю модели недоступны.

> **Без установки:** добавьте в AI-клиенте удалённый MCP-сервер `https://yougile.indalo.ru/mcp`
> и войдите логином YouGile. Администраторы компании настраивают права сотрудников на
> [yougile.indalo.ru/admin](https://yougile.indalo.ru/admin). Код сервера —
> [yougile-mcp-cloud](https://github.com/indalo-tech/yougile-mcp-cloud).

### Быстрый старт

Нужен [uv](https://docs.astral.sh/uv/getting-started/installation/) — он сам поставит Python.
Пакет опубликован на [PyPI](https://pypi.org/project/yougile-mcp/), `uvx` скачает его сам.

**1. Получите ключ API**

```bash
uvx yougile-mcp setup
```

Команда спросит логин и пароль YouGile. Они используются только для запроса к YouGile и нигде
не сохраняются. Если у вас несколько компаний, выберите нужную. Если для компании уже есть ключ,
команда предложит взять его: YouGile разрешает не больше 30 ключей на аккаунт. В конце она
покажет ключ и готовые строки подключения.

Ключ действует с вашими правами в YouGile. Храните его как пароль.

**2. Подключите**

Claude Code, для всех проектов пользователя:

```bash
claude mcp add yougile --scope user -e YOUGILE_API_KEY=ваш_ключ -- uvx yougile-mcp
```

Claude Desktop, Cursor и другие клиенты — запись в `mcpServers`:

```json
{
  "mcpServers": {
    "yougile": {
      "command": "uvx",
      "args": ["yougile-mcp"],
      "env": { "YOUGILE_API_KEY": "ваш_ключ" }
    }
  }
}
```

**3. Проверьте**

```bash
YOUGILE_API_KEY=ваш_ключ uvx yougile-mcp check
```

Покажет версию, пользователя и компанию, сколько проектов, досок и колонок видно, действующие
права, часовой пояс и найденные файлы настроек. Проверка тратит 5 запросов.

### Инструменты для задач

Принимают названия и номера, показывают имена и даты. Для повседневной работы начинайте с них.

| инструмент | что умеет |
|---|---|
| `yougile_overview` | проекты → доски → колонки в порядке экрана, цепочки Workflow, умолчания и права |
| `yougile_find_tasks` | поиск по проекту, доске, колонке, исполнителю (имя, почта или `me`), словам из названия или номеру; по умолчанию только открытые. Выполненные за период — `completed_since` / `completed_until`; у выполненных видно время выполнения, у просроченных — `overdue` |
| `yougile_task` | карточка: где лежит, исполнители, срок, часы, чек-листы, стикеры по названиям (стикеры типов, которых нет в API, — числа, свободный текст — отдельно по id), описание, последние сообщения |
| `yougile_create_task` | создать: доска и колонка по названию, исполнители по имени или почте, срок датой, план часов, чек-лист, цвет |
| `yougile_update_task` | изменить поля, выполнить, архивировать, добавить или снять исполнителей, отметить пункты чек-листа, убрать срок |
| `yougile_move_task` | перенести в другую колонку; на досках с Workflow проходит все промежуточные колонки |
| `yougile_log_time` | прибавить часы к факту, не трогая план |
| `yougile_task_chat` | последние сообщения с именами авторов, отправка сообщения |
| `yougile_attach_file` | прикрепить файл к задаче: загрузить в YouGile и отправить в чат задачи вложением, можно с комментарием; файл — путь на этом компьютере (локальный сервер) или содержимое в base64 |
| `yougile_use_board` | запомнить доску, с которой вы работаете: дальше задачи создаются там без указания доски |

Даты пишутся как `2026-09-30` или `30.09.2026`, со временем — `2026-09-30 18:00`. Дата без
времени сохраняется как полночь по часовому поясу компании — так же, как в интерфейсе YouGile.

### Готовые сценарии

Промпты MCP: клиент показывает их как готовые команды. В Claude Code это
`/mcp__yougile__standup` и т. п.; в других клиентах — в меню подключённого сервера, если клиент
поддерживает промпты. Сценарий только пишет задание модели, работает она обычными инструментами —
с теми же правами и лимитами.

| промпт | что получится | параметры |
|---|---|---|
| `standup` | стендап: что сделано с прошлого рабочего дня, что в работе, блокеры и просрочка | `person` (по умолчанию вы), `project` |
| `hours_report` | план и факт часов по задачам, выполненным за период, — по проектам и людям, перерасход, задачи без оценки; отдельно открытые задачи со списанными часами | `since`, `until` (по умолчанию эта неделя), `project`, `person` |
| `triage` | разбор очереди: задачи без исполнителя, срока или оценки, просроченные, загрузка людей и предложения; изменения — только после вашего согласия | `board`, `column`, `project` |

YouGile хранит часы только суммой по задаче, без дат списания, поэтому отчёт «за период» строится
по задачам, выполненным в этот период.

Параметры дополняются, если клиент это умеет: сотрудники, проекты, доски («Проект / Доска»),
колонки выбранной доски и удобные даты периода. Проекты вне разрешённых правами не предлагаются.

### Экраны (MCP Apps)

Клиенты, которые умеют рисовать интерфейс внутри чата (MCP Apps), получают экраны: модель
открывает их, когда вы хотите посмотреть задачи или поработать с задачей, а кнопки на экране
работают без запроса к модели.

| экран | что на нём |
|---|---|
| `yougile_show_tasks` | таблица задач с поиском и сортировкой (фильтры как у `yougile_find_tasks`); строка открывает карточку, кнопка «Обновить»; «Развернуть» — на всё окно, если клиент это умеет |
| `yougile_show_task` | карточка задачи: статус, исполнители, срок, часы, чек-лист, описание, чат; кнопки «Выполнено», «Взять себе», перенос в колонку (по цепочке Workflow), отметки чек-листа, списание часов, сообщение в чат |
| `yougile_show_board` | доска: колонки рядом с карточками задач, фильтр по исполнителю, стрелки ← → для переноса в соседнюю колонку, карточка по клику |
| `yougile_new_task_form` | форма новой задачи: доска, колонка, название, описание, исполнитель, срок, план часов, чек-лист; модель заполняет, что знает, вы проверяете и создаёте кнопкой |
| `yougile_show_standup` | стендап: метрики, «Вчера», «Сегодня — в работе», «Блокеры и риски», «Дальше по очереди» и готовый текст; кнопка «Отправить в чат» передаёт его в разговор |
| `yougile_show_hours` | часы за период: план и факт графиками по людям и проектам, перерасход, выполненные без плана, открытые со списанными часами; период меняется на экране |
| `yougile_show_triage` | разбор очереди: у каждой задачи — проблемы (нет исполнителя, срока, плана, просрочена), правка исполнителя, срока и плана прямо в строке, загрузка людей на доске |
| `yougile_attach_files` | файлы в задачу: перетащите файлы (до 10, каждый до 10 МБ), добавьте комментарий — они загрузятся в YouGile и появятся в чате задачи вложениями |

Кнопки действуют с правами сессии, кнопок без прав нет. Нажатие — это ваше подтверждение: запись
в проект из `confirm_projects` проходит без повторного вопроса, а на карточке такого проекта
написано, что его видят клиенты. Модель получает те же данные текстом.

Экраны ставятся дополнением `apps` (Prefab UI):

```bash
claude mcp add yougile --scope user -e YOUGILE_API_KEY=ваш_ключ -- uvx "yougile-mcp[apps]"
```

Клиентам без MCP Apps (например, Claude Code) экраны и их кнопки не показываются.

### Доменные инструменты — весь API

| инструмент | что умеет |
|---|---|
| `yougile_tasks` | список и поиск (по колонке, исполнителям, стикеру, названию), открыть, создать, изменить: перенос, выполнение, архив, срок, план и факт часов, чек-листы, стикеры, удаление; подписчики чата задачи |
| `yougile_chats` | история, отправка, правка и удаление сообщений в чатах задач (id чата = id задачи) и групповых чатах; управление групповыми чатами |
| `yougile_boards` | доски: список, открыть, создать, переименовать, перенести, удалить |
| `yougile_columns` | колонки: список, открыть, создать, изменить, удалить |
| `yougile_projects` | проекты и участники, роли проекта |
| `yougile_users` | сотрудники и отделы: список, приглашение, изменение, удаление из компании |
| `yougile_stickers` | стикеры с набором состояний, стикеры спринтов и их состояния |
| `yougile_company` | данные компании, вебхуки |
| `yougile_files` | загрузка файла (по пути или в base64), возвращает ссылку |
| `yougile_crm` | контактные лица, поиск контакта по внешнему id |
| `yougile_help` | поля, типы, обязательность и примеры для любой операции |

Каждый доменный инструмент принимает `operation` (список допустимых значений есть в схеме)
и один плоский объект `params`, где вместе лежат параметры пути, запроса и тела:

```json
{ "operation": "update", "params": { "id": "ID-123", "completed": true } }
```

### Настройки репозитория и пользователя

Сервер ищет `.yougile.json` вверх от текущей папки (обычно это корень репозитория) и общий
файл `~/.yougile-mcp.json`. Настройки репозитория перекрывают общие. Путь к файлу можно задать
явно через `YOUGILE_CONFIG`.

```json
{
  "project": "Разработка",
  "board": "Бэкенд",
  "role": "member",
  "projects": ["Разработка"],
  "confirm_projects": ["Клиенты"],
  "deny": ["tasks.delete", "users.*"],
  "workflows": {
    "Клиенты / Сайт": ["Очередь", "В работе", "На проверке", "Готово"]
  },
  "done_columns": ["Готово"],
  "timezone": "Europe/Moscow",
  "instructions": "В задачах клиентских проектов пишите клиентским языком."
}
```

| поле | смысл |
|---|---|
| `project`, `board` | значения по умолчанию: где искать и куда создавать задачи |
| `role` | `reader` — только чтение; `member` — плюс задачи, сообщения, файлы; `admin` (по умолчанию) — всё, включая проекты, доски, колонки, сотрудников, роли и вебхуки |
| `projects` | работать только с этими проектами (названия или id). Чужие объекты скрыты из списков, запись в них запрещена |
| `confirm_projects` | запись в эти проекты — только после подтверждения человеком |
| `deny` | запрещённые операции, можно маской: `users.*`. Удаление через `deleted: true` считается отдельной операцией `<инструмент>.delete`, например `tasks.delete` |
| `workflows` | цепочки колонок для досок с расширением Workflow: YouGile не отдаёт их по API. Ключ — `"Проект / Доска"`. Первая колонка цепочки — колонка по умолчанию для новых задач |
| `done_columns` | колонки, которые означают «сделано», даже если задача не отмечена выполненной: название для всех досок (`"Готово"`) или `"Проект / Доска / Колонка"`. Такие задачи не считаются открытыми и просроченными; перенося задачу туда, сервер отмечает её выполненной, чтобы YouGile запомнил дату, а перенося обратно — снимает отметку |
| `timezone` | часовой пояс компании для дат, по умолчанию `Europe/Moscow` |
| `instructions` | правила вашей компании для модели, строка или список строк |

Эти права только сужают права YouGile: ключ всегда действует с правами пользователя,
который его выпустил. Модель видит только то, что права разрешают: читателю не показываются
инструменты записи, а инструменты разделов API перечисляют лишь разрешённые операции.

**Как работает подтверждение.** Если клиент умеет показывать запросы пользователю
(MCP elicitation), человек подтверждает запись в окне клиента, и модель не может обойти этот
шаг. Одно действие спрашивает подтверждение один раз, даже если делает несколько записей.
Если клиент так не умеет, инструмент возвращает `confirmation_required` с текстом того, что
будет записано. Модель должна показать его пользователю и повторить вызов с `confirm=true`
только после его явного согласия.

**Неоднозначные названия.** Если под название подходит несколько досок, проектов, колонок или
сотрудников («Сайт» есть в двух проектах, «Иван» — это двое), клиент с MCP elicitation
показывает человеку варианты, и действие продолжается с выбранным. Без elicitation инструмент
возвращает ошибку со списком вариантов, чтобы модель уточнила у пользователя.

### Переменные окружения

| переменная | по умолчанию | назначение |
|---|---|---|
| `YOUGILE_API_KEY` | — | ключ API, обязателен для работы сервера |
| `YOUGILE_BASE_URL` | `https://ru.yougile.com` | адрес YouGile, например вашего коробочного сервера |
| `YOUGILE_RATE_LIMIT` | `45` | запросов в минуту на один ключ; `0` отключает ограничитель |
| `YOUGILE_TIMEZONE` | `Europe/Moscow` | часовой пояс компании, перекрывает `timezone` из файла |
| `YOUGILE_CONFIG` | — | явный путь к файлу настроек вместо поиска `.yougile.json` |
| `YOUGILE_MCP_STATE_DIR` | папка кэша ОС | где лежит общий счётчик лимита |
| `YOUGILE_MCP_LOG_LEVEL` | `WARNING` | уровень логов; логи идут в stderr |

### Советы

- Структура компании (проекты, доски, колонки, сотрудники, стикеры) кэшируется на 5 минут —
  повторные вызовы не тратят лимит.
- В доменных инструментах чек-листы и стикеры при изменении задачи заменяются целиком;
  `yougile_update_task` делает это сам.
- Удалённые объекты скрыты из списков; чтобы их найти, добавьте `includeDeleted: true`.
- Списки отдают до 50 объектов, можно до 1000 через `limit`. Одним большим запросом лимит
  расходуется бережнее, чем многими маленькими.

### Версии

- Актуальная версия — на бейдже вверху и на странице
  [Releases](https://github.com/indalo-tech/yougile-mcp/releases/latest); что изменилось —
  в [CHANGELOG.md](CHANGELOG.md).
- Установленную версию показывают `yougile-mcp --version` и `yougile-mcp check`.
- Номера по [SemVer](https://semver.org/lang/ru/): до 1.0 новые возможности поднимают вторую
  цифру, исправления — третью.
- Поставить конкретную версию: `uvx yougile-mcp@0.5.0`. Последнюю, минуя кэш uv:
  `uvx yougile-mcp@latest`.

### Как это устроено

Каталог операций собран из официальной спецификации YouGile (`https://ru.yougile.com/api-json`),
её снимок лежит в пакете. Каждая операция отнесена к инструменту и уровню доступа: `read`,
`write` или `admin`. Инструменты для задач вызывают те же операции, поэтому права и
подтверждения действуют одинаково. Тесты не дадут выпустить версию, в которой новая операция
API осталась без инструмента, а CI каждый раз сверяет снимок с опубликованной спецификацией.

### Разработка

```bash
uv sync
uv run pytest
uv run ruff check src tests scripts
uv run --no-project python scripts/sync_spec.py   # обновить снимок спецификации
```

Запуск по HTTP для отладки: `uv run yougile-mcp serve --transport http --port 8000`.

**Выпуск версии.** Поменяйте `__version__` в `src/yougile_mcp/__init__.py`, перенесите записи
из `[Unreleased]` в новый раздел `CHANGELOG.md` (на двух языках), закоммитьте и отправьте тег:
`git tag v0.3.0 && git push origin v0.3.0`. Workflow проверит, что тег совпадает с версией,
прогонит тесты, соберёт пакет и опубликует GitHub Release с описанием из `CHANGELOG.md`
и пакет на PyPI.

**PyPI** получает пакет через Trusted Publishing — токенов нет: PyPI доверяет только workflow
`release.yml` этого репозитория в environment `pypi`. Публикацию выключает переменная
репозитория `PUBLISH_PYPI` (не `true`). Уже выпущенный тег можно отправить повторно через
Actions → Release → Run workflow.

### Участники

- [Hovhannes Mirzoyan](https://github.com/hovhannes-mirzoyan)
- [Artashes Mirzoyan](https://github.com/AMirzoian)

Проект развивает [Indalo](https://github.com/indalo-tech). Предложения и ошибки — в
[Issues](https://github.com/indalo-tech/yougile-mcp/issues).

### Лицензия

[MIT](LICENSE)

---

## English

An MCP server that lets Claude and other AI assistants work with your company's YouGile:
tasks, boards, columns, chats, employees and stickers, on top of the official REST API v2.

### Features

- **Task work in human terms.** Board and column names, assignee names, task numbers and
  dates instead of UUIDs and timestamps. Moving a card walks the Workflow chain by itself.
- **The whole API.** 65 operations in 10 domain tools, plus the `yougile_help` reference tool.
- **Tasks by number.** The company-wide `ID-123` or the project one like `DEV-12`.
- **Ready-made scenarios.** Stand-up, hours report, queue triage — one command each.
- **A shared rate limit.** YouGile allows 50 requests per minute per company, people in the
  web UI included. The server enforces the limit itself with one counter shared by every
  session running on the machine, and all of them back off together on HTTP 429.
- **Results that fit.** An oversized result (a thousand tasks, a long chat) is trimmed neatly:
  list tails and long texts go, with a note on what is shown and how to narrow the request.
- **Permissions on top of YouGile's.** Restrict a session to reading, to selected projects,
  deny specific operations, or require a human to confirm writes into projects your
  clients can see.
- **Safe retries.** After a network failure only requests that cannot be applied twice are
  retried: reads, updates, and creates carrying an idempotency key, which the server adds
  automatically.
- **The key comes from the environment only.** It never goes into config files or to the
  model. Login-and-password endpoints are not exposed to the model.

> **Nothing to install:** add the remote MCP server `https://yougile.indalo.ru/mcp` in your AI
> client and sign in with your YouGile login. Company admins set their people's rights at
> [yougile.indalo.ru/admin](https://yougile.indalo.ru/admin). Server code:
> [yougile-mcp-cloud](https://github.com/indalo-tech/yougile-mcp-cloud).

### Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/); it installs Python
for you. The package is on [PyPI](https://pypi.org/project/yougile-mcp/); `uvx` fetches it.

**1. Get an API key**

```bash
uvx yougile-mcp setup
```

It asks for your YouGile login and password. They are only used for the request to YouGile
and are never stored. If you belong to several companies, pick one. If the company already
has a key, the command offers to reuse it: YouGile allows at most 30 keys per account. At the
end it prints the key and ready-to-paste connection snippets.

The key acts with your YouGile rights. Keep it as secret as a password.

**2. Connect**

Claude Code, for all projects of the user:

```bash
claude mcp add yougile --scope user -e YOUGILE_API_KEY=your_key -- uvx yougile-mcp
```

Claude Desktop, Cursor and other clients — an `mcpServers` entry:

```json
{
  "mcpServers": {
    "yougile": {
      "command": "uvx",
      "args": ["yougile-mcp"],
      "env": { "YOUGILE_API_KEY": "your_key" }
    }
  }
}
```

**3. Check**

```bash
YOUGILE_API_KEY=your_key uvx yougile-mcp check
```

Shows the version, user and company, how many projects, boards and columns are visible, the
effective permissions, the time zone and the config files found. The check costs 5 requests.

### Task tools

They take names and numbers and show names and dates. Start with them for everyday work.

| tool | what it does |
|---|---|
| `yougile_overview` | projects → boards → columns in screen order, Workflow chains, defaults and permissions |
| `yougile_find_tasks` | search by project, board, column, assignee (name, email or `me`), title words or number; open tasks by default. Tasks completed in a period — `completed_since` / `completed_until`; completed tasks show when, overdue ones show `overdue` |
| `yougile_task` | the card: location, assignees, deadline, hours, checklists, stickers by name (sticker types the API does not describe — numbers, free text — separately, by id), description, latest messages |
| `yougile_create_task` | create: board and column by name, assignees by name or email, deadline as a date, planned hours, checklist, color |
| `yougile_update_task` | edit fields, complete, archive, add or remove assignees, check checklist items, remove the deadline |
| `yougile_move_task` | move to another column; on Workflow boards it passes every intermediate column |
| `yougile_log_time` | add worked hours, keeping the plan |
| `yougile_task_chat` | latest messages with author names, post a message |
| `yougile_attach_file` | attach a file to a task: upload it to YouGile and post it into the task's chat as an attachment, optionally with a comment; the file is a path on this computer (local server) or base64 content |
| `yougile_use_board` | remember the board you work on, so tasks go there without naming the board |

Dates are written as `2026-09-30` or `30.09.2026`, with time as `2026-09-30 18:00`. A date
without time is stored as midnight in the company time zone, just as the YouGile UI does.

### Ready-made scenarios

MCP prompts: clients show them as ready commands. In Claude Code they are
`/mcp__yougile__standup` and so on; other clients list them in the connected server's menu if
they support prompts. A scenario only writes the model's assignment; the model then works with
the regular tools, under the same permissions and limits. The texts are in Russian.

| prompt | what you get | parameters |
|---|---|---|
| `standup` | a stand-up: done since the previous working day, in progress, blockers and overdue tasks | `person` (you by default), `project` |
| `hours_report` | planned vs worked hours of tasks completed in a period, by project and person, overruns, tasks without estimates; open tasks with logged hours separately | `since`, `until` (this week by default), `project`, `person` |
| `triage` | queue triage: tasks without assignee, deadline or estimate, overdue ones, people's load and suggestions; changes only after your consent | `board`, `column`, `project` |

YouGile keeps only a task's total hours, not when they were logged, so a report "for a period"
is built from the tasks completed in that period.

Parameters are completed when the client supports it: people, projects, boards ("Project /
Board"), the chosen board's columns and handy period dates. Projects outside the permissions
are not offered.

### Screens (MCP Apps)

Clients that draw interfaces inside the chat (MCP Apps) get screens: the model opens one when
you want to look through tasks or work on a task, and the screen's buttons work without asking
the model.

| screen | what it shows |
|---|---|
| `yougile_show_tasks` | a task table with search and sorting (filters as in `yougile_find_tasks`); a row opens the card; a Refresh button; Expand for the whole window, if the client can |
| `yougile_show_task` | a task card: status, assignees, deadline, hours, checklist, description, chat; buttons to complete, take, move to a column (along the Workflow chain), tick checklist items, log hours and post to the chat |
| `yougile_show_board` | a board: columns side by side with task cards, a filter by assignee, ← → arrows to move a card to the neighbouring column, the card on click |
| `yougile_new_task_form` | a new-task form: board, column, title, description, assignee, deadline, planned hours, checklist; the model fills in what it knows, you check and create it with a button |
| `yougile_show_standup` | a stand-up: counts, done since the previous working day, in progress, blockers and risks, next in the queue, and a ready text; Send to chat passes it to the conversation |
| `yougile_show_hours` | hours for a period: planned vs worked as charts by person and project, overruns, completed without a plan, open with logged hours; the period changes on the screen |
| `yougile_show_triage` | queue triage: each task's problems (no assignee, deadline or plan, overdue), the assignee, deadline and plan edited right in the row, people's load on the board |
| `yougile_attach_files` | files for a task: drop files (up to 10, each up to 10 MB), add a comment, and they are uploaded to YouGile and appear in the task's chat as attachments |

Buttons act with the session's permissions, and buttons without them are not shown. A click is
your confirmation: a write into a project from `confirm_projects` goes ahead without asking
again, and the card of such a project says clients can see it. The model gets the same data as
text.

Screens come with the `apps` extra (Prefab UI):

```bash
claude mcp add yougile --scope user -e YOUGILE_API_KEY=your_key -- uvx "yougile-mcp[apps]"
```

Clients without MCP Apps (Claude Code, for one) are not shown the screens or their buttons.

### Domain tools — the whole API

| tool | what it does |
|---|---|
| `yougile_tasks` | list and search (by column, assignees, sticker, title), get, create, update: move, complete, archive, deadline, planned and worked hours, checklists, stickers, delete; task chat subscribers |
| `yougile_chats` | history, send, edit and delete messages in task chats (chat id = task id) and group chats; manage group chats |
| `yougile_boards` | boards: list, get, create, rename, move, delete |
| `yougile_columns` | columns: list, get, create, update, delete |
| `yougile_projects` | projects and their members, project roles |
| `yougile_users` | employees and departments: list, invite, update, remove from the company |
| `yougile_stickers` | state stickers, sprint stickers and their states |
| `yougile_company` | company details, webhooks |
| `yougile_files` | upload a file (by path or as base64); returns a URL |
| `yougile_crm` | contact persons, contact lookup by external id |
| `yougile_help` | fields, types, required flags and examples for any operation |

Every domain tool takes an `operation` (the allowed values are in its schema) and one flat
`params` object that holds path, query and body parameters together:

```json
{ "operation": "update", "params": { "id": "ID-123", "completed": true } }
```

### Repository and user config

The server looks for `.yougile.json` in the current directory and its parents (usually the
repository root), and for a shared `~/.yougile-mcp.json`. Repository settings override the
shared ones. `YOUGILE_CONFIG` points to a file explicitly.

```json
{
  "project": "Development",
  "board": "Backend",
  "role": "member",
  "projects": ["Development"],
  "confirm_projects": ["Clients"],
  "deny": ["tasks.delete", "users.*"],
  "workflows": {
    "Clients / Website": ["Queue", "In progress", "Review", "Done"]
  },
  "done_columns": ["Done"],
  "timezone": "Europe/Moscow",
  "instructions": "Use client-friendly language in client projects."
}
```

| field | meaning |
|---|---|
| `project`, `board` | defaults: where to search and where to create tasks |
| `role` | `reader` — read only; `member` — plus tasks, messages, files; `admin` (default) — everything, including projects, boards, columns, employees, roles and webhooks |
| `projects` | work only with these projects (names or ids). Other objects are hidden from lists and cannot be written |
| `confirm_projects` | writes into these projects need a human confirmation |
| `deny` | denied operations, masks allowed: `users.*`. Deleting via `deleted: true` counts as a separate `<tool>.delete` operation, e.g. `tasks.delete` |
| `workflows` | column chains for boards using the Workflow extension, which YouGile does not expose via the API. Key: `"Project / Board"`. The first column of a chain is the default for new tasks |
| `done_columns` | columns that mean "done" even when a task is not marked completed: a title for every board (`"Done"`) or `"Project / Board / Column"`. Such tasks are neither open nor overdue; moving a task there marks it completed so YouGile records the date, moving it back out reopens it |
| `timezone` | the company time zone for dates, default `Europe/Moscow` |
| `instructions` | your company's rules for the model, a string or a list of strings |

These permissions only narrow YouGile's own: the key always acts with the rights of the user
who issued it. The model sees only what the permissions allow: a reader is not shown the
writing tools, and the API domain tools list only the allowed operations.

**How confirmation works.** If the client can prompt the user (MCP elicitation), the person
confirms the write in the client's UI and the model cannot skip that step. One action asks
once, even when it performs several writes. Otherwise the tool returns `confirmation_required`
with exactly what would be written; the model has to show it to the user and repeat the call
with `confirm=true` only after explicit consent.

**Ambiguous names.** When a name fits several boards, projects, columns or people ("Site"
exists in two projects, there are two Ivans), a client with MCP elicitation shows the person the
options and the action goes on with the chosen one. Without elicitation the tool returns an
error listing the options, so the model asks the user.

### Environment variables

| variable | default | purpose |
|---|---|---|
| `YOUGILE_API_KEY` | — | API key, required to run the server |
| `YOUGILE_BASE_URL` | `https://ru.yougile.com` | YouGile address, e.g. your on-premise server |
| `YOUGILE_RATE_LIMIT` | `45` | requests per minute per key; `0` disables the limiter |
| `YOUGILE_TIMEZONE` | `Europe/Moscow` | company time zone, overrides `timezone` from the file |
| `YOUGILE_CONFIG` | — | explicit config file instead of looking for `.yougile.json` |
| `YOUGILE_MCP_STATE_DIR` | OS cache dir | where the shared rate-limit counter lives |
| `YOUGILE_MCP_LOG_LEVEL` | `WARNING` | log level; logs go to stderr |

### Tips

- The company structure (projects, boards, columns, employees, stickers) is cached for
  5 minutes, so repeated calls do not spend the limit.
- In domain tools checklists and stickers are replaced as a whole on update;
  `yougile_update_task` handles that for you.
- Deleted objects are hidden from lists; add `includeDeleted: true` to find them.
- Lists return up to 50 objects, up to 1000 with `limit`. One large request spends the limit
  more wisely than many small ones.

### Versions

- The current version is on the badge above and on the
  [Releases](https://github.com/indalo-tech/yougile-mcp/releases/latest) page; what changed is
  in [CHANGELOG.md](CHANGELOG.md).
- `yougile-mcp --version` and `yougile-mcp check` show the installed version.
- Numbers follow [SemVer](https://semver.org/): before 1.0, new features bump the second
  number and fixes the third.
- Install a specific version: `uvx yougile-mcp@0.5.0`; the newest one, bypassing uv's cache:
  `uvx yougile-mcp@latest`.

### How it works

The operation catalog is built from YouGile's official spec (`https://ru.yougile.com/api-json`);
a snapshot ships with the package. Each operation is mapped to a tool and an access level:
`read`, `write` or `admin`. Task tools call the same operations, so permissions and
confirmations apply identically. Tests refuse a release in which a new API operation is left
without a tool, and CI compares the snapshot with the published spec on every run.

### Development

```bash
uv sync
uv run pytest
uv run ruff check src tests scripts
uv run --no-project python scripts/sync_spec.py   # refresh the spec snapshot
```

HTTP transport for debugging: `uv run yougile-mcp serve --transport http --port 8000`.

**Releasing.** Bump `__version__` in `src/yougile_mcp/__init__.py`, move the `[Unreleased]`
entries into a new `CHANGELOG.md` section (in both languages), commit and push a tag:
`git tag v0.3.0 && git push origin v0.3.0`. The workflow checks that the tag matches the
version, runs the tests, builds the package and publishes a GitHub Release with the notes from
`CHANGELOG.md` and the package on PyPI.

**PyPI** receives the package via Trusted Publishing — there are no tokens: PyPI trusts only
this repository's `release.yml` workflow in the `pypi` environment. The repository variable
`PUBLISH_PYPI` (anything but `true`) turns publishing off. An already released tag can be
published again via Actions → Release → Run workflow.

### Contributors

- [Hovhannes Mirzoyan](https://github.com/hovhannes-mirzoyan)
- [Artashes Mirzoyan](https://github.com/AMirzoian)

Maintained by [Indalo](https://github.com/indalo-tech). Ideas and bugs go to
[Issues](https://github.com/indalo-tech/yougile-mcp/issues).

### License

[MIT](LICENSE)
