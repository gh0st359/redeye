"""Terminal rendering: banner, streaming text, tool-call panels, approvals."""
from __future__ import annotations

import json
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

BANNER = r"""
    ____           ________
   / __ \___  ____/ / ____/_  _____
  / /_/ / _ \/ __  / / __/ / / / _ \
 / _, _/  __/ /_/ / /___/ /_/ /  __/
/_/ |_|\___/\__,_/_____/\__, /\___/
                       /____/   v{version}
"""

TIER_STYLE = {"passive": "green", "active": "yellow", "sensitive": "red"}


class Renderer:
    def __init__(self, console: Console | None = None, verbose: bool = True):
        self.console = console or Console()
        self.verbose = verbose
        self._stream_open = False  # a token stream is on the terminal line

    # ------------------------------------------------------------ events #
    def emit(self, kind: str, data: dict) -> None:
        handler = getattr(self, f"on_{kind}", None)
        if handler:
            handler(data)

    def _close_stream(self) -> None:
        if self._stream_open:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._stream_open = False

    def on_token(self, data: dict) -> None:
        sys.stdout.write(data["text"])
        sys.stdout.flush()
        self._stream_open = True

    def on_step(self, data: dict) -> None:
        self._close_stream()
        if self.verbose:
            self.console.print(f"\n[dim]── step {data['n']} ──[/dim]")

    def on_assistant_turn_end(self, data: dict) -> None:
        self._close_stream()

    def on_tool_call(self, data: dict) -> None:
        self._close_stream()
        name, tier = data["name"], data["tier"]
        style = TIER_STYLE.get(tier, "white")
        args = json.dumps(data.get("args", {}), ensure_ascii=False)
        if len(args) > 200:
            args = args[:200] + "…"
        flag = " [bold red](awaiting approval)[/bold red]" if data.get("needs_approval") else ""
        self.console.print(f"  [bold {style}]▶ {name}[/bold {style}] [dim]{args}[/dim]{flag}")

    def on_tool_result(self, data: dict) -> None:
        self._close_stream()
        ok = data["ok"]
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
        elapsed = data.get("elapsed", 0.0)
        trunc = " [dim](truncated)[/dim]" if data.get("truncated") else ""
        preview = data.get("preview", "")
        self.console.print(f"    {icon} [dim]{elapsed}s{trunc}[/dim] {preview}")

    def on_steering(self, data: dict) -> None:
        self._close_stream()
        self.console.print(f"    [yellow]⚑ harness: {data['message']}[/yellow]")

    def on_warning(self, data: dict) -> None:
        self._close_stream()
        self.console.print(f"[bold yellow]⚠ {data['message']}[/bold yellow]")

    def on_report(self, data: dict) -> None:
        self._close_stream()
        self.console.print(f"[bold green]◈ report saved:[/bold green] {data['path']}")

    # ------------------------------------------------------------ prompts #
    def approval(self, name: str, tier: str, args: dict) -> tuple[bool, bool]:
        """Interactive approval prompt. Returns (approved, remember)."""
        self._close_stream()
        pretty = json.dumps(args, ensure_ascii=False, indent=2)
        if len(pretty) > 800:
            pretty = pretty[:800] + "\n…"
        self.console.print(
            Panel(
                pretty,
                title=f"[bold]{name}[/bold] — {tier} tool requesting approval",
                border_style=TIER_STYLE.get(tier, "white"),
            )
        )
        choice = Prompt.ask(
            "  Allow?",
            choices=["y", "n", "a", "v"],
            default="n",
            show_choices=True,
        )
        # y = yes once, n = no once, a = always allow this tool, v = never this tool
        return (choice in ("y", "a"), choice in ("a", "v"))


def print_banner(console: Console, version: str, model: str, mode: str, skills: int, tools: int) -> None:
    console.print(Text(BANNER.format(version=version), style="bold red"))
    console.print(
        f"[dim]model[/dim] [bold]{model}[/bold]  [dim]│ mode[/dim] [bold]{mode}[/bold]  "
        f"[dim]│ skills[/dim] {skills}  [dim]│ tools[/dim] {tools}"
    )
    console.print("[dim]type an objective to start an investigation · /help for commands · /exit to quit[/dim]\n")


def render_final(console: Console, text: str) -> None:
    console.print()
    console.print(Panel(Markdown(text or "_(empty)_"), title="[bold]Assessment[/bold]", border_style="red"))
