from redeye.permissions import Decision, PermissionPolicy


def test_readonly_matrix():
    p = PermissionPolicy(mode="readonly")
    assert p.decide("web_search", "passive") == Decision.ALLOW
    assert p.decide("http_headers", "active") == Decision.ASK
    assert p.decide("mcp__x__write", "sensitive") == Decision.DENY


def test_balanced_matrix():
    p = PermissionPolicy(mode="balanced")
    assert p.decide("web_search", "passive") == Decision.ALLOW
    assert p.decide("http_headers", "active") == Decision.ASK
    assert p.decide("mcp__x__write", "sensitive") == Decision.ASK


def test_fullauto_allows_all():
    p = PermissionPolicy(mode="fullauto")
    for tier in ("passive", "active", "sensitive"):
        assert p.decide("anything", tier) == Decision.ALLOW


def test_remember_overrides():
    p = PermissionPolicy(mode="readonly")
    p.remember("http_headers", allow=True)
    assert p.decide("http_headers", "active") == Decision.ALLOW
    p.remember("http_headers", allow=False)
    # deny set wins (checked first)
    assert p.decide("http_headers", "active") == Decision.DENY


def test_mode_switch_clears_memory():
    p = PermissionPolicy(mode="balanced")
    p.remember("t", allow=True)
    p.set_mode("readonly")
    assert p.decide("t", "active") == Decision.ASK


def test_invalid_mode_rejected():
    p = PermissionPolicy(mode="balanced")
    try:
        p.set_mode("yolo")
        assert False, "should have raised"
    except ValueError:
        pass
