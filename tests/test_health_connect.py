import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from vitaldock.cli import main
from vitaldock.health_connect import (
    HealthConnectClient,
    HealthConnectError,
    validate_token,
)

TOKEN = "a" * 64
SINCE = "2026-10-27T00:00:00+08:00"
UNTIL = "2026-10-28T00:00:00+08:00"


def payload(**values):
    return {"schema_version": "health-connect/1", "provider": "android_health_connect", **values}


class FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(json.dumps(result).encode())


class HealthConnectTests(unittest.TestCase):
    def test_local_get_transport_and_token_never_in_url(self):
        opener = FakeOpener(payload(status="connected", permissions={"steps": True}, token="discard"))
        result = HealthConnectClient(TOKEN, opener).status()
        request = opener.requests[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:38765/status")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertNotIn("token", result)
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_missing_records_stay_empty_and_refetch_on_every_call(self):
        opener = FakeOpener(payload(metric="steps", records=[], status="no_records"),
                            payload(metric="steps", records=[{"count": 20}]))
        client = HealthConnectClient(TOKEN, opener)
        first = client.records("steps", SINCE, UNTIL)
        second = client.records("steps", SINCE, UNTIL)
        self.assertEqual(first["records"], [])
        self.assertEqual(second["records"][0]["count"], 20)
        self.assertEqual(len(opener.requests), 2)

    def test_invalid_queries_stop_before_network(self):
        opener = FakeOpener()
        client = HealthConnectClient(TOKEN, opener)
        cases = [("steps", SINCE, UNTIL, 0), ("steps", SINCE, UNTIL, True),
                 ("gps", SINCE, UNTIL, 10), ("steps", "2026-10-27", UNTIL, 10),
                 ("steps", SINCE, "2026-11-06T00:00:00+08:00", 10)]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(HealthConnectError):
                client.records(*args)
        self.assertEqual(opener.requests, [])

    def test_pagination_preserves_cursor_and_attribution_without_aggregation(self):
        rows = [{"id": "synthetic-1", "source_package": "org.example.one", "count": 20},
                {"id": "synthetic-2", "source_package": "org.example.two", "count": 25}]
        opener = FakeOpener(payload(metric="steps", records=rows, next_page_token="next",
                                    result_truncated=True))
        result = HealthConnectClient(TOKEN, opener).records("steps", SINCE, UNTIL, 2, "first")
        self.assertEqual(result["records"], rows)
        self.assertEqual(result["next_page_token"], "next")
        self.assertIn("cursor=first", opener.requests[0].full_url)
        self.assertNotIn("total", result)

    def test_strava_and_unexpected_protocol_are_refused(self):
        for response in ({"provider": "unknown"}, payload(metric="steps", records=[
            {"source_package": "com.strava", "count": 50}])):
            with self.subTest(response=response), self.assertRaises(HealthConnectError):
                HealthConnectClient(TOKEN, FakeOpener(response)).records("steps", SINCE, UNTIL)

    def test_http_failure_does_not_echo_phone_payload_or_credentials(self):
        for code, expected in ((401, "phone_pairing_rejected"), (403, "phone_permission_denied"),
                               (302, "phone_redirect_refused")):
            error = HTTPError("http://127.0.0.1:38765", code, "private message", {},
                              io.BytesIO(b"private upstream body"))
            with self.subTest(code=code), self.assertRaisesRegex(HealthConnectError, expected):
                HealthConnectClient(TOKEN, FakeOpener(error)).status()

    def test_coverage_metric_scope_reaches_phone(self):
        opener = FakeOpener(payload(metrics={"sleep": {"status": "no_records"}}))
        result = HealthConnectClient(TOKEN, opener).coverage(SINCE, UNTIL, {"sleep"})
        self.assertIn("metrics=sleep", opener.requests[0].full_url)
        self.assertEqual(result["metrics"]["sleep"]["status"], "no_records")

    def test_token_requires_exact_random_hex_format(self):
        for value in (None, "", "a" * 63, "g" * 64, "a" * 64 + "\n"):
            with self.subTest(value=value), self.assertRaises(HealthConnectError):
                validate_token(value)

    def test_cli_status_remains_single_json_document(self):
        with patch("vitaldock.health_connect.HealthConnectClient") as factory:
            factory.return_value.status.return_value = payload(status="connected")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["health-connect-status"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "connected")


@unittest.skipUnless(importlib.util.find_spec("mcp"), "install .[mcp] for transport tests")
class PhoneMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_offline_and_matches_published(self):
        from vitaldock.health_connect_mcp import tool_manifest
        with patch("vitaldock.health_connect.load_token", side_effect=AssertionError("credential read")):
            manifest = await tool_manifest()
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root / "interfaces/health-connect-mcp-tools.json").read_text(
            encoding="utf-8")), manifest)
        self.assertEqual(len(manifest["metrics"]), 13)

    async def test_real_stdio_transport_enforces_metric_scope_and_pagination(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as folder:
            wrapper = Path(folder) / "phone_fixture.py"
            wrapper.write_text('''
from vitaldock.health_connect_mcp import build_server
class Client:
    def status(self):
        return {"permissions": {"steps": True, "sleep": True}}
    def coverage(self, since, until, metrics):
        return {"metrics": sorted(metrics)}
    def records(self, metric, since, until, limit, cursor):
        return {"records": [{"count": 20}], "next_page_token": "synthetic-next"}
build_server(Client(), {"steps"}).run(transport="stdio")
''', encoding="utf-8")
            root = Path(__file__).resolve().parents[1]
            params = StdioServerParameters(command=sys.executable, args=[str(wrapper)], env={
                "PYTHONPATH": str(root / "src"), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    self.assertEqual(len(tools), 3)
                    self.assertTrue(all(tool.annotations.readOnlyHint for tool in tools))
                    result = await session.call_tool("health_connect_status", {})
                    self.assertEqual(json.loads(result.content[0].text)["permissions"], {"steps": True})
                    args = {"metric": "steps", "since": SINCE, "until": UNTIL, "limit": 1}
                    result = await session.call_tool("health_connect_records", args)
                    self.assertEqual(json.loads(result.content[0].text)["next_page_token"], "synthetic-next")
                    denied = await session.call_tool("health_connect_records", {**args, "metric": "sleep"})
                    self.assertTrue(denied.isError)
                    invalid = await session.call_tool("health_connect_records", {**args, "limit": 201})
                    self.assertTrue(invalid.isError)


if __name__ == "__main__":
    unittest.main()
