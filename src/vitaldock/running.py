"""Fresh running context for an agent; evidence and arithmetic, no recovery score."""

import json
import math
from datetime import datetime, timedelta, timezone
from statistics import mean

from vitaldock.intervals import STREAM_TYPES, LiveAPIError, dates
from vitaldock.model import digest

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except ValueError:
        return None


def run_summary(row):
    distance = finite(row.get("distance"))
    moving = finite(row.get("moving_time"))
    elapsed = finite(row.get("elapsed_time"))
    distance = distance if distance is not None and distance > 0 else None
    moving = moving if moving is not None and moving >= 0 else None
    elapsed = elapsed if elapsed is not None and elapsed > 0 else None
    start = timestamp(row.get("start_date"))
    try:
        end = start + timedelta(seconds=elapsed) if start and elapsed else None
    except (OverflowError, ValueError):
        end = None
    return {
        "activity_id": row.get("id"), "source": row.get("source"), "type": row.get("type"),
        "started_at": row.get("start_date"), "started_at_local": row.get("start_date_local"),
        "estimated_finished_at": end.isoformat() if end else None,
        "distance_m": distance, "moving_time_s": moving, "elapsed_time_s": elapsed,
        "moving_pace_s_per_km": round(moving * 1000 / distance, 2)
        if moving is not None and moving > 0 and distance and distance > 0 else None,
        "average_heart_rate_bpm": finite(row.get("average_heartrate")),
        "max_heart_rate_bpm": finite(row.get("max_heartrate")),
        "elevation_gain_m": finite(row.get("total_elevation_gain")),
        "training_load": finite(row.get("icu_training_load")),
        "platform_synced_at": row.get("icu_sync_date"),
    }


def compare(latest, previous):
    changes = {}
    for field in ("distance_m", "moving_time_s", "moving_pace_s_per_km",
                  "average_heart_rate_bpm", "elevation_gain_m", "training_load"):
        a, b = finite(latest.get(field)), finite(previous.get(field))
        changes[field] = round(a-b, 2) if a is not None and b is not None else None
    return {"previous_run": previous, "latest_minus_previous": changes,
            "basis": "same_run_type_and_distance_within_20_percent",
            "interpretation": "descriptive_difference_not_proof_of_fitness_improvement",
            "uncontrolled_factors": ["route", "terrain", "weather", "intended_effort", "pauses"]}


def recovery_context(rows, day):
    # Daily platform records may be merged from several sources. Do not label them all Huawei.
    valid = []
    for row in rows:
        try:
            dates(row.get("id"), 1)
        except (ValueError, TypeError):
            continue
        if row["id"] <= day:
            valid.append({k: (v if k in ("id", "updated") else finite(v))
                          for k, v in row.items()})
    valid.sort(key=lambda row: row["id"])
    today = next((row for row in valid if row["id"] == day), None)
    prior = [row for row in valid if row["id"] < day]
    baseline = {}
    for field in ("restingHR", "hrv", "hrvSDNN", "sleepSecs"):
        values = [finite(row.get(field)) for row in prior]
        values = [v for v in values if v is not None and
                  (v >= 0 if field == "sleepSecs" else v > 0)]
        current = finite(today.get(field)) if today else None
        average = mean(values) if values else None
        baseline[field] = {"prior_days_with_data": len(values), "prior_mean": average,
                           "today": current,
                           "today_minus_prior_mean": round(current-average, 2)
                           if current is not None and average is not None else None}
    return {"daily_records": valid, "today_present": today is not None,
            "latest_observed_day": valid[-1]["id"] if valid else None,
            "baseline": baseline,
            "units": {"restingHR": "bpm", "hrv": "ms", "hrvSDNN": "ms", "sleepSecs": "s"},
            "source": "intervals_wellness_merged_source_not_resolved_per_field",
            "interpretation": "recovery_context_without_a_medical_or_readiness_verdict",
            "missing_data": ["hrv_is_not_guaranteed_by_huawei_native_connection",
                             "post_exercise_hr_recovery_requires_post_stop_samples"]}


def bounded_streams(rows, max_points=400):
    output = []
    lengths = [len(row["data"]) for row in rows
               if row.get("type") in STREAM_TYPES and isinstance(row.get("data"), list)]
    stride = max(1, math.ceil((max(lengths, default=0)-1)/(max_points-1)))
    for row in rows:
        kind = row.get("type")
        values = row.get("data")
        if kind not in STREAM_TYPES or not isinstance(values, list):
            continue
        # Keep a common stride across streams to preserve alignment by source index.
        indices = list(range(0, len(values), stride))
        if values and indices[-1] != len(values)-1:
            indices.append(len(values)-1)
        output.append({"type": kind, "original_points": len(values), "stride": stride,
                       "source_indices": indices,
                       "data": [finite(values[i]) for i in indices]})
    return {"streams": output, "sampling": "display_sample_not_for_recomputing_session_statistics",
            "equal_source_lengths": len(set(lengths)) <= 1,
            "gps_included": False}


def post_run_context(client, *, day, completed_after, history_days=28,
                     include_wellness=False, include_streams=False, now=None):
    oldest, _ = dates(day, history_days)
    after = timestamp(completed_after)
    if after is None:
        raise ValueError("completed_after must be an ISO timestamp with UTC offset")
    now = now or datetime.now(timezone.utc)
    if after > now:
        raise ValueError("completed_after is in the future")
    if not oldest <= after.date().isoformat() <= day:
        raise ValueError("completed_after must fall within the requested local date window")
    rows = client.activities(day, history_days)
    runs = []
    for row in rows:
        if row.get("source") != "HUAWEI" or row.get("type") not in RUN_TYPES:
            continue
        item = run_summary(row)
        if timestamp(item["started_at"]) and isinstance(item["activity_id"], str):
            runs.append(item)
    runs.sort(key=lambda item: timestamp(item["started_at"]), reverse=True)
    recent = [r for r in runs if timestamp(r["estimated_finished_at"])
              and after <= timestamp(r["estimated_finished_at"]) <= now]
    latest = recent[0] if recent else None
    output = {
        "schema_version": "live/1", "provider": "intervals.icu", "upstream": "HUAWEI",
        "account_scope": "authenticated_self", "fetched_at": now.isoformat(),
        "date_window": {"oldest": oldest, "newest": day},
        "completed_after": completed_after,
        "status": "run_available" if latest else "awaiting_upstream_sync",
        "freshness": "fresh_api_read_does_not_force_watch_to_phone_or_phone_to_cloud_sync",
        "latest_run": latest, "comparison": None,
        "history_may_be_truncated": len(rows) >= 500,
        "huawei_runs_in_window": len(runs),
        "next_action": None if latest else "sync_watch_in_huawei_health_then_query_again",
    }
    if latest:
        distance = latest["distance_m"]
        previous = next((row for row in runs if row["activity_id"] != latest["activity_id"]
                         and timestamp(row["started_at"]) < timestamp(latest["started_at"])
                         and row["type"] == latest["type"]
                         and distance and row["distance_m"] and row["distance_m"] > 0
                         and abs(row["distance_m"]-distance)/distance <= .2), None)
        if previous:
            output["comparison"] = compare(latest, previous)
    if include_wellness:
        try:
            output["recovery"] = recovery_context(client.wellness(day, history_days), day)
        except LiveAPIError as error:
            output["recovery"] = {"status": "unavailable", "error": error.code,
                                  "retry_after_seconds": error.retry_after}
    else:
        output["recovery"] = {"status": "not_granted"}
    if include_streams and latest:
        try:
            output["series"] = bounded_streams(client.streams(latest["activity_id"]))
        except LiveAPIError as error:
            output["series"] = {"status": "unavailable", "error": error.code}
    # A digest binds the context that the agent saw, without storing a private response.
    output["context_sha256"] = digest(json.dumps(output, sort_keys=True).encode())
    return output
