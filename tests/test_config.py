import os

import pytest

from redeye.config import Config


def test_defaults_openrouter(monkeypatch, tmp_path):
    monkeypatch.setenv("REDEYE_HOME", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = Config.load(config_path=str(tmp_path / "nope.toml"))
    assert cfg.provider == "openrouter"
    assert cfg.base_url == "https://openrouter.ai/api/v1"
    assert cfg.permission_mode == "balanced"


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("REDEYE_PROVIDER", "ollama")
    monkeypatch.setenv("REDEYE_MODEL", "llama3.1:8b")
    monkeypatch.setenv("BRAVE_API_KEY", "bk-test")
    cfg = Config.load(config_path=str(tmp_path / "nope.toml"))
    assert cfg.provider == "ollama"
    assert cfg.model == "llama3.1:8b"
    assert cfg.brave_api_key == "bk-test"
    assert cfg.api_key == "redeye-local"  # local providers get a placeholder key


def test_cli_flags_win(monkeypatch, tmp_path):
    monkeypatch.setenv("REDEYE_PROVIDER", "ollama")
    cfg = Config.load(config_path=str(tmp_path / "nope.toml"), provider="echo", mode="fullauto")
    assert cfg.provider == "echo"
    assert cfg.permission_mode == "fullauto"


def test_toml_file(monkeypatch, tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[llm]\nprovider = "lmstudio"\nmodel = "qwen"\n'
        '[agent]\npermission_mode = "readonly"\nmax_steps = 7\n'
        '[keys]\ngithub_token = "ghp_x"\n'
        '[[mcp.servers]]\nname = "s1"\ntransport = "sse"\nurl = "http://localhost:9/sse"\n'
    )
    cfg = Config.load(config_path=str(p))
    assert cfg.provider == "lmstudio"
    assert cfg.model == "qwen"
    assert cfg.permission_mode == "readonly"
    assert cfg.max_steps == 7
    assert cfg.github_token == "ghp_x"
    assert cfg.mcp_servers[0].name == "s1"
    assert cfg.mcp_servers[0].transport == "sse"


def test_unknown_provider_raises(tmp_path):
    with pytest.raises(ValueError):
        Config.load(config_path=str(tmp_path / "nope.toml"), provider="skynet")
