# YouGile MCP

[Русский](#русский) · [English](#english)

MCP server for [YouGile](https://ru.yougile.com) · MCP-сервер для YouGile

---

## Русский

MCP-сервер, через который Claude и другие AI-ассистенты работают с YouGile вашей компании:
задачами, досками, колонками, чатами, сотрудниками, стикерами. Основа — официальный REST API v2.

### Возможности

- **Весь API.** 65 операций в 10 инструментах плюс справочный `yougile_help`.
- **Задачи по номеру.** Можно писать сквозной `ID-123` или проектный `DEV-12` вместо UUID.
- **Общий лимит запросов.** YouGile пропускает 50 запросов в минуту на всю компанию, включая
  тех, кто работает в интерфейсе. Сервер держит лимит сам: один счётчик на все сессии,
  запущенные на компьютере. При ответе 429 все сессии ждут вместе.
- **Права поверх прав YouGile.** Можно ограничить сессию чтением, выбранными проектами, запретить
  отдельные операции, требовать подтверждения человека перед записью в проекты, которые видят
  клиенты.
- **Безопасные повторы.** При сбое сети повторяются только запросы, которые нельзя выполнить
  дважды по ошибке: чтение, изменение и создание с ключом идемпотентности. Ключ идемпотентности
  сервер добавляет сам.
- **Ключ — только из переменной окружения.** Он не попадает ни в файлы настроек, ни в модель.
  Эндпоинты входа по логину и паролю модели недоступны.

> **Серверная версия** — подключение по адресу, без установки, вход через логин YouGile — готовится.
> Адрес появится здесь.

### Быстрый старт

Нужен [uv](https://docs.astral.sh/uv/getting-started/installation/) — он сам поставит Python.

> Пока пакет не опубликован на PyPI, вместо `uvx yougile-mcp` пишите
> `uvx --from git+https://github.com/indalo-tech/yougile-mcp yougile-mcp`.

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

Покажет пользователя и компанию, сколько проектов, досок и колонок видно, действующие права
и найденные файлы настроек. Проверка тратит 5 запросов.

### Инструменты

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
  "instructions": "В задачах клиентских проектов пишите клиентским языком."
}
```

| поле | смысл |
|---|---|
| `project`, `board` | значения по умолчанию, сообщаются модели |
| `role` | `reader` — только чтение; `member` — плюс задачи, сообщения, файлы; `admin` (по умолчанию) — всё, включая проекты, доски, колонки, сотрудников, роли и вебхуки |
| `projects` | работать только с этими проектами (названия или id). Чужие объекты скрыты из списков, запись в них запрещена |
| `confirm_projects` | запись в эти проекты — только после подтверждения человеком |
| `deny` | запрещённые операции, можно маской: `users.*`. Удаление через `deleted: true` считается отдельной операцией `<инструмент>.delete`, например `tasks.delete` |
| `instructions` | правила вашей компании для модели, строка или список строк |

Эти права только сужают права YouGile: ключ всегда действует с правами пользователя,
который его выпустил.

**Как работает подтверждение.** Если клиент умеет показывать запросы пользователю
(MCP elicitation), человек подтверждает запись в окне клиента, и модель не может обойти этот
шаг. Если клиент так не умеет, инструмент возвращает `confirmation_required` с текстом того, что
будет записано. Модель должна показать его пользователю и повторить вызов с `confirm=true`
только после его явного согласия.

### Переменные окружения

| переменная | по умолчанию | назначение |
|---|---|---|
| `YOUGILE_API_KEY` | — | ключ API, обязателен для работы сервера |
| `YOUGILE_BASE_URL` | `https://ru.yougile.com` | адрес YouGile, например вашего коробочного сервера |
| `YOUGILE_RATE_LIMIT` | `45` | запросов в минуту на один ключ; `0` отключает ограничитель |
| `YOUGILE_CONFIG` | — | явный путь к файлу настроек вместо поиска `.yougile.json` |
| `YOUGILE_MCP_STATE_DIR` | папка кэша ОС | где лежит общий счётчик лимита |
| `YOUGILE_MCP_LOG_LEVEL` | `WARNING` | уровень логов; логи идут в stderr |

### Советы

- Чек-листы и стикеры при изменении задачи заменяются целиком: прочитайте задачу, поправьте,
  запишите обратно.
- Сроки передаются в миллисекундах Unix, часы `timeTracking` — в часах.
- Удалённые объекты скрыты из списков; чтобы их найти, добавьте `includeDeleted: true`.
- Списки отдают до 50 объектов, можно до 1000 через `limit`. Одним большим запросом лимит
  расходуется бережнее, чем многими маленькими.

### Как это устроено

Каталог операций собран из официальной спецификации YouGile (`https://ru.yougile.com/api-json`),
её снимок лежит в пакете. Каждая операция отнесена к инструменту и уровню доступа: `read`,
`write` или `admin`. Тесты не дадут выпустить версию, в которой новая операция API осталась
без инструмента, а CI каждый раз сверяет снимок с опубликованной спецификацией.

### Разработка

```bash
uv sync
uv run pytest
uv run ruff check src tests scripts
uv run --no-project python scripts/sync_spec.py   # обновить снимок спецификации
```

Запуск по HTTP для отладки: `uv run yougile-mcp serve --transport http --port 8000`.

### Лицензия

[MIT](LICENSE)

---

## English

An MCP server that lets Claude and other AI assistants work with your company's YouGile:
tasks, boards, columns, chats, employees and stickers, on top of the official REST API v2.

### Features

- **The whole API.** 65 operations in 10 tools, plus the `yougile_help` reference tool.
- **Tasks by number.** Use the company-wide `ID-123` or the project one like `DEV-12`
  instead of UUIDs.
- **A shared rate limit.** YouGile allows 50 requests per minute per company, people in the
  web UI included. The server enforces the limit itself with one counter shared by every
  session running on the machine, and all of them back off together on HTTP 429.
- **Permissions on top of YouGile's.** Restrict a session to reading, to selected projects,
  deny specific operations, or require a human to confirm writes into projects your
  clients can see.
- **Safe retries.** After a network failure only requests that cannot be applied twice are
  retried: reads, updates, and creates carrying an idempotency key, which the server adds
  automatically.
- **The key comes from the environment only.** It never goes into config files or to the
  model. Login-and-password endpoints are not exposed to the model.

> **Hosted version** — connect by URL, nothing to install, sign in with your YouGile login —
> is in the works. The address will appear here.

### Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/); it installs Python
for you.

> Until the package is on PyPI, use
> `uvx --from git+https://github.com/indalo-tech/yougile-mcp yougile-mcp` instead of
> `uvx yougile-mcp`.

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

Shows the user and company, how many projects, boards and columns are visible, the effective
permissions and the config files found. The check costs 5 requests.

### Tools

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
  "instructions": "Use client-friendly language in client projects."
}
```

| field | meaning |
|---|---|
| `project`, `board` | defaults, passed on to the model |
| `role` | `reader` — read only; `member` — plus tasks, messages, files; `admin` (default) — everything, including projects, boards, columns, employees, roles and webhooks |
| `projects` | work only with these projects (names or ids). Other objects are hidden from lists and cannot be written |
| `confirm_projects` | writes into these projects need a human confirmation |
| `deny` | denied operations, masks allowed: `users.*`. Deleting via `deleted: true` counts as a separate `<tool>.delete` operation, e.g. `tasks.delete` |
| `instructions` | your company's rules for the model, a string or a list of strings |

These permissions only narrow YouGile's own: the key always acts with the rights of the user
who issued it.

**How confirmation works.** If the client can prompt the user (MCP elicitation), the person
confirms the write in the client's UI and the model cannot skip that step. Otherwise the tool
returns `confirmation_required` with exactly what would be written; the model has to show it
to the user and repeat the call with `confirm=true` only after explicit consent.

### Environment variables

| variable | default | purpose |
|---|---|---|
| `YOUGILE_API_KEY` | — | API key, required to run the server |
| `YOUGILE_BASE_URL` | `https://ru.yougile.com` | YouGile address, e.g. your on-premise server |
| `YOUGILE_RATE_LIMIT` | `45` | requests per minute per key; `0` disables the limiter |
| `YOUGILE_CONFIG` | — | explicit config file instead of looking for `.yougile.json` |
| `YOUGILE_MCP_STATE_DIR` | OS cache dir | where the shared rate-limit counter lives |
| `YOUGILE_MCP_LOG_LEVEL` | `WARNING` | log level; logs go to stderr |

### Tips

- Checklists and stickers are replaced as a whole on update: read the task, modify, write back.
- Deadlines are Unix timestamps in milliseconds; `timeTracking` values are hours.
- Deleted objects are hidden from lists; add `includeDeleted: true` to find them.
- Lists return up to 50 objects, up to 1000 with `limit`. One large request spends the limit
  more wisely than many small ones.

### How it works

The operation catalog is built from YouGile's official spec (`https://ru.yougile.com/api-json`);
a snapshot ships with the package. Each operation is mapped to a tool and an access level:
`read`, `write` or `admin`. Tests refuse a release in which a new API operation is left without
a tool, and CI compares the snapshot with the published spec on every run.

### Development

```bash
uv sync
uv run pytest
uv run ruff check src tests scripts
uv run --no-project python scripts/sync_spec.py   # refresh the spec snapshot
```

HTTP transport for debugging: `uv run yougile-mcp serve --transport http --port 8000`.

### License

[MIT](LICENSE)
