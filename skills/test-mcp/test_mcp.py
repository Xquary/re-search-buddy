"""Quick connectivity test for MCP servers."""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Use the project's venv Python
PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")


async def test_server(name: str, command: str, args: list[str], test_tool: str, test_args: dict) -> None:
    """Connect to an MCP server, list tools, and call one test tool."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"Command: {command} {' '.join(args)}")
    print(f"{'='*60}")

    params = StdioServerParameters(command=command, args=args)

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # List tools
                tools_result = await session.list_tools()
                tools = [t.name for t in tools_result.tools]
                print(f"Available tools ({len(tools)}): {tools}")

                # Call test tool
                print(f"\nCalling: {test_tool}({json.dumps(test_args, indent=2)})")
                result = await session.call_tool(test_tool, test_args)
                for item in result.content:
                    text = item.text if hasattr(item, "text") else str(item)
                    # Print first 500 chars to keep output manageable
                    print(f"\nResult (truncated):\n{text[:500]}")
                    if len(text) > 500:
                        print(f"... ({len(text)} chars total)")

                print(f"\n✅ {name}: SUCCESS")

    except Exception as e:
        print(f"\n❌ {name}: FAILED — {type(e).__name__}: {e}")


async def main():
    servers_to_test = sys.argv[1:] if len(sys.argv) > 1 else ["arxiv", "scholar", "cnki"]

    tests = {
        "arxiv": {
            "command": shutil.which("uv") or "uv",
            "args": ["tool", "run", "arxiv-mcp-server"],
            "test_tool": "search_papers",
            "test_args": {"query": "transformer attention mechanism", "max_results": 3},
        },
        "scholar": {
            "command": VENV_PYTHON,
            "args": ["mcp_servers/google_scholar/google_scholar_server.py"],
            "test_tool": "search_google_scholar_key_words",
            "test_args": {"query": "attention is all you need", "num_results": 3},
        },
        "cnki": {
            "command": "npx",
            "args": ["-y", "chrome-devtools-mcp@latest"],
            "test_tool": "navigate_page",
            "test_args": {"url": "https://kns.cnki.net/kns8s/search"},
            # Note: requires Chrome running with --remote-debugging-port=9222
        },
    }

    for name in servers_to_test:
        if name in tests:
            t = tests[name]
            await test_server(name, t["command"], t["args"], t["test_tool"], t["test_args"])
        else:
            print(f"Unknown server: {name}. Available: {list(tests.keys())}")

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
