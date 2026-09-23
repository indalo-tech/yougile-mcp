import re

from yougile_mcp.catalog import MAPPING, TOOLS, auth_operation, by_tool, find, load_spec, operations


def test_every_spec_operation_is_mapped_and_nothing_stale():
    spec_ids = {op["operationId"] for item in load_spec()["paths"].values() for op in item.values()}
    assert spec_ids == set(MAPPING)


def test_path_placeholders_match_path_params():
    for op in operations().values():
        placeholders = set(re.findall(r"{(\w+)}", op.path))
        assert placeholders == {p.name for p in op.path_params}, op.operation_id


def test_tools_and_names_are_consistent():
    grouped = by_tool()
    assert set(grouped) == set(TOOLS)
    assert all(grouped[t] for t in TOOLS), "every tool has operations"
    names = [(op.tool, op.name) for op in operations().values() if op.tool]
    assert len(names) == len(set(names))
    assert sum(len(ops) for ops in grouped.values()) == 65


def test_auth_endpoints_are_not_exposed():
    exposed = {op.operation_id for ops in by_tool().values() for op in ops.values()}
    for op_id in ("getCompanies", "AuthKeyController_create", "AuthKeyController_search"):
        assert op_id not in exposed
    assert auth_operation("create_key").path == "/auth/keys"


def test_reads_are_gets():
    for op in operations().values():
        if op.tool and op.method == "GET":
            assert op.access in ("read", "admin"), op.full_name
        if op.method != "GET":
            assert op.access != "read" or op.tool is None, op.full_name


def test_find_and_path_normalization():
    assert find("tasks.create").path == "/tasks"
    assert find("yougile_tasks.get").path == "/tasks/{id}"
    assert find("send_message").full_name == "chats.send_message"
    assert find("list") is None  # ambiguous bare name
    assert find("company.get").path == "/companies"


def test_broken_upload_schema_is_handled():
    upload = find("files.upload")
    assert upload.is_multipart
    assert "file" in upload.body_fields
