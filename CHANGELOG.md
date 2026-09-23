# Changelog · История изменений

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), номера версий —
[SemVer](https://semver.org/lang/ru/). Format: Keep a Changelog, versions follow SemVer.

## [Unreleased]

## [0.3.0] — 2026-09-23

### Русский

#### Добавлено
- Ядро можно встраивать в сервер для многих пользователей: `build_server()` принимает
  `auth`, `middleware` и любые параметры FastMCP (например `lifespan`), а окружение каждого
  запроса привязывается через ContextVar.
- Флаг `Runtime.allow_local_files`: на сервере загрузка файла по локальному пути запрещена,
  чтобы модель не могла выгрузить файлы самого сервера.
- `yougile_overview` возвращает правила компании (`company_rules`); инструкции сервера
  советуют начинать с него.

#### Изменено
- Пакет опубликован на PyPI: README ставит его через `uvx yougile-mcp`, конкретную версию —
  через `uvx yougile-mcp@<версия>`.

### English

#### Added
- The core can be embedded in a multi-user server: `build_server()` takes `auth`,
  `middleware` and any FastMCP option (e.g. `lifespan`); each request's runtime is bound
  through a ContextVar.
- `Runtime.allow_local_files`: hosted servers refuse uploads by local path, so a model cannot
  exfiltrate the server's own files.
- `yougile_overview` returns the company's rules (`company_rules`); the server instructions
  suggest calling it first.

#### Changed
- The package is on PyPI: README installs it with `uvx yougile-mcp`, a specific version with
  `uvx yougile-mcp@<version>`.

## [0.2.0] — 2026-09-23

### Русский

#### Добавлено
- Инструменты уровня задач — имена и номера вместо UUID, даты вместо меток времени:
  - `yougile_overview` — проекты, доски и колонки в порядке экрана, цепочки Workflow,
    умолчания и права сессии;
  - `yougile_find_tasks` — поиск по названиям проекта, доски и колонки, исполнителю
    (имя, почта или `me`), словам из названия или номеру; по умолчанию только открытые;
  - `yougile_task` — карточка: где лежит, исполнители по именам, срок датой, часы,
    чек-листы с отметками, стикеры по названиям, описание текстом, последние сообщения;
  - `yougile_create_task` — доска и колонка по названию, исполнители по имени или почте,
    срок и начало датой, план часов, чек-лист, цвет;
  - `yougile_update_task` — правка полей, выполнение, архив, добавление и снятие
    исполнителей, отметки и новые пункты чек-листа, снятие срока;
  - `yougile_move_task` — перенос с проходом по цепочке Workflow из `.yougile.json`,
    в обе стороны; без цепочки подсказывает, как её задать;
  - `yougile_log_time` — прибавить часы к факту, не трогая план;
  - `yougile_task_chat` — последние сообщения с именами авторов и отправка сообщения.
- Настройка `timezone` (и переменная `YOUGILE_TIMEZONE`), по умолчанию `Europe/Moscow`:
  дата без времени становится полуночью по часовому поясу компании, как в интерфейсе YouGile.
- Поле `workflows` в `.yougile.json` теперь используется при переносе и создании задач.
- Подтверждение записи в клиентский проект спрашивается один раз на действие, даже если
  действие делает несколько записей (перенос через несколько колонок).
- Версионирование: версия в одном месте, этот файл, выпуск GitHub Release по тегу `vX.Y.Z`
  и публикация на PyPI через Trusted Publishing, когда она включена.

#### Изменено
- Зависимость `tzdata` на Windows — там нет системной базы часовых поясов.

### English

#### Added
- Task-level tools — names and numbers instead of UUIDs, dates instead of timestamps:
  - `yougile_overview` — projects, boards and columns in screen order, Workflow chains,
    session defaults and permissions;
  - `yougile_find_tasks` — search by project, board and column names, assignee (name, email
    or `me`), title words or number; open tasks only by default;
  - `yougile_task` — the card: location, assignees by name, deadline as a date, hours,
    checklists with marks, stickers by name, description as text, latest messages;
  - `yougile_create_task` — board and column by name, assignees by name or email, deadline
    and start as dates, planned hours, checklist, color;
  - `yougile_update_task` — edit fields, complete, archive, add and remove assignees, check
    and add checklist items, remove the deadline;
  - `yougile_move_task` — moves along the Workflow chain from `.yougile.json`, both ways;
    without a chain it explains how to configure one;
  - `yougile_log_time` — add worked hours, keeping the plan;
  - `yougile_task_chat` — latest messages with author names, and posting a message.
- `timezone` setting (and `YOUGILE_TIMEZONE`), default `Europe/Moscow`: a date without time
  becomes midnight in the company time zone, as the YouGile UI stores it.
- The `workflows` field of `.yougile.json` is now used when moving and creating tasks.
- A confirmation for writing into a client-facing project is asked once per action, even when
  the action performs several writes (a move through several columns).
- Versioning: a single version source, this file, GitHub Releases from `vX.Y.Z` tags and
  PyPI publishing via Trusted Publishing once enabled.

#### Changed
- `tzdata` dependency on Windows, which has no system time zone database.

## [0.1.0] — 2026-09-23

### Русский

#### Добавлено
- Весь REST API v2 YouGile: 65 операций в 10 инструментах и `yougile_help`; каталог собран
  из официальной спецификации.
- Задачи по номеру: `ID-123` или `DEV-12` вместо UUID.
- Общий лимит на все сессии компьютера (45 в минуту на ключ), общая пауза при 429,
  повторы только безопасных запросов.
- Права поверх прав YouGile: роль, список проектов, запрет операций, подтверждение перед
  записью в клиентские проекты.
- Команды `setup`, `check`, `serve` (stdio / http).

### English

#### Added
- The whole YouGile REST API v2: 65 operations in 10 tools plus `yougile_help`; the catalog
  is built from the official spec.
- Tasks by number: `ID-123` or `DEV-12` instead of UUIDs.
- A rate limit shared by all sessions on the machine (45/min per key), shared back-off on
  429, retries only for safe requests.
- Permissions on top of YouGile's: role, project allowlist, denied operations, confirmation
  before writing into client-facing projects.
- Commands `setup`, `check`, `serve` (stdio / http).

[Unreleased]: https://github.com/indalo-tech/yougile-mcp/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/indalo-tech/yougile-mcp/releases/tag/v0.1.0
