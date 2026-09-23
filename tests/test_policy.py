import pytest

from yougile_mcp.catalog import find
from yougile_mcp.dispatch import prepare
from yougile_mcp.policy import Policy, PolicyError, action_names


def test_role_levels():
    reader = Policy(role="reader")
    reader.check_static(find("tasks.get"), None)
    with pytest.raises(PolicyError, match="needs role 'member'"):
        reader.check_static(find("tasks.update"), {})
    member = Policy(role="member")
    member.check_static(find("chats.send_message"), {})
    with pytest.raises(PolicyError, match="needs role 'admin'"):
        member.check_static(find("boards.create"), {})


def test_deny_patterns_and_soft_delete_action():
    assert action_names(find("tasks.update"), {"deleted": True}) == ["tasks.update", "tasks.delete"]
    assert (
        action_names(find("chats.update_message"), {"deleted": True})[-1] == "chats.delete_message"
    )
    policy = Policy(deny=["tasks.delete", "users.*"])
    policy.check_static(find("tasks.update"), {"title": "ok"})
    with pytest.raises(PolicyError, match="tasks.delete is denied"):
        policy.check_static(find("tasks.update"), {"deleted": True})
    with pytest.raises(PolicyError, match="users.remove is denied"):
        policy.check_static(find("users.remove"), None)


async def guard(rt, op_name, params):
    op = find(op_name)
    prep = prepare(op, params)
    return prep, await rt.policy.guard(op, prep, rt.client, rt.directory)


async def test_unrestricted_policy_makes_no_requests(make_runtime, fake):
    rt = make_runtime()
    await guard(rt, "tasks.update", {"id": "t-cli", "title": "x"})
    assert fake.requests == []


async def test_project_allowlist_blocks_other_projects(make_runtime):
    rt = make_runtime(projects=["Разработка"])
    await guard(rt, "tasks.update", {"id": "t-int", "title": "x"})
    with pytest.raises(PolicyError, match="outside the projects"):
        await guard(rt, "tasks.update", {"id": "t-cli", "title": "x"})
    with pytest.raises(PolicyError, match="outside the projects"):
        await guard(rt, "tasks.update", {"id": "t-int", "columnId": "c-cli-queue"})  # moving out
    with pytest.raises(PolicyError, match="outside the projects"):
        await guard(rt, "tasks.create", {"title": "x", "columnId": "c-cli-work"})
    with pytest.raises(PolicyError, match="company-wide"):
        await guard(rt, "chats.create_group_chat", {"title": "x"})


async def test_allowlist_filters_lists_and_checks_single_results(make_runtime):
    rt = make_runtime(projects=["p-int"])
    prep, g = await guard(rt, "tasks.list", {})
    result = await g.apply(await prep.send(rt.client), rt.directory)
    assert [t["id"] for t in result["content"]] == ["t-int"]
    assert result["hidden_by_policy"] == 1

    prep, g = await guard(rt, "tasks.get", {"id": "ID-2"})
    with pytest.raises(PolicyError):
        await g.apply(await prep.send(rt.client), rt.directory)


async def test_confirm_projects_only_for_writes(make_runtime):
    rt = make_runtime(confirm_projects=["Клиенты"])
    _, g = await guard(rt, "chats.send_message", {"chatId": "t-cli", "text": "hi"})
    assert g.confirm_titles == ["Клиенты"]
    _, g = await guard(rt, "chats.send_message", {"chatId": "t-int", "text": "hi"})
    assert g.confirm_titles == []
    _, g = await guard(rt, "chats.list_messages", {"chatId": "t-cli"})
    assert g.confirm_titles == []
