"""One-shot (non-interactive) investigation runner."""
from __future__ import annotations

from rich.console import Console

from .config import Config
from .runtime import build_runtime
from .tui.render import Renderer, render_final


def run_oneshot(cfg: Config, goal: str, *, auto_yes: bool = False) -> int:
    console = Console()
    renderer = Renderer(console)
    console.print(f"[bold red]RedEye[/bold red] · {cfg.provider}:{cfg.model} · mode={cfg.permission_mode}")
    console.print(f"[dim]objective: {goal}[/dim]\n")

    runtime = build_runtime(cfg, goal=goal)
    try:
        if auto_yes:
            approval = lambda name, tier, args: (True, False)  # noqa: E731
        elif console.is_interactive:
            approval = renderer.approval
        else:
            # headless without --yes: deny anything that asks
            def approval(name, tier, args):
                renderer.console.print(f"[yellow]denied (headless, no --yes): {name}[/yellow]")
                return (False, False)

        agent = runtime.make_agent(renderer.emit, approval)
        try:
            result = agent.run(goal, prior_messages=runtime.session.messages)
        except KeyboardInterrupt:
            console.print("\n[yellow]interrupted[/yellow]")
            return 130

        render_final(console, result.final_text)
        console.print(
            f"[dim]session {runtime.session.session_id} · {result.stats.get('steps', 0)} steps · "
            f"{len(runtime.case.findings)} findings"
            + (f" · halted: {result.stopped_reason}" if result.stopped_reason else "")
            + "[/dim]"
        )
        return 0
    finally:
        runtime.shutdown()
