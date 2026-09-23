import base64

import pytest

from yougile_mcp.catalog import find
from yougile_mcp.dispatch import ParamError, describe, error_hint, prepare


def test_flat_params_are_routed():
    prep = prepare(find("tasks.list"), {"columnId": "c1", "limit": 10})
    assert prep.path == "/task-list"
    assert prep.query == {"columnId": "c1", "limit": 10}
    assert prep.body is None

    prep = prepare(find("tasks.update"), {"id": "ID-5", "title": "T", "completed": True})
    assert prep.path == "/tasks/ID-5"
    assert prep.body == {"title": "T", "completed": True}


def test_explicit_query_and_body_are_accepted():
    prep = prepare(find("tasks.update"), {"id": "x", "body": {"title": "T"}})
    assert prep.body == {"title": "T"}


def test_unknown_param_is_rejected_with_allowed_list():
    with pytest.raises(ParamError, match="unknown parameter.*titel.*Allowed:.*title"):
        prepare(find("tasks.update"), {"id": "x", "titel": "typo"})


def test_missing_path_param():
    with pytest.raises(ParamError, match="missing required path parameter 'id'"):
        prepare(find("tasks.get"), {})


def test_id_alias_for_single_path_param():
    prep = prepare(find("chats.list_messages"), {"id": "task-1", "limit": 5})
    assert prep.path == "/chats/task-1/messages"
    assert prep.query == {"limit": 5}


def test_path_values_are_url_encoded():
    prep = prepare(find("tasks.get"), {"id": "a/b c"})
    assert prep.path == "/tasks/a%2Fb%20c"


def test_idempotency_key_is_added_to_creates():
    prep = prepare(find("tasks.create"), {"title": "T", "columnId": "c"})
    assert prep.body["idempotencyKey"]
    prep = prepare(find("tasks.create"), {"title": "T", "idempotencyKey": "mine"})
    assert prep.body["idempotencyKey"] == "mine"
    assert "idempotencyKey" not in (
        prepare(find("chats.send_message"), {"chatId": "c", "text": "x"}).body
    )


def test_upload_from_base64_and_path(tmp_path):
    prep = prepare(
        find("files.upload"),
        {"content_base64": base64.b64encode(b"hi").decode(), "filename": "a.txt"},
    )
    assert prep.files == {"file": ("a.txt", b"hi", "text/plain")}
    file = tmp_path / "pic.png"
    file.write_bytes(b"\x89PNG")
    prep = prepare(find("files.upload"), {"file_path": str(file)})
    assert prep.files["file"][0] == "pic.png"
    with pytest.raises(ParamError):
        prepare(find("files.upload"), {})


def test_describe_and_hint():
    info = describe(find("tasks.create"))
    names = {f["name"] for f in info["body"]}
    assert {"title", "columnId", "deadline", "timeTracking"} <= names
    assert "idempotencyKey" not in names
    assert "title" in error_hint(find("tasks.create"))
