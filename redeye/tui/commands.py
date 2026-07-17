"""Slash commands for the interactive REPL."""
from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ..permissions import MODE_DESCRIPTIONS
from ..session import list_sessions

HELP = """\
**Investigation**
  just type a goal — e.g. `map the infrastructure of example.com`
  RedEye plans, collects, records findings, and writes a report.

**Commands**
  /help                 this help
  /model [name]         show or switch the model (e.g. /model openai/gpt-4o)
  /mode [mode]          show or switch permission mode: readonly | balanced | fullauto
  /skills               list loaded tradecraft skills
  /skill <name>         print a skill's full playbook
  /tools                list registered tools and risk tiers
  /mcp                  MCP server status
  /case                 show findings in the current case file
  /report               print report path for the current session
  /sessions             list past sessions
  /resume <id>          resume a past session (new case goal continues its transcript)
  /new                  start a fresh session + case file
  /doctor               environment & connectivity self-check
  /clear                clear the screen
  /exit                 quit

**Tips**
  · Quote exact strings for search: `"jane.doe@example.com"`
  · Runs are bounded by step/time budgets — the harness stops loops itself.
  · Every run ends with a Markdown report in ~/.redeye/reports/.
"""


def handle_command(line: str, runtime, console: Console) -> bool:
    """Returns True if the REPL should continue, False to exit."""
    parts = line.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/exit", "/quit"):
        return False
    if cmd == "/help":
        console.print(Markdown(HELP))
    elif cmd == "/model":
        if arg:
            runtime.llm.model = arg
            runtime.cfg.model = arg
            console.print(f"[green]model → {arg}[/green]")
        else:
            console.print(f"model: [bold]{runtime.llm.model}[/bold] (provider: {runtime.cfg.provider})")
    elif cmd == "/mode":
        if arg:
            try:
                runtime.policy.set_mode(arg)
                runtime.cfg.permission_mode = arg
                console.print(f"[green]permission mode → {arg}[/green]")
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
        else:
            console.print(f"mode: [bold]{runtime.policy.mode}[/bold] — {MODE_DESCRIPTIONS[runtime.policy.mode]}")
    elif cmd == "/skills":
        table = Table(title="Tradecraft skills", show_lines=False)
        table.add_column("name", style="bold")
        table.add_column("origin", style="dim")
        table.add_column("description")
        for s in sorted(runtime.skills.values(), key=lambda x: x.name):
            table.add_row(s.name, s.origin, s.description)
        console.print(table)
    elif cmd == "/skill":
        skill = runtime.skills.get(arg)
        if not skill:
            console.print(f"[red]unknown skill {arg!r}[/red]")
        else:
            console.print(Panel(Markdown(skill.body), title=f"skill: {skill.name}", border_style="blue"))
    elif cmd == "/tools":
        tiers = runtime.registry.tiers()
        table = Table(title=f"{len(tiers)} tools", show_lines=False)
        table.add_column("tool", style="bold")
        table.add_column("tier")
        for name in sorted(tiers):
            style = {"passive": "green", "active": "yellow", "sensitive": "red"}.get(tiers[name], "white")
            table.add_row(name, f"[{style}]{tiers[name]}[/{style}]")
        console.print(table)
    elif cmd == "/mcp":
        mcp = runtime.mcp
        if not mcp:
            console.print("[dim]no MCP servers configured — see config.example.toml[/dim]")
        else:
            console.print(f"connected: {', '.join(mcp.connected) or 'none'}")
            for name, err in mcp.errors.items():
                console.print(f"[red]{name}: {err}[/red]")
    elif cmd == "/case":
        console.print(runtime.case.summary())
    elif cmd == "/report":
        console.print(f"case file: {runtime.case.path}")
        console.print(f"reports dir: {runtime.cfg.reports_dir}")
    elif cmd == "/sessions":
        sessions = list_sessions(runtime.cfg.sessions_dir)
        if not sessions:
            console.print("[dim]no past sessions[/dim]")
        for s in sessions[:20]:
            console.print(f"  [bold]{s.get('session_id')}[/bold]  {s.get('started', '')}  [dim]{(s.get('goal') or '')[:70]}[/dim]")
    elif cmd == "/resume":
        console.print("[yellow]/resume is handled by the REPL (reloads runtime)[/yellow]")
    elif cmd == "/new":
        console.print("[yellow]/new is handled by the REPL (rebuilds runtime)[/yellow]")
    elif cmd == "/doctor":
        from ..cli import run_doctor

        run_doctor(runtime.cfg, console)
    elif cmd == "/clear":
        console.clear()
    else:
        console.print(f"[red]unknown command {cmd!r} — /help[/red]")
    return True
