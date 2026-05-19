#!/usr/bin/env python3
"""Group ranked frame-to-frame jump candidates into contiguous events."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Group frame-to-frame jump candidates into events. Consecutive candidate rows "
            "whose prev_frame_idx values are close together become one event."
        )
    )
    parser.add_argument("--candidates", type=Path, required=True, help="Candidates CSV.")
    parser.add_argument("--out", type=Path, required=True, help="Output event summary CSV.")
    parser.add_argument(
        "--fps",
        type=float,
        default=25.0,
        help="Video frames per second for timestamp conversion.",
    )
    parser.add_argument(
        "--max-gap-frames",
        type=int,
        default=1,
        help=(
            "Maximum gap between consecutive candidate prev_frame_idx values within an event. "
            "Use 1 for strictly adjacent frame-to-frame jumps."
        ),
    )
    parser.add_argument(
        "--sort-by",
        choices=("avg_diff", "max_diff", "start_frame"),
        default="avg_diff",
        help="How to sort events in the output.",
    )
    return parser.parse_args()


def seconds_to_mmss(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - 60 * minutes
    return f"{minutes:d}:{secs:06.3f}"


def read_candidates(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "prev_frame_idx": int(row["prev_frame_idx"]),
                    "next_frame_idx": int(row["next_frame_idx"]),
                    "prev_time_s": float(row.get("prev_time_s") or 0.0),
                    "next_time_s": float(row.get("next_time_s") or 0.0),
                    "mean_abs_diff": float(row["mean_abs_diff"]),
                }
            )
    return sorted(rows, key=lambda row: row["prev_frame_idx"])


def group_events(rows: list[dict], max_gap_frames: int) -> list[list[dict]]:
    if not rows:
        return []
    events = [[rows[0]]]
    for row in rows[1:]:
        previous = events[-1][-1]
        gap = row["prev_frame_idx"] - previous["prev_frame_idx"]
        if gap <= max_gap_frames:
            events[-1].append(row)
        else:
            events.append([row])
    return events


def summarize_event(event_id: int, rows: list[dict], fps: float) -> dict:
    diffs = [row["mean_abs_diff"] for row in rows]
    start_frame = rows[0]["prev_frame_idx"]
    stop_frame = rows[-1]["next_frame_idx"]
    start_s = start_frame / fps
    stop_s = stop_frame / fps
    peak = max(rows, key=lambda row: row["mean_abs_diff"])
    return {
        "event_id": event_id,
        "start_frame_idx": start_frame,
        "stop_frame_idx": stop_frame,
        "start_time_s": start_s,
        "stop_time_s": stop_s,
        "start_time_min": start_s / 60.0,
        "stop_time_min": stop_s / 60.0,
        "start_time_mmss": seconds_to_mmss(start_s),
        "stop_time_mmss": seconds_to_mmss(stop_s),
        "duration_frames": stop_frame - start_frame + 1,
        "duration_s": (stop_frame - start_frame + 1) / fps,
        "jump_count": len(rows),
        "avg_mean_abs_diff": statistics.mean(diffs),
        "median_mean_abs_diff": statistics.median(diffs),
        "max_mean_abs_diff": max(diffs),
        "min_mean_abs_diff": min(diffs),
        "peak_prev_frame_idx": peak["prev_frame_idx"],
        "peak_next_frame_idx": peak["next_frame_idx"],
        "peak_time_s": peak["prev_frame_idx"] / fps,
    }


def write_events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "event_id",
        "start_frame_idx",
        "stop_frame_idx",
        "start_time_s",
        "stop_time_s",
        "start_time_min",
        "stop_time_min",
        "start_time_mmss",
        "stop_time_mmss",
        "duration_frames",
        "duration_s",
        "jump_count",
        "avg_mean_abs_diff",
        "median_mean_abs_diff",
        "max_mean_abs_diff",
        "min_mean_abs_diff",
        "peak_prev_frame_idx",
        "peak_next_frame_idx",
        "peak_time_s",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            out = {"rank": rank, **row}
            for key in [
                "start_time_s",
                "stop_time_s",
                "start_time_min",
                "stop_time_min",
                "duration_s",
                "avg_mean_abs_diff",
                "median_mean_abs_diff",
                "max_mean_abs_diff",
                "min_mean_abs_diff",
                "peak_time_s",
            ]:
                out[key] = f"{out[key]:.6f}"
            writer.writerow(out)


def main() -> None:
    args = parse_args()
    candidates = args.candidates.expanduser().resolve()
    out = args.out.expanduser().resolve()

    rows = read_candidates(candidates)
    events = group_events(rows, args.max_gap_frames)
    summaries = [summarize_event(i, event, args.fps) for i, event in enumerate(events)]
    if args.sort_by == "avg_diff":
        summaries.sort(key=lambda row: row["avg_mean_abs_diff"], reverse=True)
    elif args.sort_by == "max_diff":
        summaries.sort(key=lambda row: row["max_mean_abs_diff"], reverse=True)
    else:
        summaries.sort(key=lambda row: row["start_frame_idx"])

    write_events(out, summaries)
    multi = sum(1 for row in summaries if row["jump_count"] > 1)
    print(f"read candidates: {len(rows)}")
    print(f"grouped events: {len(summaries)}")
    print(f"multi-jump events: {multi}")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
