#!/usr/bin/env python3
"""Time CLI - Standalone time and timezone utilities."""

import argparse
import json
import sys
from datetime import datetime

try:
    from zoneinfo import ZoneInfo, available_timezones
except ImportError:
    from pytz import timezone as ZoneInfo, all_timezones as _all_tz
    def available_timezones():
        return set(_all_tz)


def get_current_time(tz_name: str) -> dict:
    """Get current time in specified timezone."""
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        return {
            "timezone": tz_name,
            "datetime": now.isoformat(),
            "is_dst": bool(now.dst()) if hasattr(now, 'dst') and now.dst() else False
        }
    except Exception as e:
        return {"error": str(e)}


def convert_time(source_tz: str, time_str: str, target_tz: str) -> dict:
    """Convert time between timezones."""
    try:
        hour, minute = map(int, time_str.split(':'))
        source = ZoneInfo(source_tz)
        target = ZoneInfo(target_tz)

        today = datetime.now(source).date()
        source_dt = datetime(today.year, today.month, today.day, hour, minute, tzinfo=source)
        target_dt = source_dt.astimezone(target)

        source_offset = source_dt.utcoffset().total_seconds() / 3600
        target_offset = target_dt.utcoffset().total_seconds() / 3600
        diff = target_offset - source_offset

        return {
            "source": {
                "timezone": source_tz,
                "datetime": source_dt.isoformat(),
                "is_dst": bool(source_dt.dst()) if hasattr(source_dt, 'dst') and source_dt.dst() else False
            },
            "target": {
                "timezone": target_tz,
                "datetime": target_dt.isoformat(),
                "is_dst": bool(target_dt.dst()) if hasattr(target_dt, 'dst') and target_dt.dst() else False
            },
            "time_difference": f"{diff:+.1f}h"
        }
    except Exception as e:
        return {"error": str(e)}


def list_timezones(filter_str: str = None) -> list:
    """List available timezones."""
    zones = sorted(available_timezones())
    if filter_str:
        zones = [z for z in zones if filter_str.lower() in z.lower()]
    return zones


def main():
    parser = argparse.ArgumentParser(description="Time and timezone utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # get command
    get_parser = subparsers.add_parser("get", help="Get current time")
    get_parser.add_argument("--timezone", "-tz", default="UTC", help="IANA timezone name")

    # convert command
    convert_parser = subparsers.add_parser("convert", help="Convert time between timezones")
    convert_parser.add_argument("--time", "-t", required=True, help="Time in HH:MM format")
    convert_parser.add_argument("--from", "-f", dest="source", required=True, help="Source timezone")
    convert_parser.add_argument("--to", "-o", dest="target", required=True, help="Target timezone")

    # list command
    list_parser = subparsers.add_parser("list", help="List available timezones")
    list_parser.add_argument("--filter", "-f", help="Filter timezones by substring")

    args = parser.parse_args()

    if args.command == "get":
        result = get_current_time(args.timezone)
        print(json.dumps(result, indent=2))
    elif args.command == "convert":
        result = convert_time(args.source, args.time, args.target)
        print(json.dumps(result, indent=2))
    elif args.command == "list":
        zones = list_timezones(args.filter)
        for z in zones:
            print(z)


if __name__ == "__main__":
    main()
