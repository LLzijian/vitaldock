"""End-to-end official SDK client -> stdio subprocess -> local read-only vault."""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from vitaldock.model import digest
from vitaldock.store import Vault


@unittest.skipUnless(importlib.util.find_spec("mcp"), "install .[mcp] to test MCP transport")
class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_scopes_pagination_and_readonly(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.json"
            points = [{"key": "DATA_POINT_DYNAMIC_HEARTRATE", "startTime": 1792886400000,
                       "endTime": 1792886460000, "value": str(value)} for value in (70, 71)]
            source.write_text(json.dumps([{"samplePoints": points}]), encoding="utf-8")
            vault = Vault(root / "vault")
            vault.import_huawei(source)
            before = digest(vault.database.read_bytes())
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "vitaldock", "--vault", str(vault.root), "mcp", "--subject", "self",
                      "--metrics", "heart_rate"],
                env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                     "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    self.assertEqual({t.name for t in tools},
                                     {"health_coverage", "health_query", "health_provenance"})
                    self.assertTrue(all(t.annotations.readOnlyHint for t in tools))
                    result = await session.call_tool("health_query", {
                        "metric": "heart_rate", "since": "2026-10-01T00:00:00Z",
                        "until": "2026-11-01T00:00:00Z", "limit": 1})
                    self.assertFalse(result.isError)
                    payload = json.loads(result.content[0].text)
                    self.assertTrue(payload["has_more"])
                    self.assertEqual(len(payload["records"]), 1)
                    denied = await session.call_tool("health_query", {
                        "metric": "body_weight", "since": "2026-10-01T00:00:00Z",
                        "until": "2026-11-01T00:00:00Z"})
                    self.assertTrue(denied.isError)
                    coverage = await session.call_tool("health_coverage", {})
                    self.assertFalse(coverage.isError)
                    provenance = await session.call_tool("health_provenance", {
                        "record_id": payload["records"][0]["id"]})
                    self.assertFalse(provenance.isError)
            self.assertEqual(digest(vault.database.read_bytes()), before)
