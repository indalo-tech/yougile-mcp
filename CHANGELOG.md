# Changelog · История изменений

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), номера версий —
[SemVer](https://semver.org/lang/ru/). Format: Keep a Changelog, versions follow SemVer.

## [Unreleased]

## [0.6.0] — 2026-09-23

### Русский

#### Добавлено
- `yougile_use_board` — запомнить доску, с которой человек обычно работает. Инструменты задач
  берут её, когда не указаны ни доска, ни проект (создать задачу, колонка без доски);
  `yougile_overview` показывает её в `defaults`. Без доски — забыть выбор. Локально выбор живёт
  до перезапуска сервера; сервер может хранить его за человеком (`Runtime.board`,
  `Runtime.save_board`).

#### Изменено
- Ошибка «нужна доска» предлагает передать доску или запомнить её через `yougile_use_board`,
  а не отправляет в настройки.

### English

#### Added
- `yougile_use_board` remembers the board the person usually works on. Task tools use it when
  they get neither a board nor a project (creating a task, a column without a board);
  `yougile_overview` shows it under `defaults`. Without a board it forgets the choice. Locally
  the choice lasts until the server restarts; a hosted server can keep it per person
  (`Runtime.board`, `Runtime.save_board`).

#### Changed
- The "board is required" error suggests passing a board or remembering one with
  `yougile_use_board` instead of sending people to the settings.

## [0.5.1] — 2026-09-23

### Русский

#### Исправлено
- Отказ по правам (роль, проекты, запрещённые операции) говорит, где эти права меняются:
  `.yougile.json` локально, страница администратора на сервере (`Runtime.settings_hint`).
- `yougile_overview` возвращает `settings_in` — где меняются настройки и права, чтобы ассистент
  мог дать ссылку, когда об этом спрашивают.

### English

#### Fixed
- Permission refusals (role, projects, denied operations) say where those permissions are
  changed: `.yougile.json` locally, the admin page on a hosted server (`Runtime.settings_hint`).
- `yougile_overview` returns `settings_in`, where settings and permissions are changed, so the
  assistant can give the link when asked.

## [0.5.0] — 2026-09-23

### Русский

#### Добавлено
- Настройка `done_columns` — колонки, которые означают «сделано», даже если задача не отмечена
  выполненной (многие команды просто переносят карточку в «Готово»). Такие задачи в поиске
  считаются выполненными (`done_by_column: true`), не попадают в открытые и не бывают
  просроченными; `yougile_overview` показывает эти колонки.
- `yougile_move_task`: перенос в такую колонку отмечает задачу выполненной — YouGile запоминает
  дату, и задача попадает в стендап и отчёты за период; перенос обратно снимает отметку.

#### Изменено
- Сценарии `standup` и `hours_report` отделяют задачи «сделано по колонке» без даты: YouGile не
  хранит дату переноса, поэтому их нельзя отнести ко «вчера» или к периоду.

### English

#### Added
- `done_columns` setting: columns that mean "done" even when a task is not marked completed
  (many teams just move the card to "Done"). Such tasks count as completed in searches
  (`done_by_column: true`), are never open or overdue, and `yougile_overview` lists the columns.
- `yougile_move_task`: moving into such a column marks the task completed, so YouGile records
  the date and the task shows up in stand-ups and period reports; moving it back reopens it.

#### Changed
- The `standup` and `hours_report` scenarios keep "done by column" tasks without a date apart:
  YouGile does not store when a card was moved, so they cannot be placed in "yesterday" or a
  period.

## [0.4.0] — 2026-09-23

### Русский

#### Добавлено
- Готовые сценарии — промпты MCP: `standup` (стендап: сделано с прошлого рабочего дня, в работе,
  блокеры), `hours_report` (план и факт часов за период по проектам и людям, перерасход) и
  `triage` (разбор очереди с предложениями; изменения — только после согласия человека).
  «Сегодня» и «прошлый рабочий день» считаются в часовом поясе компании.
- `yougile_find_tasks`: фильтры `completed_since` / `completed_until` — задачи, выполненные за
  период, новые сверху; у выполненных задач — `completed_at`, у просроченных открытых —
  `overdue: true` (срок-дата действует до конца дня).

### English

#### Added
- Ready-made scenarios as MCP prompts: `standup` (done since the previous working day, in
  progress, blockers), `hours_report` (planned vs worked hours for a period by project and
  person, overruns) and `triage` (queue triage with suggestions; changes only after a person's
  consent). "Today" and "the previous working day" follow the company time zone.
- `yougile_find_tasks`: `completed_since` / `completed_until` select tasks completed in a period,
  newest first; completed tasks show `completed_at`, overdue open ones `overdue: true` (a
  date-only deadline lasts until the end of that day).

## [0.3.1] — 2026-09-23

### Русский

#### Исправлено
- Карточка задачи больше не выдаёт id стикера за его название. Стикеры типов, которых API
  YouGile не описывает (числа, свободный текст), идут отдельно — в `other_stickers`, по id.
- Подсказки в ошибках («нет доски по умолчанию», «добавьте цепочку Workflow») указывают, где
  на самом деле меняются настройки: новое поле `Runtime.settings_hint` — `.yougile.json`
  локально, страница администратора на сервере. Описания инструментов больше не отсылают
  к `.yougile.json`.
- Поиск задачи по номеру возвращает `scope`, как любой другой поиск.
- README: адрес работающей серверной версии — `https://yougile.indalo.ru/mcp`.

### English

#### Fixed
- The task card no longer passes a sticker id off as its name. Sticker types the YouGile API
  does not describe (numbers, free text) come separately, by id, under `other_stickers`.
- Error hints ("no default board", "add the Workflow chain") point to where settings really
  live: the new `Runtime.settings_hint` — `.yougile.json` locally, the admin page on a hosted
  server. Tool descriptions no longer refer to `.yougile.json`.
- A search by task number returns `scope`, like any other search.
- README: the address of the running hosted version, `https://yougile.indalo.ru/mcp`.

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

[Unreleased]: https://github.com/indalo-tech/yougile-mcp/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/indalo-tech/yougile-mcp/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/indalo-tech/yougile-mcp/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/indalo-tech/yougile-mcp/releases/tag/v0.1.0
