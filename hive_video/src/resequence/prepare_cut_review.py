#!/usr/bin/env python3
"""Prepare an editable discontinuity-cut review table from summarized events."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


FIELDNAMES = [
    "keep",
    "prev_frame_idx",
    "event_id",
    "event_rank",
    "jump_count",
    "duration_frames",
    "avg_mean_abs_diff",
    "max_mean_abs_diff",
    "notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert jump_events.csv into an editable cut-review CSV. Single-jump "
            "events are proposed with keep=1; multi-jump events remain visible with keep=0."
        )
    )
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def prepare_rows(events_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with events_path.open(newline="") as handle:
        for event in csv.DictReader(handle):
            jump_count = int(event["jump_count"])
            rows.append(
                {
                    "keep": "1" if jump_count == 1 else "0",
                    "prev_frame_idx": event["peak_prev_frame_idx"],
                    "event_id": event["event_id"],
                    "event_rank": event["rank"],
                    "jump_count": event["jump_count"],
                    "duration_frames": event["duration_frames"],
                    "avg_mean_abs_diff": event["avg_mean_abs_diff"],
                    "max_mean_abs_diff": event["max_mean_abs_diff"],
                    "notes": "",
                }
            )
    rows.sort(key=lambda row: int(row["prev_frame_idx"]))
    return rows


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(f"{path.suffix}.partial")
    with partial.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    partial.replace(path)


def main() -> None:
    args = parse_args()
    events = args.events.expanduser().resolve()
    out = args.out.expanduser().resolve()
    rows = prepare_rows(events)
    if not rows:
        raise RuntimeError(f"No discontinuity events found in {events}")
    write_rows(out, rows)
    proposed = sum(row["keep"] == "1" for row in rows)
    print(f"events reviewed : {len(rows)}")
    print(f"proposed cuts   : {proposed} single-jump events")
    print(f"wrote           : {out}")
    print("Review candidate frames, edit keep/prev_frame_idx, and save as cut_review.verified.csv.")


if __name__ == "__main__":
    main()
