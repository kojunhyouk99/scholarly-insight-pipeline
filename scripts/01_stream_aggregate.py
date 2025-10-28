#!/usr/bin/env python3
"""Stream the arXiv metadata JSON and build a monthly/category aggregate."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd
import ijson
from ijson import common as ijson_common
from dateutil import parser as dt_parser


def _parse_date(record: dict) -> pd.Timestamp | None:
    """Resolve the best available timestamp for a record."""
    created = None
    versions = record.get("versions")
    if isinstance(versions, list) and versions:
        created = versions[0].get("created")
    if not created:
        created = record.get("update_date")
    if not created:
        return None
    try:
        parsed = pd.to_datetime(dt_parser.parse(created))
    except Exception:
        return None
    if isinstance(parsed, pd.Timestamp):
        return parsed.tz_localize(None) if parsed.tzinfo else parsed
    return None


def _stream_array(path: Path) -> Iterable[dict]:
    with path.open("rb") as handle:
        yield from ijson.items(handle, "item")


def _stream_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _iter_records(path: Path) -> Iterable[dict]:
    """Yield dict records from diverse JSON formats (array or JSONL)."""
    try:
        yield from _stream_array(path)
        return
    except (ijson_common.IncompleteJSONError, ValueError):
        pass
    except FileNotFoundError:
        raise

    # Fallback to JSON Lines format if array parsing fails
    yield from _stream_jsonl(path)


def _main(args: argparse.Namespace) -> int:
    data_path = Path(args.data)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    prefix = args.prefix or ""
    since = pd.to_datetime(f"{args.since}-01") if args.since else None
    counter: Counter[Tuple[pd.Timestamp, str]] = Counter()

    for idx, record in enumerate(_iter_records(data_path), start=1):
        stamp = _parse_date(record)
        if stamp is None:
            continue
        if since is not None and stamp < since:
            continue

        ym = stamp.to_period("M").to_timestamp()
        cats = (record.get("categories") or "").strip()
        main_cat = cats.split()[0] if cats else "unknown"
        if prefix and not main_cat.startswith(prefix):
            continue
        counter[(ym, main_cat)] += 1

        if args.progress and idx % args.progress == 0:
            print(f"{idx:,} records processed…", file=sys.stderr)

    if not counter:
        print("No rows were aggregated. Adjust the filters and retry.", file=sys.stderr)
        return 1

    rows = (
        {"year_month": key[0], "main_cat": key[1], "count": value}
        for key, value in counter.items()
    )
    df = pd.DataFrame(rows).sort_values(["year_month", "main_cat"]).reset_index(drop=True)
    df.to_csv(out_path, index=False)
    print(f"Saved monthly aggregates → {out_path} ({len(df):,} rows)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stream aggregate arXiv metadata into a monthly/category CSV."
    )
    parser.add_argument("--data", required=True, help="Path to arxiv-metadata-oai-snapshot.json")
    parser.add_argument(
        "--out", default="data/arxiv_monthly.csv", help="Where to store the aggregate CSV"
    )
    parser.add_argument(
        "--prefix", default="", help="Filter by category prefix (e.g., 'cs.' for computer science)"
    )
    parser.add_argument(
        "--since", default=None, help="Include records from this YYYY-MM onwards (e.g., 2015-01)"
    )
    parser.add_argument(
        "--progress",
        type=int,
        default=200_000,
        help="Emit a progress line every N records (0 to disable)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.progress <= 0:
        args.progress = None
    sys.exit(_main(args))


if __name__ == "__main__":
    main()
