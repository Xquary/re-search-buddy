from __future__ import annotations

import asyncio
import json
import shutil
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClientContext:
    """Manages an MCP server subprocess and provides tool-calling helpers."""

    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None):
        self.server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env,
        )
        self._session: ClientSession | None = None
        self._read_stream = None
        self._write_stream = None
        self._cm_stack: list[Any] = []

    async def connect(self) -> None:
        """Spawn the server subprocess and initialize the MCP session."""
        self._stdio_cm = stdio_client(self.server_params)
        read_stream, write_stream = await self._stdio_cm.__aenter__()
        self._read_stream = read_stream
        self._write_stream = write_stream

        self._session_cm = ClientSession(read_stream, write_stream)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()

    async def disconnect(self) -> None:
        """Shut down the session and server subprocess."""
        if self._session is not None:
            await self._session_cm.__aexit__(None, None, None)
            self._session = None
        if hasattr(self, "_stdio_cm"):
            await self._stdio_cm.__aexit__(None, None, None)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a tool on the MCP server and return the result content."""
        if self._session is None:
            raise RuntimeError("MCP session not connected. Call connect() first.")
        result = await self._session.call_tool(tool_name, arguments or {})
        # MCP returns list of TextContent; concatenate them
        texts = []
        for item in result.content:
            if hasattr(item, "text"):
                texts.append(item.text)
        return "\n".join(texts) if texts else str(result.content)

    async def list_tools(self) -> list[str]:
        """List available tools on the server."""
        if self._session is None:
            raise RuntimeError("MCP session not connected.")
        result = await self._session.list_tools()
        return [t.name for t in result.tools]


def run_async(coro):
    """Utility to run an async coroutine from sync code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # We're inside an existing event loop (unlikely for CLI, but safe)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)
