import contextlib
import importlib.util
import io
import json
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from test_live import FakeClient, run

from vitaldock.api import AgentAPI
from vitaldock.cli import main


class AgentAPITests(unittest.TestCase):
    def test_connection_status_does_not_return_values_or_credentials(self):
        result = AgentAPI(FakeClient(), wellness=True).connection_status("2026-10-27")
        self.assertEqual(result["status"], "connected")
        self.assertFalse(result["credential_returned"])
        self.assertNotIn("activities", result)
        self.assertNotIn("average_heart_rate_bpm", json.dumps(result))

    def test_general_workout_is_listed_without_inventing_distance_or_pace(self):
        client = FakeClient([run(type="Workout", distance=None, moving_time=1200)])
        result = AgentAPI(client).recent_activities("2026-10-27")
        self.assertEqual(result["returned_count"], 1)
        item = result["activities"][0]
        self.assertEqual(item["type"], "Workout")
        self.assertIsNone(item["distance_m"])
        self.assertIsNone(item["moving_pace_s_per_km"])

    def test_other_sources_and_invalid_timestamps_are_not_exposed(self):
        client = FakeClient([run(source="STRAVA"), run(source="GARMIN_CONNECT"),
                             run(start="bad"), {"id":"stub"}])
        result = AgentAPI(client).recent_activities("2026-10-27")
        self.assertEqual(result["status"], "no_activities")
        self.assertEqual(result["activities"], [])

    def test_recent_activities_are_sorted_bounded_and_marked_truncated(self):
        client = FakeClient([run("i-old", "2026-10-25T08:00:00Z"), run()])
        result = AgentAPI(client).recent_activities("2026-10-27", limit=1)
        self.assertEqual(result["activities"][0]["activity_id"], "i-new")
        self.assertTrue(result["result_truncated"])

    def test_invalid_limits_rejected_before_network(self):
        for limit in (0, 101, True):
            client = FakeClient()
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                AgentAPI(client).recent_activities("2026-10-27", limit=limit)
            self.assertEqual(client.calls, [])

    def test_wellness_available_without_any_run(self):
        client = FakeClient([], wellness=[{"id":"2026-10-27", "restingHR":62}])
        result = AgentAPI(client, wellness=True).wellness_context("2026-10-27")
        self.assertEqual(result["status"], "available")
        self.assertEqual(client.calls, ["wellness"])

    def test_no_wellness_grant_means_no_network_call(self):
        client = FakeClient()
        with self.assertRaisesRegex(ValueError, "wellness_not_granted"):
            AgentAPI(client).wellness_context("2026-10-27")
        self.assertEqual(client.calls, [])

    def test_load_only_days_are_not_mislabelled_as_recovery_measurements(self):
        client = FakeClient(wellness=[{"id":"2026-10-27", "ctl":15, "atl":20}])
        result = AgentAPI(client, wellness=True).wellness_context("2026-10-27")
        self.assertEqual(result["status"], "no_measurements")
        self.assertEqual(result["recovery"]["daily_records"][0]["ctl"], 15)

    def test_cli_routes_preserve_the_json_contract(self):
        cases = [
            (["check-connection", "--day", "2026-10-27"], "connection_status"),
            (["recent-activities", "--day", "2026-10-27"], "recent_activities"),
            (["wellness-context", "--day", "2026-10-27"], "wellness_context"),
        ]
        for args, method in cases:
            with self.subTest(args=args), patch("vitaldock.api.AgentAPI") as factory:
                getattr(factory.return_value, method).return_value = {"status":"synthetic_ok"}
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(args)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output.getvalue()), {"status":"synthetic_ok"})

    def test_client_configuration_examples_have_no_secret_fields(self):
        root = Path(__file__).resolve().parents[1]
        generic = json.loads((root / "examples/mcp-client.json").read_text(encoding="utf-8"))
        codex = tomllib.loads((root / "examples/codex-mcp.toml").read_text(encoding="utf-8"))
        for config in (generic["mcpServers"]["vitaldock-live"],
                       codex["mcp_servers"]["vitaldock_live"]):
            self.assertEqual(config["args"][:3], ["-m", "vitaldock", "mcp-live"])
            self.assertNotIn("env", config)
            self.assertNotIn("API_KEY", json.dumps(config))

    @unittest.skipUnless(importlib.util.find_spec("mcp"), "install .[mcp] for offline schema discovery")
    def test_cli_tool_discovery_never_loads_credentials(self):
        output = io.StringIO()
        with patch("vitaldock.intervals.load_key", side_effect=AssertionError("key read")), \
             contextlib.redirect_stdout(output):
            code = main(["agent-tools", "--wellness"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(output.getvalue())["tools"]), 4)
