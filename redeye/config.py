"""Configuration loading for RedEye.

Resolution order (later wins):
  1. built-in defaults
  2. ~/.redeye/config.toml (or --config path)
  3. environment variables (REDEYE_*, OPENROUTER_API_KEY, ...)
  4. CLI flags
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REDEYE_HOME = Path(os.environ.get("REDEYE_HOME", str(Path.home() / ".redeye"))).expanduser()

PROVIDERS: dict[str, dict[str, Any]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-sonnet-4",
        "api_key_env": "OPENROUTER_API_KEY",
        "headers": {"HTTP-Referer": "https://github.com/redeye-osint/redeye", "X-Title": "RedEye OSINT"},
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen3:14b",
        "api_key_env": None,  # no key needed
    },
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
        "api_key_env": None,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "api_key_env": "OPENAI_API_KEY",
    },
    "openai-compatible": {
        "base_url": None,  # must be supplied by user
        "default_model": "default",
        "api_key_env": "REDEYE_API_KEY",
    },
    "echo": {  # deterministic offline provider for testing the harness
        "base_url": None,
        "default_model": "echo",
        "api_key_env": None,
    },
}

PERMISSION_MODES = ("readonly", "balanced", "fullauto")


@dataclass
class McpServerConfig:
    name: str
    transport: str = "stdio"  # "stdio" | "sse"
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    enabled: bool = True


@dataclass
class Config:
    # llm
    provider: str = "openrouter"
    model: str = "anthropic/claude-sonnet-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_headers: dict[str, str] = field(default_factory=dict)

    # agent
    permission_mode: str = "balanced"
    max_steps: int = 40
    max_wall_seconds: int = 900
    context_token_budget: int = 60_000

    # optional integration keys
    brave_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None
    hibp_api_key: Optional[str] = None
    github_token: Optional[str] = None
    etherscan_api_key: Optional[str] = None

    mcp_servers: list[McpServerConfig] = field(default_factory=list)

    home: Path = REDEYE_HOME

    # ------------------------------------------------------------------ #
    @property
    def sessions_dir(self) -> Path:
        p = self.home / "sessions"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports_dir(self) -> Path:
        p = self.home / "reports"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def skills_dir(self) -> Path:
        p = self.home / "skills"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def load(
        cls,
        config_path: Optional[str] = None,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> "Config":
        cfg = cls()
        path = Path(config_path).expanduser() if config_path else cfg.home / "config.toml"
        data: dict[str, Any] = {}
        if path.exists():
            with open(path, "rb") as fh:
                data = tomllib.load(fh)

        llm = data.get("llm", {})
        agent = data.get("agent", {})
        keys = data.get("keys", {})
        mcp = data.get("mcp", {})

        if llm.get("provider"):
            cfg.provider = llm["provider"]
        if agent.get("permission_mode") in PERMISSION_MODES:
            cfg.permission_mode = agent["permission_mode"]
        cfg.max_steps = int(agent.get("max_steps", cfg.max_steps))
        cfg.max_wall_seconds = int(agent.get("max_wall_seconds", cfg.max_wall_seconds))
        cfg.context_token_budget = int(agent.get("context_token_budget", cfg.context_token_budget))

        for k in ("brave_api_key", "tavily_api_key", "hibp_api_key", "github_token", "etherscan_api_key"):
            if keys.get(k):
                setattr(cfg, k, keys[k])

        for srv in mcp.get("servers", []) or []:
            if srv.get("name"):
                cfg.mcp_servers.append(
                    McpServerConfig(
                        name=srv["name"],
                        transport=srv.get("transport", "stdio"),
                        command=srv.get("command"),
                        args=list(srv.get("args", [])),
                        env=dict(srv.get("env", {})),
                        url=srv.get("url"),
                        enabled=bool(srv.get("enabled", True)),
                    )
                )

        # --- environment overrides ---
        env = os.environ
        if env.get("REDEYE_PROVIDER"):
            cfg.provider = env["REDEYE_PROVIDER"]
        if env.get("REDEYE_MODE") in PERMISSION_MODES:
            cfg.permission_mode = env["REDEYE_MODE"]
        for env_name, attr in (
            ("BRAVE_API_KEY", "brave_api_key"),
            ("TAVILY_API_KEY", "tavily_api_key"),
            ("HIBP_API_KEY", "hibp_api_key"),
            ("GITHUB_TOKEN", "github_token"),
            ("ETHERSCAN_API_KEY", "etherscan_api_key"),
        ):
            if env.get(env_name):
                setattr(cfg, attr, env[env_name])

        # --- CLI overrides ---
        if provider:
            cfg.provider = provider
        if mode and mode in PERMISSION_MODES:
            cfg.permission_mode = mode
        if base_url:
            cfg.base_url = base_url
        if api_key:
            cfg.api_key = api_key

        # --- resolve provider profile ---
        profile = PROVIDERS.get(cfg.provider)
        if profile is None:
            raise ValueError(
                f"Unknown provider {cfg.provider!r}. Choose from: {', '.join(PROVIDERS)}"
            )
        cfg.model = model or env.get("REDEYE_MODEL") or llm.get("model") or profile["default_model"]
        cfg.base_url = cfg.base_url or llm.get("base_url") or profile.get("base_url")
        if not cfg.api_key:
            key_env = profile.get("api_key_env")
            cfg.api_key = llm.get("api_key") or (env.get(key_env) if key_env else None) or env.get("REDEYE_API_KEY")
        cfg.default_headers = dict(profile.get("headers", {}))

        if cfg.provider in ("ollama", "lmstudio", "echo") and not cfg.api_key:
            cfg.api_key = "redeye-local"  # OpenAI client requires a non-empty key
        return cfg
