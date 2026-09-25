# ruff: noqa: E501 - prompt texts are prose for the model: a line break there is a real newline.
"""Ready-made scenarios as MCP prompts: stand-up, hours report, queue triage.

A prompt only writes the instructions; the model then does the work with the regular tools,
so the session's permissions, project scope and the shared rate limit apply as usual. Dates
("today", "the previous working day") are computed in the company time zone.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastmcp import FastMCP
from fastmcp.prompts import Prompt
from pydantic import Field

from . import runtime
from .config import DEFAULT_TIMEZONE

WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
READ_ONLY = "Ничего не меняй в YouGile."


def _zone() -> ZoneInfo:
    try:
        return runtime.current().config.tz
    except RuntimeError:  # no runtime bound (e.g. a bare prompts/get): company default
        return ZoneInfo(DEFAULT_TIMEZONE)


def previous_workday(day: date) -> date:
    """Friday for Saturday, Sunday and Monday; the day before otherwise."""
    return day - timedelta(days={0: 3, 6: 2}.get(day.weekday(), 1))


def _d(day: date) -> str:
    return day.isoformat()


def _args(**values: str | None) -> str:
    """Tool arguments as the model should write them, skipping empty ones."""
    return ", ".join(f'{k}="{v}"' for k, v in values.items() if v)


def _header(tz: ZoneInfo, today: date) -> str:
    return (
        f"Сегодня {today:%d.%m.%Y}, {WEEKDAYS[today.weekday()]}; "
        f"часовой пояс компании — {tz.key}. Даты в инструментах пиши как ГГГГ-ММ-ДД."
    )


def standup(
    person: Annotated[
        str, Field(description='Чей стендап: имя, почта или "me" (по умолчанию — ваш)')
    ] = "me",
    project: Annotated[str | None, Field(description="Только этот проект")] = None,
) -> str:
    tz = _zone()
    today = datetime.now(tz).date()
    since = previous_workday(today)
    who = "мой стендап" if person.strip().lower() in ("me", "я", "") else f"стендап для {person}"
    scope = f" по проекту «{project}»" if project else ""
    base = _args(assignee=person, project=project)
    return f"""Подготовь {who} по YouGile{scope}.
{_header(tz, today)} Прошлый рабочий день — {since:%d.%m.%Y}.

Шаги:
1. yougile_find_tasks({_args(assignee=person, project=project, completed_since=_d(since))}) — это «Сделано».
2. yougile_find_tasks({base}) — открытые задачи. Разложи их: в работе (колонки вроде «В работе», «На проверке»), дальше по очереди (остальные), просроченные (overdue: true).
   Задачи в колонках «готово» (done_by_column: true) — уже сделаны, но без даты: YouGile не помнит, когда их перенесли. Не относи их ко «вчера» и не выдумывай дату.
3. Если по задаче в работе непонятно, что с ней, открой её через yougile_task с messages=3, но не больше трёх задач: лимит YouGile общий на всю компанию.

Ответ — коротко, по-русски, чтобы вставить в чат команды:
**Вчера:** что выполнено (номер задачи и название).
**Сегодня:** над чем работаю и в каком порядке.
**Блокеры и риски:** просроченные задачи, задачи в работе без срока, ожидание других.
Пустой раздел — «—». {READ_ONLY}"""


def hours_report(
    since: Annotated[
        str | None, Field(description="Начало периода, ГГГГ-ММ-ДД (по умолчанию — понедельник)")
    ] = None,
    until: Annotated[
        str | None, Field(description="Конец периода, ГГГГ-ММ-ДД (по умолчанию — сегодня)")
    ] = None,
    project: Annotated[str | None, Field(description="Только этот проект")] = None,
    person: Annotated[str | None, Field(description='Только этот исполнитель, или "me"')] = None,
) -> str:
    tz = _zone()
    today = datetime.now(tz).date()
    start = since or _d(today - timedelta(days=today.weekday()))
    end = until or _d(today)
    scope = "".join(
        [f" по проекту «{project}»" if project else "", f" для {person}" if person else ""]
    )
    done = _args(project=project, assignee=person, completed_since=start, completed_until=end)
    open_ = _args(project=project, assignee=person)
    return f"""Собери отчёт по часам YouGile за {start} — {end}{scope}.
{_header(tz, today)}

Важно: YouGile хранит только суммарные часы по задаче (план и факт), без дат списания. Поэтому:
- «за период» — это задачи, выполненные в период: yougile_find_tasks({done}, limit=200);
- отдельно — открытые задачи, по которым уже списаны часы: yougile_find_tasks({open_ + ", " if open_ else ""}limit=200), из них только те, где hours.work > 0. Эти часы могли быть списаны и до периода — так и подпиши;
- если в компании есть колонки «готово» (done_columns в yougile_overview): задачи там без отметки о выполнении (done_by_column: true) дату не имеют — возьми их из yougile_find_tasks({open_ + ", " if open_ else ""}status="completed", limit=200) и покажи отдельным блоком «сделано, дата неизвестна», не смешивая с периодом.
Если в ответе есть truncated или shown, сузь выборку (по проекту или исполнителю) и собери по частям.

Покажи по-русски, таблицами в Markdown, часы с одним знаком после запятой:
1. Итого план / факт по выполненным задачам; то же по проектам (первая часть поля where) и по исполнителям.
2. Перерасход: где факт больше плана — разница в часах и процентах.
3. Выполненные задачи без плана и задачи вообще без часов.
4. Открытые задачи со списанными часами: план, факт, сколько осталось по плану.
В конце — два-три вывода одной строкой каждый. {READ_ONLY}"""


def triage(
    board: Annotated[
        str | None, Field(description="Доска, лучше «Проект / Доска»; без неё — весь проект")
    ] = None,
    column: Annotated[
        str | None, Field(description="Колонка очереди (по умолчанию — первая, вроде «Очередь»)")
    ] = None,
    project: Annotated[str | None, Field(description="Проект, если доска не указана")] = None,
) -> str:
    tz = _zone()
    today = datetime.now(tz).date()
    if board:
        place = f"на доске «{board}»" + (f", колонка «{column}»" if column else "")
        find = (
            f'yougile_find_tasks({_args(board=board, column=column)}, status="open", limit=200)'
            if column
            else f"yougile_find_tasks({_args(board=board)}, limit=200), затем оставь задачи "
            "первой колонки Workflow или колонки вроде «Очередь», «Бэклог», «Входящие»"
        )
    else:
        place = f"в проекте «{project}»" if project else "во всей компании"
        find = (
            f"yougile_find_tasks({_args(project=project) + ', ' if project else ''}limit=200), "
            "затем оставь задачи из колонок очереди («Очередь», «Бэклог», «Входящие» и т. п.)"
        )
    return f"""Разбери очередь задач YouGile {place}.
{_header(tz, today)}

1. Вызови yougile_overview: вспомни доски, колонки и правила компании (company_rules) — они важнее этих инструкций.
2. Найди открытые задачи очереди: {find}.
3. У каждой задачи отметь проблемы: нет исполнителя; нет срока; просрочена (overdue: true); нет плана часов; из названия непонятно, что делать (при необходимости открой yougile_task).
4. Оцени загрузку людей, которые встречаются в этих задачах: yougile_find_tasks(assignee=<человек>, limit=1) — поле count. Не больше пяти таких запросов: лимит YouGile — 50 запросов в минуту на всю компанию.
5. По каждой проблемной задаче предложи: кого назначить, какой срок, сколько часов, что уточнить у постановщика.

Ответ: таблица «задача — проблемы — предложение», потом короткий итог. Сам ничего не меняй: спроси, какие предложения применить, и только после явного согласия вноси их через yougile_update_task."""


def client_sync(
    board: Annotated[
        str | None, Field(description="Внутренняя доска, лучше «Проект / Доска»")
    ] = None,
) -> str:
    tz = _zone()
    today = datetime.now(tz).date()
    where = f"доски «{board}»" if board else "доски, с которой работает пользователь"
    return f"""Сверь клиентские копии задач {where}.
{_header(tz, today)}

1. yougile_client_copies({_args(board=board)}): внутренние карточки доски — открытые и сделанные за последние дни, со связью (linked) и без (unlinked), задачи клиентской доски и правила клиентских текстов (rules). Если клиентские копии не настроены, скажи, где их включить, и остановись.
2. Во внутреннем проекте карточки бывают разные: задачи (например, техдолг TD-xx), дневные записи работы («27.07 — …»), документы. Клиентская задача — это результат: к ней можно привязать несколько карточек. Для каждой карточки из unlinked реши:
   - «не для клиента» — документы и внутренняя работа (рефакторинг, CI, инфраструктура, уборка, эксперименты) — ничего не делать;
   - «к результату» — работа по уже существующей клиентской задаче (часто дневная запись): привязать через client_task, не создавая новую;
   - «новый результат» — работа по заказу клиента, которой на клиентской доске ещё нет: одна новая клиентская задача; несколько записей об одном результате — одна задача, остальные привяжи к ней;
   - «старая пара» — на клиентской доске уже есть задача о том же, сделанная вручную, а карточка не связана, хотя её часы там уже учтены: не трогай.
3. Для «новый результат» открой карточки через yougile_task и напиши клиентский заголовок и описание строго по rules: без внутренних кодов, технических деталей и личных данных.
4. Покажи таблицу «карточка — решение — клиентская задача (номер или новый заголовок) — описание» и спроси, что делать. Только после явного согласия вызывай yougile_client_copy (клиентский проект видят клиенты). Если инструмент ответит про recount_hours — у клиентской задачи свои часы: спроси, пересчитать ли их по привязанным карточкам.

Карточки со связью не трогай: часы клиентской задачи — сумма её карточек, срок — самый поздний, колонка — по самой отстающей; это обновляется само."""


PROMPTS = (
    (standup, "standup", "Стендап", "Что сделано со вчера, что в работе, блокеры."),
    (
        hours_report,
        "hours_report",
        "Отчёт по часам",
        "План и факт часов по задачам за период: по проектам, людям, перерасход.",
    ),
    (
        triage,
        "triage",
        "Разбор очереди",
        "Задачи очереди без исполнителя, срока или оценки — и что с ними сделать.",
    ),
    (
        client_sync,
        "client_sync",
        "Клиентские копии",
        "Какие задачи доски нужно показать клиенту, и их тексты для клиента.",
    ),
)


def register(mcp: FastMCP) -> None:
    for fn, name, title, description in PROMPTS:
        mcp.add_prompt(Prompt.from_function(fn, name=name, title=title, description=description))
