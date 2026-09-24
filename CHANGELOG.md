# Changelog · История изменений

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), номера версий —
[SemVer](https://semver.org/lang/ru/). Format: Keep a Changelog, versions follow SemVer.

## [Unreleased]

## [0.13.0] — 2026-09-24

### Русский

#### Добавлено
- Экран `yougile_show_board` — доска: колонки рядом, в каждой карточки задач (номер, название,
  исполнители, срок, просрочка красным), фильтр по исполнителю с поиском, стрелки ← → переносят
  карточку в соседнюю колонку (по цепочке Workflow, если она настроена), клик открывает полную
  карточку с её кнопками. В колонке до 30 карточек и счётчик «30 из N»; в колонках «готово» —
  последние выполненные.
- Экран `yougile_new_task_form` — форма новой задачи. Модель заполняет то, что знает (доска,
  колонка, название, описание, исполнитель, срок); вы выбираете доску и колонку, исполнителя с
  поиском, дату, план часов, чек-лист по строкам и создаёте задачу кнопкой — после этого форма
  показывает карточку новой задачи. Форма есть только у тех, кому можно создавать задачи.
- Кнопки экранов: `yougile_app_board`, `yougile_app_columns`, `yougile_app_create`.

### English

#### Added
- The `yougile_show_board` screen — a board: columns side by side with task cards (number,
  title, assignees, deadline, overdue in red), a searchable filter by assignee, ← → arrows that
  move a card to the neighbouring column (along the Workflow chain if configured), and the full
  card with its buttons on click. A column shows up to 30 cards with a "30 of N" count; done
  columns show the latest completed.
- The `yougile_new_task_form` screen — a new-task form. The model fills in what it knows (board,
  column, title, description, assignee, deadline); you pick the board and column, a searchable
  assignee, the date, planned hours and a line-per-item checklist and create the task with a
  button, after which the form shows the new task's card. Only sessions that may create tasks
  get the form.
- Tools behind the buttons: `yougile_app_board`, `yougile_app_columns`, `yougile_app_create`.

## [0.12.1] — 2026-09-24

### Русский

#### Добавлено
- Кнопка «Развернуть» / «Свернуть» на экранах: просит у клиента показать экран на всё окно
  (режим MCP Apps `fullscreen`) и вернуть обратно. Сработает ли, решает клиент.

#### Изменено
- В таблице задач колонка «Где» стала «Колонкой» и не повторяет проект или доску из заголовка.

### English

#### Added
- An Expand / Collapse button on the screens: asks the client to show the screen in the whole
  window (MCP Apps `fullscreen` mode) and back. Whether it does is up to the client.

#### Changed
- In the task table the "where" column is now "Column" and no longer repeats the project or
  board named in the title.

## [0.12.0] — 2026-09-24

### Русский

#### Добавлено
- Экраны MCP Apps (дополнение `yougile-mcp[apps]`, Prefab UI 0.20.2): `yougile_show_tasks` —
  таблица задач с поиском, сортировкой и карточкой по клику; `yougile_show_task` — карточка с
  кнопками «Выполнено» / «Вернуть в работу», «Взять себе», перенос в колонку по цепочке
  Workflow, отметки чек-листа, списание часов и сообщение в чат. После нажатия экран получает
  свежие данные без запроса к модели; модель получает те же данные текстом.
- Кнопки вызывают инструменты `yougile_app_*`, видимые только экрану. Они идут через те же
  проверки прав; кнопок без прав нет. Нажатие — подтверждение записи, в том числе в проекты из
  `confirm_projects` (на карточке такого проекта есть пометка).
- Экраны и их кнопки показываются только клиентам, которые объявили поддержку MCP Apps
  (`io.modelcontextprotocol/ui`), и только при установленном дополнении.

#### Изменено
- Поиск задач вынесен из `yougile_find_tasks` в `smart.search_tasks`, результат — `Found`;
  таблица и инструмент ищут одинаково.

### English

#### Added
- MCP Apps screens (the `yougile-mcp[apps]` extra, Prefab UI 0.20.2): `yougile_show_tasks` —
  a task table with search, sorting and a card on click; `yougile_show_task` — a card with
  buttons to complete or reopen, take the task, move it to a column along the Workflow chain,
  tick checklist items, log hours and post to the chat. After a click the screen gets fresh
  data without asking the model; the model gets the same data as text.
- Buttons call `yougile_app_*` tools that only the screen sees. They go through the same
  permission checks, and buttons without permission are not shown. A click confirms the write,
  including writes into `confirm_projects` (the card of such a project says so).
- Screens and their buttons are shown only to clients that announce MCP Apps support
  (`io.modelcontextprotocol/ui`), and only with the extra installed.

#### Changed
- The task search moved out of `yougile_find_tasks` into `smart.search_tasks`, returning
  `Found`; the table and the tool search the same way.

## [0.11.0] — 2026-09-24

### Русский

#### Добавлено
- Автодополнение параметров готовых сценариев (MCP completion): `person` — «me» и сотрудники,
  `project` — проекты, `board` — «Проект / Доска» (с учётом выбранного проекта), `column` —
  колонки выбранной доски, `since`/`until` в `hours_report` — понедельник, начало месяца,
  сегодня и т. п. Сначала совпадения с начала, потом по вхождению; проекты вне разрешённых
  правами не предлагаются. В MCP дополняются только аргументы промптов, не инструментов.
- `build_server(resolve_runtime=...)`: запросы дополнения идут мимо middleware, поэтому
  сервер с несколькими пользователями передаёт функцию, которая находит runtime вызывающего.

### English

#### Added
- Argument completion for the ready-made scenarios (MCP completion): `person` — "me" and the
  company's people, `project` — projects, `board` — "Project / Board" (narrowed by a chosen
  project), `column` — the chosen board's columns, `since`/`until` in `hours_report` — Monday,
  the first of the month, today and so on. Prefix matches come first; projects outside the
  permissions are not offered. MCP completes prompt arguments only, not tool arguments.
- `build_server(resolve_runtime=...)`: completion requests bypass middleware, so a
  multi-user server passes a function that finds the caller's runtime.

## [0.10.0] — 2026-09-24

### Русский

#### Добавлено
- Прогресс долгих операций (уведомления MCP progress, если клиент их просит): ожидание лимита
  YouGile («Жду лимит YouGile… ещё около N с»), постраничная загрузка задач, шаги переноса
  по цепочке Workflow, загрузка структуры компании. Сообщения по-русски — их видит человек.
  Модуль `progress`: любой слой зовёт `progress.report(...)`, серверный ограничитель запросов
  может делать так же (`progress.rate_limit_note`).

### English

#### Added
- Progress for long operations (MCP progress notifications, when the client asks for them):
  waiting for YouGile's rate limit, loading tasks page by page, Workflow chain steps, loading
  the company structure. Messages are in Russian, since people read them. The `progress`
  module lets any layer call `progress.report(...)`; a hosted rate limiter can do the same
  (`progress.rate_limit_note`).

## [0.9.1] — 2026-09-24

### Русский

#### Исправлено
- Лимит размера ответа снижен до 30 000 символов: сырой JSON YouGile (UUID, русский текст)
  даёт около половины токена на символ, и 60 000 символов не проходили в Claude Code
  (лимит 25 тыс. токенов на результат инструмента).

### English

#### Fixed
- The response size limit is lowered to 30,000 characters: raw YouGile JSON (UUIDs, Russian
  text) runs at about half a token per character, and 60,000 characters did not pass Claude
  Code's 25k-token limit on a tool result.

## [0.9.0] — 2026-09-24

### Русский

#### Добавлено
- Лимит размера ответа: результат инструмента длиннее ~60 000 символов JSON (около 20 тыс.
  токенов) урезается без поломки структуры. Сначала от самых длинных списков отбрасываются
  хвостовые элементы, затем укорачиваются самые длинные тексты (с пометкой `…[cut]`); в ответе
  появляется `truncated` — сколько показано из скольких и совет сузить запрос. Лимит задаётся
  `Runtime.max_response_chars`.

### English

#### Added
- A response size limit: a tool result longer than ~60,000 characters of JSON (about 20k
  tokens) is trimmed without breaking its structure. The longest lists lose their tail items
  first, then the longest texts are shortened (marked `…[cut]`); the result gets `truncated`
  with how many items are shown out of how many and a hint to narrow the request. The limit is
  `Runtime.max_response_chars`.

## [0.8.0] — 2026-09-24

### Русский

#### Добавлено
- Список инструментов следует правам сессии. Читателю не показываются инструменты записи
  задач (`yougile_create_task`, `yougile_update_task`, `yougile_move_task`, `yougile_log_time`),
  у `yougile_task_chat` без права писать пропадает отправка сообщения, а инструменты разделов
  API перечисляют только разрешённые операции (с учётом роли и запретов `deny`). Проверка
  прав при вызове остаётся прежней.
- `build_server` сам добавляет фильтр списка (`ToolVisibility`); серверу с `middleware`
  нужно привязывать runtime и на выдачу списка инструментов.

### English

#### Added
- The tool list follows the session's permissions. A reader does not see the task-writing tools
  (`yougile_create_task`, `yougile_update_task`, `yougile_move_task`, `yougile_log_time`),
  `yougile_task_chat` loses posting when writing is not allowed, and the API domain tools list
  only the allowed operations (by role and `deny`). Permission checks on calls stay as they were.
- `build_server` adds the listing filter (`ToolVisibility`) itself; a server with its own
  `middleware` has to bind a runtime for tool listings too.

## [0.7.0] — 2026-09-23

### Русский

#### Добавлено
- Выбор вместо ошибки при неоднозначности. Если под название подходит несколько досок,
  проектов, колонок или сотрудников, клиент с MCP elicitation показывает человеку варианты,
  и действие продолжается с выбранным (по протоколу 2026-07-28 — через повтор вызова с
  ответом; выбор и подтверждение записи уживаются в одном действии). Отказ от выбора отменяет
  действие.

#### Изменено
- Несколько частичных совпадений (до 10) теперь тоже считаются неоднозначностью: «Иван» при
  двух Иванах предлагает выбрать, а не отвечает «не найдено».
- Сотрудники в вариантах показываются с почтой — тёзок можно различить.
- Без elicitation ошибка перечисляет варианты и просит модель уточнить у пользователя.

### English

#### Added
- A choice instead of an error for ambiguous names. When a name fits several boards, projects,
  columns or people, a client with MCP elicitation shows the person the options and the action
  goes on with the chosen one (with the 2026-07-28 protocol, by re-running the call with the
  answer; a choice and a write confirmation work together in one action). Declining cancels.

#### Changed
- Several partial matches (up to 10) now count as ambiguous too: "Ivan" with two Ivans asks
  which one instead of answering "not found".
- People in the options show their email, so namesakes can be told apart.
- Without elicitation the error lists the options and asks the model to check with the user.

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

[Unreleased]: https://github.com/indalo-tech/yougile-mcp/compare/v0.13.0...HEAD
[0.13.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.12.1...v0.13.0
[0.12.1]: https://github.com/indalo-tech/yougile-mcp/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/indalo-tech/yougile-mcp/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/indalo-tech/yougile-mcp/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/indalo-tech/yougile-mcp/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/indalo-tech/yougile-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/indalo-tech/yougile-mcp/releases/tag/v0.1.0
