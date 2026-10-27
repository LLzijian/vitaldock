"""Read-through Intervals.icu API client. Fixed host, self account, GET only."""

import base64
import json
import re
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from vitaldock.credentials import load_key

BASE = "https://intervals.icu/api/v1"
ACTIVITY_FIELDS = (
    "id", "source", "type", "start_date", "start_date_local", "distance", "moving_time",
    "elapsed_time", "average_speed", "average_heartrate", "max_heartrate",
    "total_elevation_gain", "icu_training_load", "device_name", "icu_sync_date",
)
WELLNESS_FIELDS = ("id", "updated", "restingHR", "hrv", "hrvSDNN", "sleepSecs", "sleepScore",
                   "fatigue", "soreness", "readiness", "ctl", "atl")
STREAM_TYPES = ("time", "heartrate", "velocity_smooth", "distance", "cadence", "altitude")
MAX_BODY = 8 * 1024 * 1024


class LiveAPIError(ValueError):
    def __init__(self, code, retry_after=None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LiveAPIError("redirect_refused")


def dates(day, history_days=28):
    if isinstance(history_days, bool) or not isinstance(history_days, int) or not 1 <= history_days <= 90:
        raise ValueError("history_days must be 1..90")
    end = date.fromisoformat(day)
    return (end - timedelta(days=history_days)).isoformat(), end.isoformat()


class IntervalsClient:
    def __init__(self, key=None, opener=None):
        self._key = key if key is not None else load_key()
        self._opener = opener or build_opener(NoRedirect())

    def _get(self, path, params):
        encoded = base64.b64encode(f"API_KEY:{self._key}".encode()).decode()
        request = Request(BASE + path + "?" + urlencode(params), method="GET", headers={
            "Authorization": "Basic " + encoded, "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; VitalDock/0.2; +https://github.com/LLzijian/vitaldock)",
        })
        try:
            with self._opener.open(request, timeout=20) as response:
                content = response.read(MAX_BODY + 1)
                if len(content) > MAX_BODY:
                    raise LiveAPIError("response_too_large")
                return json.loads(content)
        except HTTPError as error:
            if error.code == 429:
                retry = error.headers.get("Retry-After", "")
                raise LiveAPIError("rate_limited", int(retry) if retry.isdigit() else None) from None
            code = {401: "authentication_failed", 403: "access_denied", 404: "not_found"}.get(
                error.code, "upstream_http_error")
            raise LiveAPIError(code) from None
        except (URLError, TimeoutError, OSError):
            raise LiveAPIError("network_unavailable") from None
        except (UnicodeError, json.JSONDecodeError, RecursionError):
            raise LiveAPIError("invalid_upstream_json") from None

    def activities(self, day, history_days=28):
        oldest, newest = dates(day, history_days)
        rows = self._get("/athlete/0/activities", {
            "oldest": oldest, "newest": newest + "T23:59:59", "limit": 500,
            "fields": ",".join(ACTIVITY_FIELDS),
        })
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise LiveAPIError("invalid_activities_shape")
        return [{k: row[k] for k in ACTIVITY_FIELDS if k in row} for row in rows]

    def wellness(self, day, history_days=28):
        oldest, newest = dates(day, history_days)
        rows = self._get("/athlete/0/wellness", {
            "oldest": oldest, "newest": newest, "fields": ",".join(WELLNESS_FIELDS),
        })
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise LiveAPIError("invalid_wellness_shape")
        return [{k: row[k] for k in WELLNESS_FIELDS if k in row} for row in rows]

    def streams(self, activity_id):
        if not isinstance(activity_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", activity_id):
            raise ValueError("invalid activity id")
        rows = self._get(f"/activity/{activity_id}/streams", {
            "types": ",".join(STREAM_TYPES), "includeDefaults": "false",
        })
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise LiveAPIError("invalid_streams_shape")
        return rows
