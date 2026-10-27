"""Machine-readable CLI; every successful command produces one JSON document."""

import argparse
import getpass
import json
import sqlite3
import sys
import zipfile

from vitaldock import __version__
from vitaldock.archive import inputs
from vitaldock.huawei import parse
from vitaldock.model import METRICS, digest
from vitaldock.store import Vault


def parser():
    root = argparse.ArgumentParser(prog="vitaldock", description="Fresh health context for agents")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--vault", help="private vault directory (default outside source repository)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="initialize a local vault")
    inspect = commands.add_parser("inspect", help="inspect an export without saving data")
    inspect.add_argument("source")
    ingest = commands.add_parser("import-huawei", help="import Huawei personal-data export")
    ingest.add_argument("source")
    ingest.add_argument("--profile", default="self", help="local pseudonymous account label")
    ingest.add_argument("--strict", action="store_true", help="reject every warning/error atomically")
    coverage = commands.add_parser("coverage", help="list subjects and observed data extents")
    coverage.add_argument("--subject")
    query = commands.add_parser("query", help="read bounded records with provenance")
    query.add_argument("--subject", required=True)
    query.add_argument("--metric", choices=sorted(METRICS))
    query.add_argument("--since", help="inclusive ISO timestamp with UTC offset")
    query.add_argument("--until", help="exclusive ISO timestamp with UTC offset")
    query.add_argument("--limit", type=int, default=100)
    query.add_argument("--cursor")
    provenance = commands.add_parser("provenance", help="find source objects for a record")
    provenance.add_argument("record_id")
    provenance.add_argument("--subject", required=True)
    mcp = commands.add_parser("mcp", help="run a subject-scoped, read-only stdio MCP server")
    mcp.add_argument("--subject", required=True)
    mcp.add_argument("--metrics", nargs="+", choices=sorted(METRICS), required=True,
                     help="explicit metric allowlist granted to the connected agent")
    commands.add_parser("guide-huawei", help="show the Huawei acquisition steps")
    commands.add_parser("connect-intervals", help="verify a hidden key entry and save to OS credentials")
    live = commands.add_parser("run-context", help="fetch fresh Huawei running context from Intervals.icu")
    live.add_argument("--day", required=True, help="user's local YYYY-MM-DD")
    live.add_argument("--completed-after", required=True, help="ISO timestamp with UTC offset")
    live.add_argument("--history-days", type=int, default=28)
    live.add_argument("--wellness", action="store_true", help="allow recent daily recovery measurements")
    live.add_argument("--streams", action="store_true", help="allow sampled non-GPS activity streams")
    live_mcp = commands.add_parser("mcp-live", help="run live self-only Intervals.icu GET tools")
    live_mcp.add_argument("--wellness", action="store_true")
    live_mcp.add_argument("--streams", action="store_true")
    return root


def main(argv=None):
    arguments = parser().parse_args(argv)
    vault = Vault(arguments.vault)
    try:
        match arguments.command:
            case "init":
                vault.initialize()
                output = {"status": "ready", "vault": str(vault.root)}
            case "inspect":
                files = []
                for _name, data in inputs(arguments.source):
                    result = parse(data)
                    files.append({"sha256": digest(data), "bytes": len(data),
                                  "recognized": result.recognized,
                                  "supported_records": len(result.records), "issues": result.issues})
                output = {"files": files, "writes_performed": False}
            case "import-huawei":
                output = vault.import_huawei(arguments.source, arguments.profile, arguments.strict)
            case "coverage":
                output = vault.coverage(arguments.subject)
            case "query":
                output = vault.query(subject=arguments.subject, metric=arguments.metric,
                                     since=arguments.since, until=arguments.until,
                                     limit=arguments.limit, cursor=arguments.cursor)
            case "provenance":
                output = vault.provenance(arguments.record_id, subject=arguments.subject)
            case "mcp":
                from vitaldock.mcp_server import serve
                serve(vault, arguments.subject, set(arguments.metrics))
                return 0
            case "guide-huawei":
                output = {
                    "primary_route": "Huawei native connection -> Intervals.icu -> VitalDock live MCP",
                    "connections": "https://intervals.icu/settings/connections?services=huawei",
                    "setup": "connect-intervals",
                    "live_query": "run-context --day YYYY-MM-DD --completed-after ISO_TIMESTAMP",
                    "archive_fallback_only": {
                    "portal": "https://privacy.consumer.huawei.com/tool?lang=zh-cn",
                    "steps": ["Sync your wearable to Huawei Health and the cloud with your consent.",
                              "Sign in to the official privacy portal yourself.",
                              "Request a data copy and select Huawei Health.",
                              "Wait for Huawei to prepare the archive, then download it locally.",
                              "Decrypt locally using your archive password if required.",
                              "Run inspect, then import-huawei on the decrypted folder."],
                    "notes": ["Huawei estimates about 7 working days.",
                              "Online copies normally cover the past year. Ask Huawei for older data.",
                              "No Huawei password or developer credentials are needed by VitalDock."]}}
            case "connect-intervals":
                from datetime import datetime

                from vitaldock.credentials import save_key
                from vitaldock.intervals import IntervalsClient
                if not sys.stdin.isatty():
                    raise ValueError("run connect-intervals yourself in a local interactive terminal")
                key = getpass.getpass("Intervals.icu personal API key (hidden): ")
                IntervalsClient(key).activities(datetime.now().astimezone().date().isoformat(), 1)
                save_key(key)
                output = {"status": "connected", "account": "authenticated_self",
                          "credential_storage": "native_os_store", "key_returned": False}
            case "run-context":
                from vitaldock.intervals import IntervalsClient
                from vitaldock.running import post_run_context
                output = post_run_context(IntervalsClient(), day=arguments.day,
                                          completed_after=arguments.completed_after,
                                          history_days=arguments.history_days,
                                          include_wellness=arguments.wellness,
                                          include_streams=arguments.streams)
            case "mcp-live":
                from vitaldock.intervals import IntervalsClient
                from vitaldock.live_mcp import build_live_server
                build_live_server(IntervalsClient(), wellness=arguments.wellness,
                                  streams=arguments.streams).run(transport="stdio")
                return 0
        print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
        if arguments.command == "import-huawei" and output["status"] != "complete":
            return 2
        return 0
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile, NotImplementedError) as error:
        # Do not print source payloads or arbitrary vendor values through exceptions.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(json.dumps({"error": type(error).__name__, "message": message,
                          "retry_after_seconds": getattr(error, "retry_after", None)},
                         ensure_ascii=False), file=sys.stderr)
        return 1
