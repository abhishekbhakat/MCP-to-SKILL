#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.0.0",
#     "httpx",
# ]
# ///
"""
MCP to Skill Converter
======================
Converts any MCP server into a Claude Skill with dynamic tool invocation.

Supports both stdio and HTTP (Streamable HTTP) MCP transports.

Usage:
    ./mcp_to_skill.py --mcp-config config.json --output-dir ./skills/my-skill
    ./mcp_to_skill.py --mcp-config config.json  # generates into ./skills/<server-name> per server
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse


class MCPSkillGenerator:
    """Generate a Skill from a single MCP server configuration."""

    def __init__(self, server_config: Dict[str, Any], output_dir: Path, server_name: str):
        self.server_config = server_config
        self.output_dir = Path(output_dir)
        self.server_name = server_name
        self.transport = self._detect_transport()

    def _detect_transport(self) -> str:
        if "url" in self.server_config:
            return self.server_config.get("transport", "http")
        if "command" in self.server_config:
            return self.server_config.get("transport", "stdio")
        return self.server_config.get("transport", "stdio")

    async def generate(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Generating skill for MCP server: {self.server_name} (transport: {self.transport})")

        tools = await self._get_mcp_tools()

        self._generate_skill_md(tools)
        self._generate_executor()
        self._generate_config()

        print(f"  Skill generated at: {self.output_dir}")
        print(f"  Tools discovered: {len(tools)}")

    async def _get_mcp_tools(self) -> List[Dict[str, Any]]:
        if self.transport in ("http", "sse", "streamable-http"):
            return await self._get_tools_http()
        else:
            return await self._get_tools_stdio()

    async def _get_tools_http(self) -> List[Dict[str, Any]]:
        try:
            import httpx
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            url = self.server_config.get("url", "")
            headers = self.server_config.get("headers", {})

            http_client = httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(30, read=60))

            async with http_client:
                async with streamable_http_client(url=url, http_client=http_client) as (
                    read_stream,
                    write_stream,
                    _,
                ):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        response = await session.list_tools()
                        tools = [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": tool.inputSchema,
                            }
                            for tool in response.tools
                        ]
                        print(f"  Found {len(tools)} tools via HTTP")
                        return tools
        except ImportError:
            print("  Warning: mcp/httpx not installed, using mock tools")
            return self._get_mock_tools()
        except Exception as e:
            print(f"  Warning: Could not connect to HTTP MCP server: {e}")
            return self._get_mock_tools()

    async def _get_tools_stdio(self) -> List[Dict[str, Any]]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            command = self.server_config.get("command", "")
            args = self.server_config.get("args", [])
            env = self.server_config.get("env")

            server_params = StdioServerParameters(command=command, args=args, env=env)

            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    response = await session.list_tools()
                    tools = [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema,
                        }
                        for tool in response.tools
                    ]
                    print(f"  Found {len(tools)} tools via stdio")
                    return tools
        except ImportError:
            print("  Warning: mcp package not installed, using mock tools")
            return self._get_mock_tools()
        except Exception as e:
            print(f"  Warning: Could not connect to stdio MCP server: {e}")
            return self._get_mock_tools()

    def _get_mock_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "example_tool",
                "description": "Mock tool (could not connect to server at introspection time)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "First parameter"}
                    },
                    "required": ["param1"],
                },
            }
        ]

    def _generate_skill_md(self, tools: List[Dict[str, Any]]):
        tool_list = "\n".join(
            [f"- `{t['name']}`: {t.get('description', 'No description')}" for t in tools]
        )
        tool_count = len(tools)

        content = f"""---
name: {self.server_name}
description: Dynamic access to {self.server_name} MCP server ({tool_count} tools)
user-invocable: false
disable-model-invocation: false
---

# {self.server_name} Skill

This skill provides dynamic access to the {self.server_name} MCP server without loading all tool definitions into context.

## Available Tools

{tool_list}

## Usage Pattern

When the user's request matches this skill's capabilities:

**Step 1: Identify the right tool** from the list above

**Step 2: Generate a tool call** in this JSON format:

```json
{{
  "tool": "tool_name",
  "arguments": {{
    "param1": "value1"
  }}
}}
```

**Step 3: Execute via bash:**

```bash
cd $SKILL_DIR
./executor.py --call 'YOUR_JSON_HERE'
```

IMPORTANT: Replace $SKILL_DIR with the actual discovered path of this skill directory.

## Getting Tool Details

If you need detailed information about a specific tool's parameters:

```bash
cd $SKILL_DIR
./executor.py --describe tool_name
```

## Error Handling

If the executor returns an error:
- Check the tool name is correct
- Verify required arguments are provided
- Ensure the MCP server is accessible

---

*Auto-generated from MCP server configuration by mcp_to_skill.py*
"""
        skill_path = self.output_dir / "SKILL.md"
        skill_path.write_text(content)
        print(f"  Generated: {skill_path}")

    def _generate_executor(self):
        if self.transport in ("http", "sse", "streamable-http"):
            self._generate_http_executor()
        else:
            self._generate_stdio_executor()

    def _generate_stdio_executor(self):
        code = '''#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.0.0",
# ]
# ///
"""MCP Skill Executor - stdio transport"""

import json
import sys
import asyncio
import argparse
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(config, args):
    server_params = StdioServerParameters(
        command=config["command"],
        args=config.get("args", []),
        env=config.get("env"),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            if args.list:
                response = await session.list_tools()
                tools = [{"name": t.name, "description": t.description} for t in response.tools]
                print(json.dumps(tools, indent=2))

            elif args.describe:
                response = await session.list_tools()
                for tool in response.tools:
                    if tool.name == args.describe:
                        print(json.dumps({"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}, indent=2))
                        return
                print(f"Tool not found: {args.describe}", file=sys.stderr)
                sys.exit(1)

            elif args.call:
                call_data = json.loads(args.call)
                result = await session.call_tool(call_data["tool"], call_data.get("arguments", {}))
                for item in result.content:
                    if hasattr(item, "text"):
                        print(item.text)
                    else:
                        print(json.dumps(item.model_dump(), indent=2))
            else:
                parser.print_help()


def main():
    parser = argparse.ArgumentParser(description="MCP Skill Executor (stdio)")
    parser.add_argument("--call", help="JSON tool call to execute")
    parser.add_argument("--describe", help="Get tool schema")
    parser.add_argument("--list", action="store_true", help="List all tools")
    args = parser.parse_args()

    config_path = Path(__file__).parent / "mcp-config.json"
    if not config_path.exists():
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    asyncio.run(run(config, args))


if __name__ == "__main__":
    main()
'''
        executor_path = self.output_dir / "executor.py"
        executor_path.write_text(code)
        executor_path.chmod(0o755)
        print(f"  Generated: {executor_path}")

    def _generate_http_executor(self):
        code = '''#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.0.0",
#     "httpx",
# ]
# ///
"""MCP Skill Executor - HTTP (Streamable HTTP) transport"""

import json
import sys
import asyncio
import argparse
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run(config, args):
    url = config["url"]
    headers = config.get("headers", {})

    http_client = httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(30, read=60))

    async with http_client:
        async with streamable_http_client(url=url, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                if args.list:
                    response = await session.list_tools()
                    tools = [{"name": t.name, "description": t.description} for t in response.tools]
                    print(json.dumps(tools, indent=2))

                elif args.describe:
                    response = await session.list_tools()
                    for tool in response.tools:
                        if tool.name == args.describe:
                            print(json.dumps({"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}, indent=2))
                            return
                    print(f"Tool not found: {args.describe}", file=sys.stderr)
                    sys.exit(1)

                elif args.call:
                    call_data = json.loads(args.call)
                    result = await session.call_tool(call_data["tool"], call_data.get("arguments", {}))
                    for item in result.content:
                        if hasattr(item, "text"):
                            print(item.text)
                        else:
                            print(json.dumps(item.model_dump(), indent=2))
                else:
                    parser.print_help()


def main():
    parser = argparse.ArgumentParser(description="MCP Skill Executor (HTTP)")
    parser.add_argument("--call", help="JSON tool call to execute")
    parser.add_argument("--describe", help="Get tool schema")
    parser.add_argument("--list", action="store_true", help="List all tools")
    args = parser.parse_args()

    config_path = Path(__file__).parent / "mcp-config.json"
    if not config_path.exists():
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    asyncio.run(run(config, args))


if __name__ == "__main__":
    main()
'''
        executor_path = self.output_dir / "executor.py"
        executor_path.write_text(code)
        executor_path.chmod(0o755)
        print(f"  Generated: {executor_path}")

    def _generate_config(self):
        config_path = self.output_dir / "mcp-config.json"
        with open(config_path, "w") as f:
            json.dump(self.server_config, f, indent=2)
        print(f"  Generated: {config_path}")


def parse_mcp_config(config_path: str) -> Dict[str, Dict[str, Any]]:
    """Parse MCP config file, handling both flat and nested mcpServers format.

    Returns a dict of {server_name: server_config}.
    """
    with open(config_path) as f:
        raw = json.load(f)

    # Nested format: {"mcpServers": {"name": {config}, ...}}
    if "mcpServers" in raw:
        return raw["mcpServers"]

    # Flat format with explicit name: {"name": "foo", "command": "..."}
    if "name" in raw and ("command" in raw or "url" in raw):
        name = raw.pop("name")
        return {name: raw}

    # Flat format without name: {"command": "..."}
    if "command" in raw or "url" in raw:
        name = Path(config_path).stem
        return {name: raw}

    print(f"Error: Unrecognized config format in {config_path}", file=__import__("sys").stderr)
    __import__("sys").exit(1)


async def convert_mcp_to_skill(
    mcp_config_path: str,
    output_dir: Optional[str] = None,
    server_name: Optional[str] = None,
):
    servers = parse_mcp_config(mcp_config_path)

    if server_name:
        if server_name not in servers:
            available = ", ".join(servers.keys())
            print(f"Error: Server '{server_name}' not found in config.", file=__import__("sys").stderr)
            print(f"Available servers: {available}", file=__import__("sys").stderr)
            __import__("sys").exit(1)
        servers = {server_name: servers[server_name]}

    print(f"Converting {len(servers)} server(s)\n")

    for name, config in servers.items():
        if output_dir and len(servers) == 1:
            dest = Path(output_dir)
        else:
            base = Path(output_dir) if output_dir else Path("./skills")
            dest = base / name

        generator = MCPSkillGenerator(config, dest, name)
        await generator.generate()
        print()

    print("Done. To use a generated skill:")
    print("  cp -r <skill-dir> ~/.claude/skills/")


def main():
    parser = argparse.ArgumentParser(
        description="Convert MCP server(s) to Claude Skill(s)",
        epilog="Example: ./mcp_to_skill.py --mcp-config config.json --output-dir ./skills/github",
    )
    parser.add_argument("--mcp-config", required=True, help="Path to MCP server configuration JSON")
    parser.add_argument("--output-dir", help="Output directory (defaults to ./skills/<server-name>)")
    parser.add_argument("--server", help="Convert only this server from a multi-server config")
    args = parser.parse_args()

    asyncio.run(convert_mcp_to_skill(args.mcp_config, args.output_dir, args.server))


if __name__ == "__main__":
    main()
