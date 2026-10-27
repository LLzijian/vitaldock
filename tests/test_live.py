import base64
import io
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from vitaldock.credentials import load_key, save_key
from vitaldock.intervals import IntervalsClient, LiveAPIError, NoRedirect
from vitaldock.running import bounded_streams, post_run_context, recovery_context

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
AFTER = "2026-10-27T15:00:00+08:00"


def run(id="i-new", start="2026-10-27T08:00:00Z", source="HUAWEI", **extra):
    return {"id": id, "source": source, "type": "Run", "start_date": start,
            "start_date_local": start.replace("Z", ""), "distance": 5000,
            "moving_time": 1500, "elapsed_time": 1600,
            "average_heartrate": 145, **extra}


class FakeClient:
    def __init__(self, activities=None, wellness=None, streams=None):
        self.rows = activities if activities is not None else [run()]
        self.days = wellness or []
        self.series = streams or []
        self.calls = []

    def activities(self, *args):
        self.calls.append("activities")
        return self.rows

    def wellness(self, *args):
        self.calls.append("wellness")
        if isinstance(self.days, Exception):
            raise self.days
        return self.days

    def streams(self, activity_id):
        self.calls.append(("streams", activity_id))
        return self.series


class ContextTests(unittest.TestCase):
    def context(self, client=None, **kwargs):
        return post_run_context(client or FakeClient(), day="2026-10-27", completed_after=AFTER,
                                now=NOW, **kwargs)

    def test_new_run_and_comparison_arithmetic(self):
        client = FakeClient([run(), run("i-old", "2026-10-25T08:00:00Z", moving_time=1650)])
        result = self.context(client)
        self.assertEqual(result["status"], "run_available")
        self.assertEqual(result["latest_run"]["moving_pace_s_per_km"], 300)
        self.assertEqual(result["comparison"]["latest_minus_previous"]["moving_pace_s_per_km"], -30)
        self.assertEqual(result["recovery"]["status"], "not_granted")
        self.assertEqual(client.calls, ["activities"])

    def test_no_recent_run_does_not_substitute_previous(self):
        result = self.context(FakeClient([run(start="2026-10-25T08:00:00Z")]))
        self.assertEqual(result["status"], "awaiting_upstream_sync")
        self.assertIsNone(result["latest_run"])
        self.assertIsNone(result["comparison"])

    def test_every_call_refetches_instead_of_using_old_cache(self):
        client = FakeClient([])
        self.assertEqual(self.context(client)["status"], "awaiting_upstream_sync")
        client.rows = [run()]
        self.assertEqual(self.context(client)["status"], "run_available")
        self.assertEqual(client.calls, ["activities", "activities"])

    def test_non_huawei_sources_and_incomplete_stubs_excluded(self):
        result = self.context(FakeClient([run(source="STRAVA"), run(source="GARMIN_CONNECT"),
                                         {"id": "stub"}, run(source=None)]))
        self.assertIsNone(result["latest_run"])

    def test_only_same_run_type_and_similar_distance_compared(self):
        result = self.context(FakeClient([run(),
                             run("i-trail", "2026-10-26T08:00:00Z", type="TrailRun"),
                             run("i-long", "2026-10-25T08:00:00Z", distance=20000)]))
        self.assertIsNone(result["comparison"])

    def test_bad_or_future_timing_does_not_confirm_a_completed_run(self):
        for data in (run(elapsed_time=None), run(elapsed_time=-1),
                     run(elapsed_time=1e100), run(start="2026-10-27T08:00:00"),
                     run(start="2026-10-28T08:00:00Z")):
            with self.subTest(data=data):
                self.assertIsNone(self.context(FakeClient([data]))["latest_run"])

    def test_wellness_baseline_excludes_today_and_missing(self):
        rows = [{"id":"2026-10-25", "restingHR": 60, "sleepSecs": 25200},
                {"id":"2026-10-26", "restingHR": 64, "sleepSecs": 0},
                {"id":"2026-10-27", "restingHR": 63}]
        result = self.context(FakeClient(wellness=rows), include_wellness=True)
        baseline = result["recovery"]["baseline"]
        self.assertEqual(baseline["restingHR"]["prior_mean"], 62)
        self.assertEqual(baseline["restingHR"]["today_minus_prior_mean"], 1)
        self.assertIsNone(baseline["hrv"]["today"])
        self.assertEqual(baseline["hrv"]["prior_days_with_data"], 0)
        self.assertEqual(baseline["sleepSecs"]["prior_days_with_data"], 2)
        self.assertEqual(baseline["sleepSecs"]["prior_mean"], 12600)
        self.assertIsNone(baseline["sleepSecs"]["today"])

    def test_wellness_failure_does_not_erase_available_run(self):
        result = self.context(FakeClient(wellness=LiveAPIError("rate_limited", 300)),
                              include_wellness=True)
        self.assertEqual(result["status"], "run_available")
        self.assertEqual(result["recovery"]["retry_after_seconds"], 300)

    def test_missing_today_is_explicit(self):
        result = recovery_context([{"id":"2026-10-25", "restingHR": 60}], "2026-10-27")
        self.assertFalse(result["today_present"])
        self.assertIsNone(result["baseline"]["restingHR"]["today"])

    def test_streams_bound_preserve_time_and_omit_gps(self):
        values = list(range(800))
        result = bounded_streams([{"type":"time", "data":values},
                                  {"type":"heartrate", "data":values},
                                  {"type":"latlng", "data":[[1,2]]}])
        self.assertEqual(len(result["streams"]), 2)
        self.assertLessEqual(len(result["streams"][0]["data"]), 400)
        self.assertEqual(result["streams"][0]["source_indices"],
                         result["streams"][1]["source_indices"])
        self.assertEqual(result["streams"][0]["data"][-1], 799)
        self.assertFalse(result["gps_included"])

    def test_only_selected_own_huawei_run_streams_fetched(self):
        client = FakeClient([run(), run("strava", source="STRAVA")])
        self.context(client, include_streams=True)
        self.assertEqual(client.calls, ["activities", ("streams", "i-new")])

    def test_invalid_range_rejected_before_network(self):
        for kwargs in ({"completed_after":"2026-10-27T10:00:00"},
                       {"completed_after":"2026-10-28T10:00:00Z"},
                       {"completed_after":"2025-10-28T10:00:00Z"},
                       {"history_days":91}, {"history_days":True}, {"day":"invalid"}):
            client = FakeClient()
            params = {"day":"2026-10-27", "completed_after":AFTER, "now":NOW, **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                post_run_context(client, **params)
            self.assertEqual(client.calls, [])


class FakeOpener:
    def __init__(self, payload=None, error=None):
        self.payload = payload if payload is not None else []
        self.error = error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.payload).encode())


class ClientTests(unittest.TestCase):
    def test_exact_self_endpoint_get_auth_and_field_projection(self):
        opener = FakeOpener([run(name="PRIVATE NAME", secret="PRIVATE")])
        client = IntervalsClient("synthetic-api-key", opener)
        rows = client.activities("2026-10-27")
        request = opener.requests[0]
        url = urlparse(request.full_url)
        self.assertEqual(url.netloc, "intervals.icu")
        self.assertEqual(url.path, "/api/v1/athlete/0/activities")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(base64.b64decode(request.headers["Authorization"].split()[1]),
                         b"API_KEY:synthetic-api-key")
        self.assertNotIn("name", rows[0])
        self.assertNotIn("synthetic-api-key", request.full_url)

    def test_wellness_and_streams_endpoints_and_gps_exclusion(self):
        opener = FakeOpener()
        client = IntervalsClient("synthetic-api-key", opener)
        client.wellness("2026-10-27")
        client.streams("i-own-run")
        self.assertIn("/athlete/0/wellness?", opener.requests[0].full_url)
        query = parse_qs(urlparse(opener.requests[1].full_url).query)
        self.assertEqual(query["includeDefaults"], ["false"])
        self.assertNotIn("latlng", query["types"][0])
        with self.assertRaises(ValueError):
            client.streams("../other")

    def test_http_failures_redacted_and_retry_after_preserved(self):
        for status, code in ((401,"authentication_failed"), (403,"access_denied"),
                             (429,"rate_limited"), (500,"upstream_http_error")):
            error = HTTPError("https://intervals.icu", status, "synthetic-secret", {"Retry-After":"42"}, None)
            client = IntervalsClient("synthetic-secret", FakeOpener(error=error))
            with self.subTest(status=status), self.assertRaises(LiveAPIError) as found:
                client.activities("2026-10-27")
            self.assertEqual(found.exception.code, code)
            self.assertNotIn("synthetic-secret", str(found.exception))
            if status == 429:
                self.assertEqual(found.exception.retry_after, 42)

    def test_network_failures_redacted(self):
        client = IntervalsClient("synthetic-secret", FakeOpener(error=URLError("synthetic-secret")))
        with self.assertRaisesRegex(LiveAPIError, "network_unavailable"):
            client.activities("2026-10-27")

    def test_redirects_refused(self):
        with self.assertRaisesRegex(LiveAPIError, "redirect_refused"):
            NoRedirect().redirect_request(None,None,302,"",{},"https://other.example")

    def test_shape_validation(self):
        for payload in ({}, [1], [None]):
            with self.subTest(payload=payload), self.assertRaises(LiveAPIError):
                IntervalsClient("synthetic-key", FakeOpener(payload)).activities("2026-10-27")

    def test_environment_credential_and_native_store_write(self):
        with patch.dict(os.environ, {"VITALDOCK_INTERVALS_API_KEY":"synthetic-key"}):
            self.assertEqual(load_key(), "synthetic-key")
        with patch("vitaldock.credentials._backend") as backend:
            save_key("synthetic-key")
            backend.return_value.set_password.assert_called_once_with(
                "VitalDock/Intervals.icu", "API_KEY", "synthetic-key")
