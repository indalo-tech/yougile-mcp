import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from yougile_mcp import runtime
from yougile_mcp.server import build_server, instructions


@pytest.fixture
def server_for(make_runtime):
    def build(**config):
        rt = make_runtime(**config)
        runtime.set_default(rt)
        return build_server(rt)

    yield build
    runtime.set_default(None)


async def test_tools_are_listed_with_operation_enums(server_for):
    async with Client(server_for()) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert len(tools) == 19
    enum = tools["yougile_tasks"].input_schema["properties"]["operation"]["enum"]
    assert {"list", "get", "create", "update"} <= set(enum)


async def test_call_passes_through_to_api(server_for, fake):
    async with Client(server_for()) as client:
        result = await client.call_tool(
            "yougile_tasks", {"operation": "get", "params": {"id": "ID-1"}}
        )
    assert result.data["title"] == "Internal"
    assert fake.requests[-1].url.path == "/api-v2/tasks/ID-1"


async def test_param_errors_become_tool_errors(server_for):
    async with Client(server_for()) as client:
        with pytest.raises(ToolError, match="unknown parameter"):
            await client.call_tool(
                "yougile_tasks", {"operation": "update", "params": {"id": "x", "nope": 1}}
            )


async def test_api_errors_carry_hints(server_for, fake):
    async with Client(server_for()) as client:
        with pytest.raises(ToolError, match="404.*not visible"):
            await client.call_tool(
                "yougile_tasks", {"operation": "get", "params": {"id": "ID-404"}}
            )


async def test_role_is_enforced(server_for, fake):
    async with Client(server_for(role="reader")) as client:
        with pytest.raises(ToolError, match="needs role"):
            await client.call_tool(
                "yougile_tasks", {"operation": "update", "params": {"id": "t-int", "title": "x"}}
            )
    assert fake.requests == []


async def test_confirmation_required_without_elicitation(server_for, fake):
    async with Client(server_for(confirm_projects=["Клиенты"])) as client:
        with pytest.raises(ToolError, match="confirmation_required"):
            await client.call_tool(
                "yougile_chats",
                {"operation": "send_message", "params": {"chatId": "t-cli", "text": "hi"}},
            )
        assert fake.calls("POST", "/api-v2/chats/t-cli/messages") == 0
        await client.call_tool(
            "yougile_chats",
            {
                "operation": "send_message",
                "params": {"chatId": "t-cli", "text": "hi"},
                "confirm": True,
            },
        )
    assert fake.calls("POST", "/api-v2/chats/t-cli/messages") == 1


@pytest.mark.parametrize("approve", [False, True])
async def test_elicitation_is_used_when_client_supports_it(server_for, fake, approve):
    answers = []

    async def elicitation_handler(message, response_type, params, context):
        answers.append(message)
        return response_type(value=approve)

    server = server_for(confirm_projects=["Клиенты"])
    async with Client(server, elicitation_handler=elicitation_handler) as client:
        result = await client.call_tool(
            "yougile_chats",
            {
                "operation": "send_message",
                "params": {"chatId": "t-cli", "text": "hi"},
                "confirm": True,
            },
        )
    assert answers and "Клиенты" in answers[0]
    sent = fake.calls("POST", "/api-v2/chats/t-cli/messages")
    if approve:
        assert sent == 1 and "id" in result.data
    else:
        assert result.data["cancelled"] is True, "confirm=true must not bypass a real user prompt"
        assert sent == 0


async def test_help(server_for):
    async with Client(server_for()) as client:
        listing = (await client.call_tool("yougile_help", {})).data
        assert "tasks" in listing and "_session" in listing
        detail = (await client.call_tool("yougile_help", {"operation": "tasks.create"})).data
        assert detail["http"] == "POST /api-v2/tasks"
        with pytest.raises(ToolError, match="Did you mean"):
            await client.call_tool("yougile_help", {"operation": "tasks.craete"})


def test_instructions_include_company_rules(make_runtime):
    text = instructions(make_runtime(role="member", instructions="Пишите кратко."))
    assert "role=member" in text and "Пишите кратко." in text
