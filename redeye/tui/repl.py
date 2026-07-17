"""Interactive REPL — the RedEye operator console."""
from __future__ import annotations

from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console

from .. import __version__
from ..config import Config
from ..runtime import Runtime, build_runtime
from ..session import Session
from ..case import CaseStore
from .commands import handle_command
from .render import Renderer, print_banner, render_final

SLASH = ["/help", "/model", "/mode", "/skills", "/skill", "/tools", "/mcp", "/case",
         "/report", "/sessions", "/resume", "/new", "/doctor", "/clear", "/exit"]


def run_repl(cfg: Config, resume_id: str | None = None, auto_yes: bool = False) -> None:
    console = Console()
    renderer = Renderer(console)

    session, case = None, None
    if resume_id:
        path = cfg.sessions_dir / f"{resume_id}.jsonl"
        if not path.exists():
            console.print(f"[red]no session {resume_id!r}[/red]")
            return
        session = Session.resume(path)
        case_path = cfg.sessions_dir / f"{resume_id}.case.json"
        case = CaseStore.load(case_path) if case_path.exists() else None
        console.print(f"[green]resumed session {resume_id} ({len(session.messages)} messages)[/green]")

    runtime = build_runtime(cfg, goal=session.meta.get("goal", "") if session else "",
                            session=session, case=case)
    print_banner(console, __version__, runtime.llm.model, runtime.policy.mode,
                 len(runtime.skills), len(runtime.registry.names()))

    if runtime.mcp:
        for name, err in runtime.mcp.errors.items():
            console.print(f"[yellow]MCP {name}: {err}[/yellow]")
        if runtime.mcp.connected:
            console.print(f"[dim]MCP connected: {', '.join(runtime.mcp.connected)}[/dim]")

    prompt = PromptSession(
        history=FileHistory(str(cfg.home / "history")),
        completer=WordCompleter(SLASH, sentence=True),
    )

    try:
        while True:
            try:
                line = prompt.prompt("redeye ❯ ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]interrupted — /exit to quit[/dim]")
                continue
            if not line:
                continue

            if line.startswith("/"):
                parts = line.split(maxsplit=1)
                cmd, arg = parts[0].lower(), (parts[1].strip() if len(parts) > 1 else "")
                if cmd == "/new":
                    runtime.shutdown()
                    runtime = build_runtime(cfg, goal="")
                    console.print(f"[green]new session {runtime.session.session_id}[/green]")
                    continue
                if cmd == "/resume" and arg:
                    path = cfg.sessions_dir / f"{arg}.jsonl"
                    if not path.exists():
                        console.print(f"[red]no session {arg!r}[/red]")
                        continue
                    runtime.shutdown()
                    s = Session.resume(path)
                    cp = cfg.sessions_dir / f"{arg}.case.json"
                    c = CaseStore.load(cp) if cp.exists() else None
                    runtime = build_runtime(cfg, goal=s.meta.get("goal", ""), session=s, case=c)
                    console.print(f"[green]resumed {arg}[/green]")
                    continue
                if not handle_command(line, runtime, console):
                    break
                continue

            # ---- investigation ----
            if not runtime.case.goal:
                runtime.case.goal = line
                runtime.case.save()
            agent = runtime.make_agent(renderer.emit, _approval(renderer, auto_yes))
            try:
                result = agent.run(line, prior_messages=runtime.session.messages)
            except KeyboardInterrupt:
                console.print("\n[yellow]run interrupted by operator[/yellow]")
                continue
            render_final(console, result.final_text)
            console.print(
                f"[dim]session {runtime.session.session_id} · {result.stats.get('steps', 0)} steps · "
                f"{len(runtime.case.findings)} findings[/dim]\n"
            )
    finally:
        runtime.shutdown()
        console.print("[dim]RedEye out. Stay lawful, stay curious.[/dim]")


def _approval(renderer: Renderer, auto_yes: bool):
    if auto_yes:
        return lambda name, tier, args: (True, False)
    return renderer.approval
