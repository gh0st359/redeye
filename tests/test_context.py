from redeye import context


def make_messages(tool_chars: int, n_tools: int = 10):
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(n_tools):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": "t", "arguments": "{}"}}
        ]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "z" * tool_chars})
    msgs.append({"role": "user", "content": "latest question"})
    return msgs


def test_under_budget_unchanged():
    msgs = make_messages(100, 2)
    assert context.fit(msgs, 100_000) is msgs


def test_old_tool_outputs_compressed_recent_preserved():
    msgs = make_messages(50_000, 10)
    fitted = context.fit(msgs, 5_000)
    # recent messages untouched
    assert fitted[-1]["content"] == "latest question"
    last_tool = [m for m in fitted if m.get("role") == "tool"][-1]
    assert len(last_tool["content"]) == 50_000
    # older ones compressed
    first_tool = [m for m in fitted if m.get("role") == "tool"][0]
    assert len(first_tool["content"]) < 5_000
    # and the whole thing fits better than before
    assert context.estimate_tokens(fitted) < context.estimate_tokens(msgs)


def test_aggressive_pass_omits_old_tools():
    msgs = make_messages(100_000, 20)
    fitted = context.fit(msgs, 1_000)
    olds = [m for m in fitted[:-context.KEEP_RECENT_MESSAGES] if m.get("role") == "tool"]
    assert any("omitted" in m["content"] for m in olds)
