# Machine-readable agent interface

`mcp-tools.json` contains tool names, descriptions, input/output schemas and
read-only annotations generated from the actual MCP server. This file describes
the server with wellness and streams enabled; runtime discovery reflects the
permissions selected at startup.

Discover the installed version without credentials or network access:

```text
vitaldock agent-tools --wellness --streams
```

Store its JSON output as UTF-8 when updating this file. The regression suite
compares the published manifest with runtime discovery. The manifest contains
schemas only, never personal observations or API keys.

See [the agent API guide](../docs/agent-api.md) for transport, configuration,
status meanings, JSON commands and Python embedding.
