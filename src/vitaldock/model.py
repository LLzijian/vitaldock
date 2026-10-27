"""Versioned, vendor-neutral observations. No medical interpretation."""

import hashlib
import json
import math
import re
from datetime import datetime, timezone

PARSER_VERSION = "huawei-export/1"
SCHEMA_VERSION = "1.0"
METRICS = {
    "heart_rate": "bpm",
    "resting_heart_rate": "bpm",
    "oxygen_saturation": "%",
    "body_weight": "kg",
    "body_fat": "%",
    "sleep_stage": "category",
    "steps": "count",
    "workout_duration": "s",
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def milliseconds(value) -> int:
    # Export timestamps are milliseconds. REST nanoseconds require a separate adapter.
    if isinstance(value, bool) or not re.fullmatch(r"\d{13}", str(value)):
        raise ValueError("expected a 13-digit Unix millisecond timestamp")
    result = int(value)
    datetime.fromtimestamp(result / 1000, timezone.utc)
    return result


def iso_utc(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def instant(text: str | None) -> int | None:
    if text is None:
        return None
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("time must include UTC offset, e.g. 2026-10-27T00:00:00+08:00")
    return int(dt.timestamp() * 1000)


def number(value) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a measurement")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("measurement must be finite")
    return result


def pseudonym(value) -> str:
    return digest(str(value).encode("utf-8"))[:20]


def observation(*, profile, parent, point, metric, value, pointer, source_key,
                subject_hint=None, qualifiers=None):
    start = milliseconds(point.get("startTime"))
    end = milliseconds(point.get("endTime", point.get("startTime")))
    if end < start:
        raise ValueError("end precedes start")
    if metric in ("sleep_stage", "workout_duration", "steps") and end == start:
        raise ValueError("interval metric requires a positive duration")
    subject = parent.get("subUser")
    if subject in (None, "", "0", 0):
        subject = subject_hint
    subject_id = profile if subject in (None, "", "0", 0) else f"{profile}:{pseudonym(subject)}"
    offset = point.get("timeZone", parent.get("timeZone"))
    if offset is not None:
        if not re.fullmatch(r"[+-](?:0\d|1[0-4]):?[0-5]\d", str(offset)):
            raise ValueError("invalid source UTC offset")
        if len(offset) == 5:
            offset = offset[:3] + ":" + offset[3:]
    device = parent.get("deviceCode")
    body = {
        "provider": "huawei", "subject_id": subject_id,
        "device_id": pseudonym(device) if device is not None else None,
        "metric": metric, "start_ms": start, "end_ms": end,
        "value": value, "unit": METRICS[metric], "source_key": source_key,
        "source_utc_offset": offset, "qualifiers": qualifiers or {},
    }
    return {"id": digest(canonical(body).encode("utf-8")), **body,
            "pointer": pointer}
