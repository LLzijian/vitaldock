"""Read-only, token-authenticated phone database reads through USB loopback."""

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from vitaldock.credentials import _backend
from vitaldock.running import timestamp

METRICS = frozenset({
    "heart_rate", "resting_heart_rate", "hrv_rmssd", "sleep", "spo2", "respiratory_rate",
    "steps", "weight", "body_fat", "body_temperature", "distance", "active_energy", "total_energy",
})
BASE = "http://127.0.0.1:38765"
SERVICE = "VitalDock/HealthConnect"
USERNAME = "usb"
MAX_BODY = 8 * 1024 * 1024


class HealthConnectError(ValueError):
    pass


def validate_token(token):
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{64}", token):
        raise HealthConnectError("invalid_phone_pairing_token")
    return token


def load_token():
    token = os.environ.get("VITALDOCK_HEALTH_CONNECT_TOKEN")
    if token:
        return validate_token(token)
    try:
        token = _backend().get_password(SERVICE, USERNAME)
    except Exception:
        raise HealthConnectError("phone_credential_unavailable") from None
    if token is None:
        raise HealthConnectError("phone_not_paired: run connect-health-connect locally")
    return validate_token(token)


def save_token(token):
    token = validate_token(token)
    try:
        _backend().set_password(SERVICE, USERNAME, token)
    except Exception:
        raise HealthConnectError("phone_credential_store_failed") from None


def validate_window(since, until):
    start, end = timestamp(since), timestamp(until)
    if not start or not end or not timedelta(0) < end - start <= timedelta(days=7):
        raise HealthConnectError("phone_window_requires_offset_timestamps_and_0_to_7_days")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HealthConnectClient:
    """Fixed localhost transport. Tokens and phone URLs are never tool arguments."""

    def __init__(self, token=None, opener=None):
        self._token = validate_token(token) if token is not None else load_token()
        self._opener = opener or build_opener(ProxyHandler({}), NoRedirect())

    def _get(self, path, params=None):
        request = Request(BASE + path + ("?" + urlencode(params) if params else ""), headers={
            "Authorization": "Bearer " + self._token, "Accept": "application/json",
        }, method="GET")
        try:
            with self._opener.open(request, timeout=30) as response:
                raw = response.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise HealthConnectError("phone_response_too_large")
            data = json.loads(raw)
        except HTTPError as error:
            code = {401: "phone_pairing_rejected", 403: "phone_permission_denied",
                    400: "phone_invalid_arguments", 429: "phone_rate_limited"}.get(
                        error.code, "phone_request_failed")
            if 300 <= error.code < 400:
                code = "phone_redirect_refused"
            raise HealthConnectError(code) from None
        except (URLError, TimeoutError, OSError):
            raise HealthConnectError("phone_unreachable: open companion and restore USB forwarding") from None
        except (UnicodeError, json.JSONDecodeError, RecursionError):
            raise HealthConnectError("invalid_phone_json") from None
        if not isinstance(data, dict) or data.get("schema_version") != "health-connect/1" \
                or data.get("provider") != "android_health_connect":
            raise HealthConnectError("unexpected_phone_protocol")
        return data

    def status(self):
        data = self._get("/status")
        return {key: data[key] for key in ("schema_version", "provider", "fetched_at", "status",
                                          "permissions", "background_read_granted", "freshness")
                if key in data}

    def coverage(self, since, until, metrics=METRICS):
        validate_window(since, until)
        metrics = set(metrics)
        if not metrics or not metrics <= METRICS:
            raise HealthConnectError("unsupported_phone_metric")
        return self._get("/coverage", {"since": since, "until": until,
                                      "metrics": ",".join(sorted(metrics))})

    def records(self, metric, since, until, limit=100, cursor=None):
        validate_window(since, until)
        if metric not in METRICS:
            raise HealthConnectError("unsupported_phone_metric")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise HealthConnectError("phone_limit_must_be_1_to_200")
        if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 4096):
            raise HealthConnectError("invalid_phone_cursor")
        params = {"metric": metric, "since": since, "until": until, "limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        data = self._get("/records", params)
        rows = data.get("records")
        if data.get("metric") != metric or not isinstance(rows, list) or len(rows) > limit \
                or any(not isinstance(row, dict) for row in rows):
            raise HealthConnectError("invalid_phone_records")
        if any(row.get("source_package") == "com.strava" for row in rows):
            raise HealthConnectError("strava_source_refused")
        return data


def pair_usb(adb):
    """Read only this companion's visible pairing token; never log UI XML or token.

    The user must already have authorized USB debugging and Health Connect on the phone.
    No system health permission is granted by this helper.
    """
    def run(*arguments):
        try:
            result = subprocess.run([adb, *arguments], capture_output=True, timeout=30, check=True)
        except (OSError, subprocess.SubprocessError):
            raise HealthConnectError("usb_command_failed") from None
        return result.stdout

    devices = run("devices").decode("utf-8", "replace").splitlines()[1:]
    attached = [line for line in devices if "\tdevice" in line]
    if len(attached) != 1:
        raise HealthConnectError("exactly_one_authorized_phone_required")
    run("-d", "forward", "tcp:38765", "tcp:38765")
    remote = "/data/local/tmp/vitaldock-pairing-ui.xml"
    try:
        run("-d", "shell", "uiautomator", "dump", remote)
        raw = run("-d", "exec-out", "cat", remote)
        if len(raw) > 2 * 1024 * 1024:
            raise HealthConnectError("pairing_screen_too_large")
        root = ET.fromstring(raw)
        candidates = [node.get("text") for node in root.iter("node")
                      if node.get("content-desc") == "vitaldock-pairing-token"]
        if len(candidates) != 1:
            raise HealthConnectError("open_vitaldock_companion_pairing_screen")
        token = validate_token(candidates[0])
        result = HealthConnectClient(token).status()
        save_token(token)
        return result
    except ET.ParseError:
        raise HealthConnectError("invalid_pairing_screen") from None
    finally:
        run("-d", "shell", "rm", "-f", remote)
