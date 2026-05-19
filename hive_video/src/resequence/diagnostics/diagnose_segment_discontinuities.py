#!/usr/bin/env python3
"""Score frame-to-frame visual jumps inside source-frame ranges or segment IDs."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
from pathlib import Path

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute downsampled grayscale frame-to-frame distances for selected "
            "source-frame ranges. This is intended to diagnose missed cuts inside "
            "segments before rebuilding segments."
        )
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--segments", type=Path, default=None)
    parser.add_argument(
        "--segment-id",
        type=int,
        action="append",
        default=[],
        help="Segment ID to score. Requires --segments. May be passed more than once.",
    )
    parser.add_argument(
        "--range",
        dest="ranges",
        action="append",
        default=[],
        help="Inclusive source-frame range START:STOP to score. May be passed more than once.",
    )
    parser.add_argument("--sample-width", type=int, default=128)
    parser.add_argument("--top-n", type=int, default=20)
    return parser.parse_args()


def run_json(cmd: list[str]) -> dict:
    return json.loads(subprocess.check_output(cmd, text=True))


def parse_fps(value: str) -> float:
    if "/" in value:
        num, den = value.split("/", 1)
        return float(num) / float(den)
    return float(value)


def probe_video(video: Path) -> tuple[int, int, float]:
    data = run_json(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            str(video),
        ]
    )
    stream = next(s for s in data["streams"] if s.get("codec_type") == "video")
    fps = parse_fps(stream.get("avg_frame_rate") or stream["r_frame_rate"])
    return int(stream["width"]), int(stream["height"]), fps


def parse_range(value: str) -> tuple[int, int, str]:
    try:
        start_text, stop_text = value.split(":", 1)
        start = int(start_text.replace(",", ""))
        stop = int(stop_text.replace(",", ""))
    except ValueError as exc:
        raise ValueError(f"Range must be START:STOP, got {value!r}") from exc
    if stop <= start:
        raise ValueError(f"Range stop must be greater than start, got {value!r}")
    return start, stop, f"range_{start}_{stop}"


def segment_ranges(path: Path, segment_ids: list[int]) -> list[tuple[int, int, str]]:
    wanted = set(segment_ids)
    ranges = []
    with path.open() as f:
        for row in csv.DictReader(f):
            segment_id = int(row["segment_id"])
            if segment_id in wanted:
                ranges.append(
                    (
                        int(row["start_frame_idx"]),
                        int(row["end_frame_idx"]),
                        f"segment_{segment_id}",
                    )
                )
    found = {int(label.split("_", 1)[1]) for _, _, label in ranges}
    missing = sorted(wanted - found)
    if missing:
        raise ValueError(f"Segment IDs not found in {path}: {missing}")
    return ranges


def seconds_to_mmss(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - 60 * minutes
    return f"{minutes:d}:{secs:06.3f}"


def score_range(
    cap: cv2.VideoCapture,
    start: int,
    stop: int,
    label: str,
    sample_width: int,
    source_width: int,
    source_height: int,
    fps: float,
) -> list[dict]:
    sample_height = max(1, round(sample_width * source_height / source_width))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    previous = None
    rows = []
    for frame_idx in range(start, stop + 1):
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"Could not read frame {frame_idx}")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (sample_width, sample_height), interpolation=cv2.INTER_AREA)
        if previous is not None:
            diff = np.mean(
                np.abs(gray.astype(np.int16) - previous.astype(np.int16))
            )
            prev_frame_idx = frame_idx - 1
            rows.append(
                {
                    "label": label,
                    "prev_frame_idx": prev_frame_idx,
                    "next_frame_idx": frame_idx,
                    "prev_time_s": f"{prev_frame_idx / fps:.6f}",
                    "next_time_s": f"{frame_idx / fps:.6f}",
                    "prev_time_mmss": seconds_to_mmss(prev_frame_idx / fps),
                    "next_time_mmss": seconds_to_mmss(frame_idx / fps),
                    "mean_abs_diff": f"{diff:.6f}",
                }
            )
        previous = gray
    return rows


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "label",
                "prev_frame_idx",
                "next_frame_idx",
                "prev_time_s",
                "next_time_s",
                "prev_time_mmss",
                "next_time_mmss",
                "mean_abs_diff",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ranges = [parse_range(value) for value in args.ranges]
    if args.segment_id:
        if args.segments is None:
            raise ValueError("--segment-id requires --segments")
        ranges.extend(segment_ranges(args.segments.expanduser().resolve(), args.segment_id))
    if not ranges:
        raise ValueError("Pass at least one --range or --segment-id")

    source_width, source_height, fps = probe_video(video)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source video: {video}")
    try:
        rows = []
        for start, stop, label in ranges:
            print(f"scoring {label}: frames {start}-{stop}", flush=True)
            rows.extend(
                score_range(
                    cap,
                    start,
                    stop,
                    label,
                    args.sample_width,
                    source_width,
                    source_height,
                    fps,
                )
            )
    finally:
        cap.release()

    ranked = sorted(rows, key=lambda row: float(row["mean_abs_diff"]), reverse=True)
    write_rows(out_dir / "distances_by_time.csv", rows)
    write_rows(out_dir / "distances_ranked.csv", ranked)
    top_rows = ranked[: args.top_n]
    write_rows(out_dir / "top_distances.csv", top_rows)

    values = [float(row["mean_abs_diff"]) for row in rows]
    metadata = {
        "video": str(video),
        "segments": str(args.segments.expanduser().resolve()) if args.segments is not None else None,
        "ranges": [{"start": start, "stop": stop, "label": label} for start, stop, label in ranges],
        "sample_width": args.sample_width,
        "fps": fps,
        "row_count": len(rows),
        "median_mean_abs_diff": statistics.median(values) if values else None,
        "max_mean_abs_diff": max(values) if values else None,
        "top_distances_csv": str(out_dir / "top_distances.csv"),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"wrote ranked distances: {out_dir / 'distances_ranked.csv'}")
    print(f"wrote top distances: {out_dir / 'top_distances.csv'}")


if __name__ == "__main__":
    main()
