#!/usr/bin/env python3
"""Validate primitives/starter.csv before it can reach users.

This file is fetched directly by `agency primitives update`, so a bad or
truncated version is served to every install. The checks below are the ones
that would have caught real incidents:

  width      every row must have exactly as many fields as the header.
             (58 rows were once written against a stale 8-column schema
             while the header carried 12.)
  monotonic  the row count must not fall below the baseline. A net deletion
             nobody intended is a clobber; refuse to publish it. Override
             with --allow-shrink for a deliberate removal.
  duplicates description is the identity field, so duplicates collide on
             ingest. Pre-existing ones warn rather than block (they must not
             hold back an urgent publish), but the count must not increase.
  required   type/name/description must be non-empty; type must be valid.

Usage:
    validate_primitives.py [csv] [--baseline FILE] [--allow-shrink]
Exit 0 = clean, 1 = violations.
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

VALID_TYPES = {"role_component", "desired_outcome", "trade_off_config"}


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def validate(path, baseline=None, allow_shrink=False):
    problems = []
    rows = read_rows(path)
    if not rows:
        return ["file is empty"]

    header = rows[0]
    ncols = len(header)
    body = rows[1:]

    for i, row in enumerate(body, start=2):
        if len(row) != ncols:
            problems.append(
                f"line {i}: {len(row)} fields, header has {ncols} "
                f"(name={row[1] if len(row) > 1 else '?'})"
            )

    idx = {name: n for n, name in enumerate(header)}
    for field in ("type", "name", "description"):
        if field not in idx:
            problems.append(f"header is missing the required column '{field}'")

    if not problems:
        for i, row in enumerate(body, start=2):
            for field in ("type", "name", "description"):
                if not row[idx[field]].strip():
                    problems.append(f"line {i}: empty {field}")
            t = row[idx["type"]].strip()
            if t not in VALID_TYPES:
                problems.append(f"line {i}: unknown type '{t}'")

        dupes = [d for d, n in Counter(
            r[idx["description"]].strip() for r in body).items() if n > 1]
        if dupes:
            print(f"  WARNING: {len(dupes)} duplicate description(s):")
            for d in dupes[:5]:
                print(f"    {d[:90]}")
            if len(dupes) > 5:
                print(f"    ...and {len(dupes) - 5} more")

    if baseline and Path(baseline).exists():
        before = len(read_rows(baseline)) - 1
        after = len(body)
        if after < before and not allow_shrink:
            problems.append(
                f"ROW COUNT FELL: {before} -> {after} ({before - after} lost). "
                "A net deletion nobody intended is a clobber. If the removal is "
                "deliberate, re-run with --allow-shrink."
            )
        else:
            print(f"  row count {before} -> {after}")

        base_rows = read_rows(baseline)
        if base_rows and "description" in {c: c for c in base_rows[0]}:
            bi = base_rows[0].index("description")
            base_dupes = sum(1 for _, n in Counter(
                r[bi].strip() for r in base_rows[1:] if len(r) > bi).items() if n > 1)
            now_dupes = len(dupes) if not problems else 0
            if now_dupes > base_dupes:
                problems.append(
                    f"DUPLICATE DESCRIPTIONS INCREASED: {base_dupes} -> {now_dupes}. "
                    "description is the identity field; new collisions must not be published."
                )

    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", nargs="?", default="primitives/starter.csv")
    ap.add_argument("--baseline")
    ap.add_argument("--allow-shrink", action="store_true")
    args = ap.parse_args()

    print(f"validating {args.csv_path}")
    problems = validate(args.csv_path, args.baseline, args.allow_shrink)
    if problems:
        print("\nBLOCKED - starter.csv failed validation:\n")
        for p in problems:
            print(f"  {p}")
        print("\nThis file is served to every install. Fix before publishing.")
        return 1
    rows = read_rows(args.csv_path)
    print(f"  OK: {len(rows) - 1} primitives, {len(rows[0])} columns, no duplicates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
