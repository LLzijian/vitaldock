"""A real stdio MCP client example; reads credentials in the child server only."""

import argparse
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def call(day):
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "vitaldock", "mcp-live", "--wellness"])
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            result = await session.call_tool("connection_status", {"day": day})
            payload = result.structuredContent
            if payload is None:
                payload = [item.text for item in result.content if item.type == "text"]
            print(json.dumps({"tools": names, "is_error": result.isError, "result": payload},
                             ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    asyncio.run(call(parser.parse_args().day))
