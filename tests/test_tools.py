from redeye.tools.base import MAX_RESULT_CHARS, ToolRegistry, ToolResult


def test_register_and_execute():
    reg = ToolRegistry()

    @reg.tool(name="ping", description="t", parameters={"type": "object", "properties": {}})
    def ping():
        return ToolResult(ok=True, content="pong")

    r = reg.execute("ping", {})
    assert r.ok and r.content == "pong"
    assert reg.openai_tools()[0]["function"]["name"] == "ping"


def test_unknown_tool_is_error_not_exception():
    reg = ToolRegistry()
    r = reg.execute("nope", {})
    assert not r.ok and "unknown tool" in r.content


def test_handler_exception_becomes_error_result():
    reg = ToolRegistry()

    @reg.tool(name="boom", description="t", parameters={})
    def boom():
        raise RuntimeError("kaput")

    r = reg.execute("boom", {})
    assert not r.ok and "kaput" in r.content


def test_bad_args_become_error_result():
    reg = ToolRegistry()

    @reg.tool(name="needs", description="t", parameters={})
    def needs(required_arg):
        return ToolResult(ok=True, content=required_arg)

    r = reg.execute("needs", {"wrong": 1})
    assert not r.ok and "bad arguments" in r.content


def test_long_results_are_truncated():
    reg = ToolRegistry()

    @reg.tool(name="big", description="t", parameters={})
    def big():
        return ToolResult(ok=True, content="x" * (MAX_RESULT_CHARS + 5000))

    r = reg.execute("big", {})
    assert r.truncated
    assert len(r.content) <= MAX_RESULT_CHARS + 100
    assert "truncated" in r.content


def test_schema_sanitization():
    reg = ToolRegistry()

    @reg.tool(name="s", description="d", parameters={"$schema": "http://x", "properties": {}})
    def s():
        return ToolResult(ok=True, content="")

    schema = reg.openai_tools()[0]
    params = schema["function"]["parameters"]
    assert params["type"] == "object"
    assert "$schema" not in params
