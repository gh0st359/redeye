from redeye.guardrails import GuardConfig, LoopGuard


def make(**kw):
    return LoopGuard(GuardConfig(**kw))


def test_repeat_soft_steering_then_hard_stop():
    g = make(repeat_soft_threshold=2, repeat_hard_threshold=4)
    assert g.record_call("web_search", {"query": "x"}).steering is None
    v2 = g.record_call("web_search", {"query": "x"})
    assert v2.steering and "already called" in v2.steering
    g.record_call("web_search", {"query": "x"})
    v4 = g.record_call("web_search", {"query": "x"})
    assert v4.stop and "identical" in v4.reason


def test_different_args_do_not_trigger_repeat():
    g = make()
    for i in range(5):
        v = g.record_call("web_search", {"query": f"q{i}"})
        assert not v.stop
        assert v.steering is None


def test_per_tool_caps():
    g = make(per_tool_soft_cap=3, per_tool_hard_cap=5)
    for i in range(2):
        g.record_call("fetch_url", {"url": f"http://a{i}.com"})
    v = g.record_call("fetch_url", {"url": "http://b.com"})
    assert v.steering and "fetch_url" in v.steering
    g.record_call("fetch_url", {"url": "http://c.com"})
    v = g.record_call("fetch_url", {"url": "http://d.com"})
    assert v.stop


def test_error_circuit_breaker():
    g = make(error_soft_threshold=2, error_hard_threshold=4)
    assert g.record_result(ok=False).steering is None
    v = g.record_result(ok=False)
    assert v.steering and "failed" in v.steering
    g.record_result(ok=False)
    v = g.record_result(ok=False)
    assert v.stop
    # recovery resets the counter
    g2 = make(error_soft_threshold=2)
    g2.record_result(ok=False)
    g2.record_result(ok=True)
    assert g2.record_result(ok=False).steering is None


def test_step_budget():
    g = make(max_steps=3)
    g.record_step(); g.record_step(); g.record_step()
    v = g.budget_check()
    assert v.stop and "step budget" in v.reason


def test_stats():
    g = make()
    g.record_step()
    g.record_call("dns_records", {"domain": "x.com"})
    s = g.stats()
    assert s["steps"] == 1 and s["tools_used"] == {"dns_records": 1}
