from __future__ import annotations

import asyncio
import shutil
import threading
from typing import Any

from ..searcher.mcp_client import MCPClientContext


class ZoteroClientManager:
    """Owns a single MCPClientContext for the zotero-mcp server.

    Shared between ZoteroSearcher, ZoteroChecker, and ZoteroExporter
    to avoid spawning multiple server processes.

    Uses a dedicated background event loop thread so that the anyio task group
    inside stdio_client stays alive across multiple synchronous call sites.
    Calling run_async() on coroutines keeps them all in the same loop.
    """

    def __init__(self, config: dict[str, Any]):
        zotero_cfg = config.get("zotero", {})

        # Only inject non-empty values; let the subprocess inherit real env vars
        # for any credentials left blank in config.
        env: dict[str, str] = {}
        if zotero_cfg.get("api_key"):
            env["ZOTERO_API_KEY"] = zotero_cfg["api_key"]
        if zotero_cfg.get("library_id"):
            env["ZOTERO_LIBRARY_ID"] = str(zotero_cfg["library_id"])
        if zotero_cfg.get("library_type"):
            env["ZOTERO_LIBRARY_TYPE"] = zotero_cfg["library_type"]

        # Access mode: "local" (requires Zotero desktop running) or "api" (Zotero web API).
        # Set ZOTERO_LOCAL=true for local mode, leave unset/false for web API mode.
        access_mode = zotero_cfg.get("access_mode", "api")
        if access_mode == "local":
            env["ZOTERO_LOCAL"] = "true"

        command = shutil.which("zotero-mcp") or "zotero-mcp"
        self._client = MCPClientContext(
            command=command,
            args=["serve"],
            env=env if env else None,
        )
        self._connected = False

        # Dedicated event loop + thread — keeps the anyio task group alive
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Start the background loop, spawn the server, initialize the session."""
        self._thread.start()
        self._run_sync(self._client.connect())
        self._connected = True

    def disconnect(self) -> None:
        """Tear down the session and stop the background loop."""
        if self._connected:
            try:
                self._run_sync(self._client.disconnect())
            except Exception:
                pass
            self._connected = False
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)

    # ------------------------------------------------------------------
    # Public API for Zotero classes
    # ------------------------------------------------------------------

    def run_async(self, coro) -> Any:
        """Run a coroutine on the persistent event loop (blocking call)."""
        if not self._connected:
            raise RuntimeError("ZoteroClientManager: call connect() first.")
        return self._run_sync(coro)

    @property
    def client(self) -> MCPClientContext:
        if not self._connected:
            raise RuntimeError("ZoteroClientManager: call connect() first.")
        return self._client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Target function for the background thread — runs the event loop forever."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_sync(self, coro) -> Any:
        """Schedule a coroutine on the background loop and block until done."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()
