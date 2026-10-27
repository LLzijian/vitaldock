"""Call the public Python API. Run with your configured VitalDock environment."""

import argparse
import json

from vitaldock.api import AgentAPI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True, help="user's local YYYY-MM-DD")
    arguments = parser.parse_args()
    api = AgentAPI()
    result = api.recent_activities(arguments.day, history_days=7, limit=5)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
