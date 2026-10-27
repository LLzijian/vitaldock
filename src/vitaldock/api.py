"""Public, self-scoped Python interface shared by MCP and JSON command callers."""

from datetime import datetime, timezone

from vitaldock.intervals import IntervalsClient, dates
from vitaldock.running import RUN_TYPES, post_run_context, recovery_context, run_summary, timestamp


def _fetched_at():
    return datetime.now(timezone.utc).isoformat()


class AgentAPI:
    """Fresh reads of the authenticated user's Huawei activities and allowed wellness.

    Credentials are loaded by IntervalsClient, never supplied as agent tool arguments.
    Passing a client is intended for embedding and tests. Permissions are fixed here.
    """

    def __init__(self, client=None, *, wellness=False, streams=False):
        self.client = client if client is not None else IntervalsClient()
        self.allow_wellness = wellness
        self.allow_streams = streams

    def connection_status(self, day):
        """Verify a live authenticated read without returning private observations."""
        oldest, newest = dates(day, 7)
        rows = self.client.activities(day, 7)
        return {
            "schema_version": "agent/1", "status": "connected", "provider": "intervals.icu",
            "account_scope": "authenticated_self", "activity_source": "HUAWEI",
            "fetched_at": _fetched_at(),
            "date_window": {"oldest": oldest, "newest": newest},
            "huawei_activity_seen_in_window": any(r.get("source") == "HUAWEI" for r in rows),
            "permissions": {"wellness": self.allow_wellness, "streams": self.allow_streams},
            "credential_returned": False,
        }

    def recent_activities(self, day, history_days=28, limit=20):
        """List Huawei activities, including non-running workouts, with bounded output."""
        oldest, newest = dates(day, history_days)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        rows = self.client.activities(day, history_days)
        items = []
        for row in rows:
            if row.get("source") != "HUAWEI":
                continue
            summary = run_summary(row)
            if not timestamp(summary["started_at"]) or not isinstance(summary["activity_id"], str):
                continue
            if row.get("type") not in RUN_TYPES:
                summary["moving_pace_s_per_km"] = None
            items.append(summary)
        items.sort(key=lambda r: timestamp(r["started_at"]), reverse=True)
        return {
            "schema_version": "agent/1", "status": "available" if items else "no_activities",
            "provider": "intervals.icu", "account_scope": "authenticated_self",
            "activity_source": "HUAWEI", "fetched_at": _fetched_at(),
            "date_window": {"oldest": oldest, "newest": newest},
            "activities": items[:limit], "returned_count": min(limit, len(items)),
            "matching_count_in_fetched_window": len(items),
            "result_truncated": len(items) > limit or len(rows) >= 500,
            "freshness": "fresh_api_read_does_not_force_device_upload",
        }

    def wellness_context(self, day, history_days=28):
        """Get daily recovery observations independently of whether a run exists."""
        oldest, newest = dates(day, history_days)
        if not self.allow_wellness:
            raise ValueError("wellness_not_granted: start the server with --wellness")
        context = recovery_context(self.client.wellness(day, history_days), day)
        measured = any(any(r.get(field) is not None for field in (
            "restingHR", "hrv", "hrvSDNN", "sleepSecs", "sleepScore", "fatigue", "soreness"
        )) for r in context["daily_records"])
        return {
            "schema_version": "agent/1", "status": "available" if measured else "no_measurements",
            "provider": "intervals.icu", "account_scope": "authenticated_self",
            "fetched_at": _fetched_at(), "date_window": {"oldest": oldest, "newest": newest},
            "recovery": context,
        }

    def running_context(self, day, completed_after, history_days=28):
        """Get a newly completed run, previous comparison and granted recovery context."""
        return post_run_context(self.client, day=day, completed_after=completed_after,
                                history_days=history_days, include_wellness=self.allow_wellness,
                                include_streams=self.allow_streams)
