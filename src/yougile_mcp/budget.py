"""Keep tool results within what a model can take in, without breaking their structure.

A plain cut in the middle of JSON leaves the model guessing. Instead the longest lists lose
their tail items, then the longest texts are shortened, and a ``truncated`` note says what was
left out and how to get it.
"""

from __future__ import annotations

import copy
import json
from typing import Any

# Raw YouGile JSON (UUIDs, Russian text) runs at about half a token per character, and Claude
# Code refuses tool results over 25k tokens: 30k characters stays well below that.
DEFAULT_MAX_CHARS = 30_000
MIN_TEXT = 300  # a shortened text keeps at least this many characters
CUT_MARK = " …[cut]"
HINT = "Narrow the request (filters, a smaller limit, offset) to see the rest."


def size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _lists(value: Any, path: str = "") -> list[tuple[str, list]]:
    found: list[tuple[str, list]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found += _lists(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        if len(value) > 1:
            found.append((path or "items", value))
        for i, item in enumerate(value):
            found += _lists(item, f"{path}[{i}]")
    return found


def _texts(value: Any) -> list[tuple[Any, Any, str]]:
    """(container, key, text) for every string, so it can be replaced in place."""
    found: list[tuple[Any, Any, str]] = []
    items = value.items() if isinstance(value, dict) else enumerate(value)
    for key, item in items:
        if isinstance(item, str):
            found.append((value, key, item))
        elif isinstance(item, dict | list):
            found += _texts(item)
    return found


def fit(result: Any, max_chars: int = DEFAULT_MAX_CHARS) -> Any:
    """``result`` itself when it is small enough, else a trimmed copy with a ``truncated`` note."""
    if size(result) <= max_chars:
        return result
    data: dict[str, Any] = copy.deepcopy(result if isinstance(result, dict) else {"items": result})
    note: dict[str, Any] = {"lists": {}, "hint": HINT}
    budget = max_chars - 400  # room for the note itself

    # 1. Drop tail items of the biggest lists, the biggest first.
    for _ in range(10):
        if size(data) <= budget:
            break
        lists = [(p, lst) for p, lst in _lists(data) if len(lst) > 1]
        if not lists:
            break
        path, lst = max(lists, key=lambda pl: size(pl[1]))
        total = note["lists"].get(path, {}).get("total", len(lst))
        full = list(lst)
        lo, hi = 1, len(full) - 1  # keep at least one item, drop at least one
        while lo < hi:  # the largest count that fits
            mid = (lo + hi + 1) // 2
            lst[:] = full[:mid]
            if size(data) <= budget:
                lo = mid
            else:
                hi = mid - 1
        lst[:] = full[:lo]
        note["lists"][path] = {"shown": lo, "total": total}

    # 2. Shorten the longest texts.
    for _ in range(20):
        excess = size(data) - budget
        if excess <= 0:
            break
        texts = [t for t in _texts(data) if len(t[2]) > MIN_TEXT]
        if not texts:
            break
        container, key, text = max(texts, key=lambda t: len(t[2]))
        keep = max(MIN_TEXT, len(text) - excess - len(CUT_MARK))
        container[key] = text[:keep] + CUT_MARK
        note["texts_cut"] = note.get("texts_cut", 0) + 1

    if not note["lists"]:
        del note["lists"]
    data["truncated"] = note
    if size(data) > max_chars:  # nothing structured left to trim: plain text as the last resort
        text = json.dumps(result, ensure_ascii=False, default=str)
        return {"truncated": {"hint": HINT}, "text": text[: max(0, max_chars - 300)] + CUT_MARK}
    return data
