"""Transactional normalized records and immutable, content-addressed sources."""

import json
import os
import re
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from vitaldock.archive import inputs
from vitaldock.huawei import parse
from vitaldock.model import (
    METRICS,
    PARSER_VERSION,
    SCHEMA_VERSION,
    canonical,
    digest,
    instant,
    iso_utc,
)

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS objects (
    sha256 TEXT PRIMARY KEY, bytes INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, metric TEXT NOT NULL,
    start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_lookup ON records(subject_id, metric, start_ms, id);
CREATE TABLE IF NOT EXISTS provenance (
    record_id TEXT NOT NULL REFERENCES records(id),
    object_sha256 TEXT NOT NULL REFERENCES objects(sha256),
    pointer TEXT NOT NULL, parser TEXT NOT NULL,
    PRIMARY KEY(record_id, object_sha256, pointer, parser)
);
CREATE TABLE IF NOT EXISTS imports (
    id TEXT PRIMARY KEY, imported_at TEXT NOT NULL, report TEXT NOT NULL
);
"""


def default_vault():
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
    return Path(base) / "VitalDock" if base else Path.home() / ".local/share/vitaldock"


class Vault:
    def __init__(self, root=None):
        self.root = Path(root).expanduser().resolve() if root else default_vault().resolve()
        self.database = self.root / "vitaldock.sqlite3"

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / "objects").mkdir(exist_ok=True, mode=0o700)
        connection = self.connect()
        try:
            with connection:
                row = connection.execute("PRAGMA user_version").fetchone()
                if row[0] not in (0, 1):
                    raise ValueError("unsupported vault schema")
                connection.executescript(DDL)
                row = connection.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
                if row and row[0] != SCHEMA_VERSION:
                    raise ValueError("unsupported vault schema")
                connection.execute("INSERT OR IGNORE INTO meta VALUES ('schema', ?)",
                                   (SCHEMA_VERSION,))
                connection.execute("PRAGMA user_version=1")
        finally:
            connection.close()

    def connect(self, readonly=False):
        if readonly:
            # SQLite URI quoting prevents '?' or '#' in a local path becoming URI options.
            connection = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
        else:
            connection = sqlite3.connect(self.database)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.row_factory = sqlite3.Row
        if readonly:
            row = connection.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if not row or row[0] != SCHEMA_VERSION:
                connection.close()
                raise ValueError("unsupported vault schema")
            connection.execute("PRAGMA query_only=ON")
        return connection

    def import_huawei(self, source, profile="self", strict=False):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", profile):
            raise ValueError("profile must contain 1-64 letters, digits, '_' or '-'")
        self.initialize()
        report = {"schema_version": SCHEMA_VERSION, "parser": PARSER_VERSION,
                  "import_id": uuid.uuid4().hex, "imported_at": datetime.now(
                      timezone.utc).isoformat(), "files": [], "records_inserted": 0,
                  "records_seen": 0, "issues": {}, "status": "complete"}
        # One transaction per import. Archive/input failures roll the whole import back.
        connection = self.connect()
        try:
            with connection:
                counts = Counter()
                for _name, data in inputs(source):
                    sha = digest(data)
                    parsed = parse(data, profile)
                    codes = Counter(item["code"] for item in parsed.issues)
                    counts.update(codes)
                    file_report = {"sha256": sha, "bytes": len(data),
                                   "recognized": parsed.recognized,
                                   "records_seen": len(parsed.records),
                                   "issues": parsed.issues}
                    report["files"].append(file_report)
                    report["records_seen"] += len(parsed.records)
                    if strict and parsed.issues:
                        raise ValueError("strict import rejected a file with issues; no records committed")
                    object_path = self.root / "objects" / sha
                    if object_path.exists():
                        if digest(object_path.read_bytes()) != sha:
                            raise ValueError("source object integrity check failed")
                    else:
                        # Exclusive creation: never overwrite an immutable source object.
                        try:
                            fd = os.open(object_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        except FileExistsError:
                            if digest(object_path.read_bytes()) != sha:
                                raise ValueError("source object integrity check failed") from None
                        else:
                            with os.fdopen(fd, "wb") as handle:
                                handle.write(data)
                    connection.execute("INSERT OR IGNORE INTO objects VALUES (?, ?)",
                                       (sha, len(data)))
                    for record in parsed.records:
                        pointer = record.pop("pointer")
                        cursor = connection.execute(
                            "INSERT OR IGNORE INTO records VALUES (?, ?, ?, ?, ?, ?)",
                            (record["id"], record["subject_id"], record["metric"],
                             record["start_ms"], record["end_ms"], canonical(record)))
                        report["records_inserted"] += cursor.rowcount
                        connection.execute("INSERT OR IGNORE INTO provenance VALUES (?, ?, ?, ?)",
                                           (record["id"], sha, pointer, PARSER_VERSION))
                report["issues"] = dict(counts)
                if counts:
                    report["status"] = "needs_review"
                if report["records_seen"] == 0:
                    report["status"] = "no_supported_records"
                connection.execute("INSERT INTO imports VALUES (?, ?, ?)",
                                   (report["import_id"], report["imported_at"], canonical(report)))
        finally:
            connection.close()
        return report

    def coverage(self, subject=None):
        connection = self.connect(readonly=True)
        try:
            where = " WHERE subject_id=?" if subject else ""
            rows = connection.execute(
                "SELECT subject_id, metric, COUNT(*) AS count, MIN(start_ms) AS first_ms, "
                "MAX(end_ms) AS last_ms FROM records" + where + " GROUP BY subject_id, metric "
                "ORDER BY subject_id, metric", (subject,) if subject else ()).fetchall()
            latest = connection.execute("SELECT report FROM imports ORDER BY imported_at DESC LIMIT 1"
                                        ).fetchone()
            # Reports may involve other people. Return aggregate status to scoped agents.
            last = json.loads(latest[0]) if latest else None
            return {"schema_version": SCHEMA_VERSION,
                    "coverage_meaning": "observed_extent_not_continuous_coverage",
                    "last_import": ({"imported_at": last["imported_at"],
                                     "status": last["status"]} if last else None),
                    "series": [{"subject_id": row["subject_id"], "metric": row["metric"],
                                "count": row["count"], "first": iso_utc(row["first_ms"]),
                                "last": iso_utc(row["last_ms"]),
                                "unit": METRICS[row["metric"]]} for row in rows]}
        finally:
            connection.close()

    def query(self, *, subject, metric=None, since=None, until=None, limit=100, cursor=None):
        if not subject:
            raise ValueError("an exact subject is required; discover subjects with coverage")
        if metric is not None and metric not in METRICS:
            raise ValueError("unknown metric")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be 1..500")
        lower, upper = instant(since), instant(until)
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError("since must precede until")
        clauses, args = ["subject_id=?"], [subject]
        if metric:
            clauses.append("metric=?")
            args.append(metric)
        # Select records by start time in [since, until). Do not split interval totals.
        if lower is not None:
            clauses.append("start_ms>=?")
            args.append(lower)
        if upper is not None:
            clauses.append("start_ms<?")
            args.append(upper)
        if cursor:
            try:
                at, rid = cursor.split(":", 1)
                at = int(at)
                if not re.fullmatch(r"[0-9a-f]{64}", rid):
                    raise ValueError
            except (ValueError, AttributeError):
                raise ValueError("invalid cursor") from None
            clauses.append("(start_ms>? OR (start_ms=? AND id>?))")
            args.extend([at, at, rid])
        args.append(limit + 1)
        connection = self.connect(readonly=True)
        try:
            rows = connection.execute("SELECT * FROM records WHERE " + " AND ".join(clauses)
                                      + " ORDER BY start_ms, id LIMIT ?", args).fetchall()
            has_more = len(rows) > limit
            records = []
            for row in rows[:limit]:
                record = json.loads(row["body"])
                record["start"] = iso_utc(record.pop("start_ms"))
                record["end"] = iso_utc(record.pop("end_ms"))
                record["provenance"] = [dict(p) for p in connection.execute(
                    "SELECT object_sha256, pointer, parser FROM provenance WHERE record_id=? "
                    "ORDER BY object_sha256, pointer, parser", (row["id"],))]
                records.append(record)
            last = rows[limit - 1] if has_more else None
            return {"schema_version": SCHEMA_VERSION,
                    "selection": {"subject": subject, "metric": metric, "since": since,
                                  "until": until, "semantics": "record_start_in_half_open_range"},
                    "records": records, "has_more": has_more,
                    "next_cursor": f"{last['start_ms']}:{last['id']}" if last else None}
        finally:
            connection.close()

    def provenance(self, record_id, *, subject):
        connection = self.connect(readonly=True)
        try:
            row = connection.execute("SELECT id FROM records WHERE id=? AND subject_id=?",
                                     (record_id, subject)).fetchone()
            if not row:
                raise ValueError("record not found for this subject")
            return {"record_id": record_id, "sources": [dict(r) for r in connection.execute(
                "SELECT object_sha256, pointer, parser FROM provenance WHERE record_id=? "
                "ORDER BY object_sha256, pointer, parser", (record_id,))]}
        finally:
            connection.close()
