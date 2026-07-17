"""MCP (Model Context Protocol) client bridge.

Connects to MCP servers configured in ~/.redeye/config.toml, discovers their
tools, and exposes them through RedEye's registry as mcp__<server>__<tool>.

Design: all MCP I/O runs on a single background asyncio event loop in a daemon
thread, so the synchronous agent loop can call MCP tools without caring about
async. Servers that fail to connect are reported and skipped — never fatal.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional

from .config import McpServerConfig
from .tools.base import Tool, ToolRegistry, ToolResult


class McpManager:
    def __init__(self, servers: list[McpServerConfig]):
        self.servers = [s for s in servers if s.enabled]
        self.errors: dict[str, str] = {}
        self.connected: list[str] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._sessions: dict[str, Any] = {}
        self._ready = threading.Event()
        self._shutdown = False

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if not self.servers:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="redeye-mcp")
        self._thread.start()
        self._ready.wait(timeout=60)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_all())
        finally:
            self._ready.set()
        self._loop.run_forever()

    async def _connect_all(self) -> None:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            for s in self.servers:
                self.errors[s.name] = "mcp package not installed (pip install mcp)"
            return

        for srv in self.servers:
            try:
                if srv.transport == "stdio":
                    if not srv.command:
                        raise ValueError("stdio server requires 'command'")
                    params = StdioServerParameters(
                        command=srv.command, args=srv.args,
                        env={**srv.env} if srv.env else None,
                    )
                    ctx = stdio_client(params)
                elif srv.transport == "sse":
                    from mcp.client.sse import sse_client

                    if not srv.url:
                        raise ValueError("sse server requires 'url'")
                    ctx = sse_client(srv.url)
                else:
                    raise ValueError(f"unsupported transport {srv.transport!r}")

                read, write = await ctx.__aenter__()
                session = ClientSession(read, write)
                await session.__aenter__()
                await session.initialize()
                self._sessions[srv.name] = (session, ctx)
                self.connected.append(srv.name)
            except Exception as exc:  # noqa: BLE001 — a bad server must not kill RedEye
                self.errors[srv.name] = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ #
    def bridge_tools(self, registry: ToolRegistry) -> int:
        """Discover tools from every connected server and register them."""
        count = 0
        for name in self.connected:
            session, _ = self._sessions[name]
            fut = asyncio.run_coroutine_threadsafe(session.list_tools(), self._loop)
            try:
                result = fut.result(timeout=30)
            except Exception as exc:  # noqa: BLE001
                self.errors[name] = f"list_tools failed: {exc}"
                continue
            for t in result.tools:
                full_name = f"mcp__{name}__{t.name}"
                readonly = bool(getattr(getattr(t, "annotations", None), "readOnlyHint", False))
                schema = dict(t.inputSchema or {})
                schema.pop("$schema", None)
                schema.setdefault("type", "object")
                schema.setdefault("properties", {})

                def make_handler(server: str, tool_name: str):
                    def handler(**kwargs: Any) -> ToolResult:
                        return self._call(server, tool_name, kwargs)

                    return handler

                registry.register(
                    Tool(
                        name=full_name,
                        description=f"[MCP:{name}] {t.description or t.name}",
                        parameters=schema,
                        handler=make_handler(name, t.name),
                        tier="passive" if readonly else "sensitive",
                        timeout=60.0,
                        origin=f"mcp:{name}",
                    )
                )
                count += 1
        return count

    def _call(self, server: str, tool: str, args: dict[str, Any]) -> ToolResult:
        entry = self._sessions.get(server)
        if not entry:
            return ToolResult.error(f"MCP server {server!r} is not connected")
        session, _ = entry
        fut = asyncio.run_coroutine_threadsafe(session.call_tool(tool, args), self._loop)
        try:
            result = fut.result(timeout=60)
        except Exception as exc:  # noqa: BLE001
            return ToolResult.error(f"MCP call {server}/{tool} failed: {exc}")
        texts: list[str] = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            texts.append(text if text is not None else str(block))
        content = "\n".join(texts) or "(empty result)"
        is_error = bool(getattr(result, "isError", False))
        return ToolResult(ok=not is_error, content=content if not is_error else f"ERROR: {content}")

    def shutdown(self) -> None:
        if self._shutdown or not self._loop:
            return
        self._shutdown = True

        async def _close() -> None:
            for session, ctx in self._sessions.values():
                try:
                    await session.__aexit__(None, None, None)
                    await ctx.__aexit__(None, None, None)
                except Exception:
                    pass

        try:
            asyncio.run_coroutine_threadsafe(_close(), self._loop).result(timeout=10)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
