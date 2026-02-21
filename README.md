# MCP to Skill Converter

Convert any MCP server into a Claude Skill with ~90% context savings. Supports both **stdio** and **HTTP** (Streamable HTTP) transports.

## Requirements

- [uv](https://docs.astral.sh/uv/) (no project setup needed -- dependencies are inline)

## Quick Start

```bash
# Convert a single MCP server config
./mcp_to_skill.py --mcp-config my-server.json --output-dir ./skills/my-server

# Convert a multi-server config (one skill per server)
./mcp_to_skill.py --mcp-config example-mcp.json --output-dir ./skills

# Convert only a specific server from a multi-server config
./mcp_to_skill.py --mcp-config example-mcp.json --server youtrack

# Omit --output-dir to default to ./skills/<server-name>
./mcp_to_skill.py --mcp-config example-mcp.json
```

## Config Format

The converter accepts the standard `mcpServers` format used by Claude Desktop and other MCP clients.

### Multi-server config (recommended)

```json
{
  "mcpServers": {
    "github": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "ghp_..." }
    },
    "youtrack": {
      "url": "https://example.youtrack.cloud/mcp",
      "transport": "http",
      "headers": { "Authorization": "Bearer ..." }
    }
  }
}
```

### Single-server config (also works)

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-github"],
  "env": { "GITHUB_TOKEN": "ghp_..." }
}
```

## What Gets Generated

For each MCP server, the converter creates a skill directory:

```
skills/github/
  SKILL.md          # Instructions for Claude (tool list, usage pattern)
  executor.py       # Calls the MCP server at runtime (uv script, no install needed)
  mcp-config.json   # Server connection config
```

## Using a Generated Skill

### With Claude Code

```bash
cp -r skills/github ~/.claude/skills/
```

Claude discovers it automatically.

### Manual Testing

```bash
cd skills/github

# List available tools
./executor.py --list

# Get detailed schema for a tool
./executor.py --describe create_issue

# Call a tool
./executor.py --call '{"tool": "search_repositories", "arguments": {"query": "mcp"}}'
```

## How It Works

At conversion time, the script connects to the MCP server and introspects its tools. It then generates a `SKILL.md` containing tool names/descriptions and an `executor.py` that handles the actual MCP communication at runtime.

The executor has a `uv run --script` shebang with inline PEP 723 metadata, so dependencies (`mcp`, `httpx`) are resolved automatically on first run -- no virtual environment or install step required. Just run `./executor.py` directly.

**Context savings**: Instead of loading all tool schemas upfront (~500 tokens per tool), Claude loads only the skill metadata (~100 tokens) until the skill is actually used.

## Supported Transports

| Transport | Config key | Protocol |
|-----------|-----------|----------|
| stdio | `command` + `args` | Subprocess with JSON-RPC over stdin/stdout |
| HTTP | `url` | MCP Streamable HTTP (JSON-RPC over HTTP) |

The transport is auto-detected from the config: if `url` is present it uses HTTP, if `command` is present it uses stdio. You can also set `"transport"` explicitly.
