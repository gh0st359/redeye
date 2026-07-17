"""RedEye command-line entry point.

  redeye                      interactive operator console
  redeye run "goal"           one-shot investigation
  redeye doctor               self-check (keys, providers, MCP, egress)
  redeye sessions             list past sessions
  redeye skills               list tradecraft skills
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Config, PERMISSION_MODES, PROVIDERS
from .tui.render import Renderer, render_final

app = typer.Typer(
    add_completion=False,
    help="RedEye — agentic AI OSINT workbench for the terminal.",
    no_args_is_help=False,
)


def _load_cfg(
    config: Optional[str], provider: Optional[str], model: Optional[str],
    mode: Optional[str], base_url: Optional[str], api_key: Optional[str],
) -> Config:
    try:
        return Config.load(
            config, provider=provider, model=model, mode=mode,
            base_url=base_url, api_key=api_key,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


COMMON = dict(
    config=typer.Option(None, "--config", "-c", help="Path to config.toml"),
    provider=typer.Option(None, "--provider", "-p", help=f"LLM provider: {', '.join(PROVIDERS)}"),
    model=typer.Option(None, "--model", "-m", help="Model name, e.g. anthropic/claude-sonnet-4"),
    mode=typer.Option(None, "--mode", help=f"Permission mode: {' | '.join(PERMISSION_MODES)}"),
    base_url=typer.Option(None, "--base-url", help="Custom OpenAI-compatible endpoint"),
    api_key=typer.Option(None, "--api-key", help="API key (prefer env vars)"),
)


@app.callback(invoke_without_command=True)
def app_callback(
    ctx: typer.Context,
    config: Optional[str] = COMMON["config"],
    provider: Optional[str] = COMMON["provider"],
    model: Optional[str] = COMMON["model"],
    mode: Optional[str] = COMMON["mode"],
    base_url: Optional[str] = COMMON["base_url"],
    api_key: Optional[str] = COMMON["api_key"],
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve tool permission prompts"),
    resume: Optional[str] = typer.Option(None, "--resume", "-r", help="Resume a session id"),
) -> None:
    """Bare `redeye` opens the interactive operator console."""
    if ctx.invoked_subcommand is not None:
        return
    cfg = _load_cfg(config, provider, model, mode, base_url, api_key)
    from .tui.repl import run_repl

    run_repl(cfg, resume_id=resume, auto_yes=yes)


@app.command("run")
def run_cmd(
    goal: str = typer.Argument(..., help="Investigation objective"),
    config: Optional[str] = COMMON["config"],
    provider: Optional[str] = COMMON["provider"],
    model: Optional[str] = COMMON["model"],
    mode: Optional[str] = COMMON["mode"],
    base_url: Optional[str] = COMMON["base_url"],
    api_key: Optional[str] = COMMON["api_key"],
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve tool permission prompts"),
) -> None:
    cfg = _load_cfg(config, provider, model, mode, base_url, api_key)
    from .runner import run_oneshot

    run_oneshot(cfg, goal, auto_yes=yes)


@app.command("doctor")
def doctor(
    config: Optional[str] = COMMON["config"],
    provider: Optional[str] = COMMON["provider"],
) -> None:
    cfg = _load_cfg(config, provider, None, None, None, None)
    run_doctor(cfg, Console())


@app.command("sessions")
def sessions(config: Optional[str] = COMMON["config"]) -> None:
    from .session import list_sessions

    cfg = _load_cfg(config, None, None, None, None, None)
    console = Console()
    rows = list_sessions(cfg.sessions_dir)
    if not rows:
        console.print("[dim]no sessions yet[/dim]")
        return
    table = Table(title="RedEye sessions")
    table.add_column("id", style="bold")
    table.add_column("started")
    table.add_column("model", style="dim")
    table.add_column("goal")
    for s in rows[:30]:
        table.add_row(s.get("session_id", "?"), s.get("started", "?"),
                      s.get("model", "?"), (s.get("goal") or "")[:60])
    console.print(table)
    console.print("[dim]resume with: redeye --resume <id>  (or /resume <id> in the console)[/dim]")


@app.command("skills")
def skills_cmd(config: Optional[str] = COMMON["config"]) -> None:
    from .skills import load_skills

    cfg = _load_cfg(config, None, None, None, None, None)
    console = Console()
    for s in sorted(load_skills(cfg.skills_dir).values(), key=lambda x: x.name):
        console.print(f"  [bold]{s.name}[/bold] [{s.origin}] — {s.description}")


@app.command("version")
def version() -> None:
    Console().print(f"RedEye v{__version__}")


# ---------------------------------------------------------------------- #
def run_doctor(cfg: Config, console: Console) -> None:
    """Environment & connectivity self-check (also available as /doctor)."""
    import httpx

    table = Table(title="RedEye self-check")
    table.add_column("check", style="bold")
    table.add_column("status")
    table.add_column("detail", style="dim")

    def row(name: str, ok: bool | None, detail: str) -> None:
        icon = "[green]✓[/green]" if ok else ("[red]✗[/red]" if ok is False else "[yellow]–[/yellow]")
        table.add_row(name, icon, detail)

    row("config", True, f"provider={cfg.provider} model={cfg.model} mode={cfg.permission_mode}")
    row("home", cfg.home.exists() or True, str(cfg.home))

    if cfg.provider == "echo":
        row("llm", True, "echo provider (offline demo mode)")
    elif cfg.provider in ("ollama", "lmstudio"):
        try:
            r = httpx.get((cfg.base_url or "").removesuffix("/v1") + "/api/tags"
                          if cfg.provider == "ollama" else cfg.base_url + "/models",
                          timeout=4)
            row("llm", r.status_code == 200, f"{cfg.base_url} reachable")
        except Exception as exc:
            row("llm", False, f"{cfg.base_url} unreachable: {exc}")
    else:
        row("api key", bool(cfg.api_key),
            "set" if cfg.api_key else f"MISSING — set {PROVIDERS[cfg.provider].get('api_key_env') or 'REDEYE_API_KEY'}")

    for name, key in (("brave", cfg.brave_api_key), ("tavily", cfg.tavily_api_key),
                      ("hibp", cfg.hibp_api_key), ("github", cfg.github_token),
                      ("etherscan", cfg.etherscan_api_key)):
        row(f"key:{name}", None, "set" if key else "not set (optional)")

    try:
        r = httpx.get("https://www.gravatar.com/204", timeout=6, follow_redirects=True)
        row("egress", r.status_code < 500, f"HTTP {r.status_code}")
    except Exception as exc:
        row("egress", False, str(exc))

    if cfg.mcp_servers:
        from .mcp_client import McpManager

        mgr = McpManager(cfg.mcp_servers)
        mgr.start()
        row("mcp", not mgr.errors,
            f"connected: {', '.join(mgr.connected) or 'none'}" +
            (f" | errors: {mgr.errors}" if mgr.errors else ""))
        mgr.shutdown()
    else:
        row("mcp", None, "no servers configured")

    console.print(table)


def main() -> None:
    """Console-script entry point (`redeye`)."""
    app()


if __name__ == "__main__":
    main()
