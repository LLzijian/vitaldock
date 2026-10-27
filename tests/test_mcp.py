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

    async def test_live_stdio_refetches_and_never_substitutes_an_old_run(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as folder:
            wrapper = Path(folder) / "live_fixture.py"
            wrapper.write_text('''
from test_live import FakeClient, NOW, run
import vitaldock.running as running
from vitaldock.live_mcp import build_live_server

original = running.post_run_context
def at_fixed_time(*args, **kwargs):
    return original(*args, **kwargs, now=NOW)
running.post_run_context = at_fixed_time

class ArrivingClient(FakeClient):
    def activities(self, *args):
        self.calls.append("activities")
        return [] if len(self.calls) == 1 else [run()]

build_live_server(ArrivingClient()).run(transport="stdio")
''', encoding="utf-8")
            project = Path(__file__).resolve().parents[1]
            params = StdioServerParameters(command=sys.executable, args=[str(wrapper)], env={
                "PYTHONPATH": os.pathsep.join([str(project / "src"), str(project / "tests")]),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    self.assertEqual([t.name for t in tools], ["running_context"])
                    self.assertTrue(tools[0].annotations.readOnlyHint)
                    self.assertTrue(tools[0].annotations.openWorldHint)
                    args = {"day":"2026-10-27", "completed_after":"2026-10-27T15:00:00+08:00"}
                    first = await session.call_tool("running_context", args)
                    first = json.loads(first.content[0].text)
                    self.assertEqual(first["status"], "awaiting_upstream_sync")
                    self.assertIsNone(first["latest_run"])
                    second = await session.call_tool("running_context", args)
                    second = json.loads(second.content[0].text)
                    self.assertEqual(second["status"], "run_available")
                    self.assertEqual(second["latest_run"]["activity_id"], "i-new")
