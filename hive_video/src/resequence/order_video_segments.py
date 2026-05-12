#!/usr/bin/env python3
"""Propose an order for shuffled video segments using end-to-start frame similarity."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Segment:
    segment_id: int
    source_video: Path
    start_frame_idx: int
    end_frame_idx: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the last N frames of each segment with the first N frames of every "
            "other segment and propose a greedy ordering."
        )
    )
    parser.add_argument("--segments", type=Path, required=True, help="Segments CSV.")
    parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    parser.add_argument(
        "--window-frames",
        type=int,
        default=10,
        help="Number of frames to compare at each segment end/start.",
    )
    parser.add_argument(
        "--sample-width",
        type=int,
        default=96,
        help="Width for downsampled grayscale comparison frames.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Keep this many best outgoing matches per segment in ranked_edges.csv.",
    )
    parser.add_argument(
        "--signature",
        choices=("trajectory", "mean", "median"),
        default="trajectory",
        help=(
            "How to summarize each start/end window. 'trajectory' preserves the ordered "
            "frame sequence; 'mean' and 'median' collapse the window pixelwise."
        ),
    )
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
    return int(stream["width"]), int(stream["height"]), parse_fps(
        stream.get("avg_frame_rate") or stream["r_frame_rate"]
    )


def read_segments(path: Path) -> list[Segment]:
    segments = []
    with path.open() as f:
        for row in csv.DictReader(f):
            segments.append(
                Segment(
                    segment_id=int(row["segment_id"]),
                    source_video=Path(row["source_video"]),
                    start_frame_idx=int(row["start_frame_idx"]),
                    end_frame_idx=int(row["end_frame_idx"]),
                )
            )
    return segments


def comparison_size(source_width: int, source_height: int, sample_width: int) -> tuple[int, int]:
    height = max(1, round(sample_width * source_height / source_width))
    return sample_width, height


def extract_frame(video: Path, frame_idx: int, fps: float, width: int, height: int) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-v",
        "quiet",
        "-ss",
        f"{frame_idx / fps:.6f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:{height},format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    raw = subprocess.check_output(cmd)
    expected = width * height
    if len(raw) != expected:
        raise RuntimeError(f"Expected {expected} bytes for frame {frame_idx}, got {len(raw)}")
    return np.frombuffer(raw, dtype=np.uint8).astype(np.float32)


def segment_signature(
    segment: Segment,
    which: str,
    window_frames: int,
    fps: float,
    width: int,
    height: int,
    signature: str,
) -> np.ndarray:
    if which == "start":
        frames = range(
            segment.start_frame_idx,
            min(segment.start_frame_idx + window_frames, segment.end_frame_idx + 1),
        )
    elif which == "end":
        first = max(segment.start_frame_idx, segment.end_frame_idx - window_frames + 1)
        frames = range(first, segment.end_frame_idx + 1)
    else:
        raise ValueError(which)
    arrays = [extract_frame(segment.source_video, idx, fps, width, height) for idx in frames]
    if not arrays:
        raise RuntimeError(f"No frames available for segment {segment.segment_id} {which}")
    while len(arrays) < window_frames:
        # Short final/fragment segments need fixed-length signatures for all-pairs comparison.
        arrays.append(arrays[-1].copy())
    stack = np.stack(arrays)
    if signature == "trajectory":
        return stack.reshape(-1)
    if signature == "mean":
        return np.mean(stack, axis=0)
    if signature == "median":
        return np.median(stack, axis=0)
    raise ValueError(signature)


def mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def seconds_to_mmss(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - 60 * minutes
    return f"{minutes:d}:{secs:06.3f}"


def write_ranked_edges(path: Path, edges: list[dict], top_k: int, fps: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    by_from: dict[int, list[dict]] = {}
    for edge in edges:
        by_from.setdefault(edge["from_segment_id"], []).append(edge)
    for from_segment_id in sorted(by_from):
        ranked = sorted(by_from[from_segment_id], key=lambda row: row["mean_abs_diff"])
        for rank, row in enumerate(ranked[:top_k], start=1):
            rows.append({"rank_for_from_segment": rank, **row})

    with path.open("w", newline="") as f:
        fieldnames = [
            "rank_for_from_segment",
            "from_segment_id",
            "to_segment_id",
            "from_end_frame_idx",
            "from_end_time_s",
            "from_end_time_mmss",
            "to_start_frame_idx",
            "to_start_time_s",
            "to_start_time_mmss",
            "mean_abs_diff",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "rank_for_from_segment": row["rank_for_from_segment"],
                    "from_segment_id": row["from_segment_id"],
                    "to_segment_id": row["to_segment_id"],
                    "from_end_frame_idx": row["from_end_frame_idx"],
                    "from_end_time_s": f"{row['from_end_frame_idx'] / fps:.6f}",
                    "from_end_time_mmss": seconds_to_mmss(row["from_end_frame_idx"] / fps),
                    "to_start_frame_idx": row["to_start_frame_idx"],
                    "to_start_time_s": f"{row['to_start_frame_idx'] / fps:.6f}",
                    "to_start_time_mmss": seconds_to_mmss(row["to_start_frame_idx"] / fps),
                    "mean_abs_diff": f"{row['mean_abs_diff']:.6f}",
                }
            )


def greedy_order(segments: list[Segment], edges: list[dict]) -> list[dict]:
    by_from: dict[int, list[dict]] = {}
    incoming_best: dict[int, float] = {}
    for edge in edges:
        by_from.setdefault(edge["from_segment_id"], []).append(edge)
        incoming_best[edge["to_segment_id"]] = min(
            incoming_best.get(edge["to_segment_id"], math.inf),
            edge["mean_abs_diff"],
        )
    for from_segment_id in by_from:
        by_from[from_segment_id].sort(key=lambda row: row["mean_abs_diff"])

    segment_ids = {segment.segment_id for segment in segments}
    starts = sorted(segment_ids, key=lambda sid: incoming_best.get(sid, math.inf), reverse=True)
    current = starts[0]
    used = {current}
    order = [{"order": 0, "segment_id": current, "join_cost_from_previous": ""}]

    while len(used) < len(segment_ids):
        next_edge = None
        for edge in by_from.get(current, []):
            if edge["to_segment_id"] not in used:
                next_edge = edge
                break
        if next_edge is None:
            remaining = sorted(segment_ids - used)
            current = remaining[0]
            used.add(current)
            order.append(
                {
                    "order": len(order),
                    "segment_id": current,
                    "join_cost_from_previous": "",
                }
            )
            continue
        current = next_edge["to_segment_id"]
        used.add(current)
        order.append(
            {
                "order": len(order),
                "segment_id": current,
                "join_cost_from_previous": f"{next_edge['mean_abs_diff']:.6f}",
            }
        )
    return order


def write_order(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["order", "segment_id", "join_cost_from_previous"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    segments_path = args.segments.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    segments = read_segments(segments_path)
    if not segments:
        raise RuntimeError("No segments found.")
    source_video = segments[0].source_video.expanduser().resolve()
    source_width, source_height, fps = probe_video(source_video)
    width, height = comparison_size(source_width, source_height, args.sample_width)

    start_signatures = {}
    end_signatures = {}
    for segment in segments:
        print(f"extracting signatures for segment {segment.segment_id}", flush=True)
        start_signatures[segment.segment_id] = segment_signature(
            segment, "start", args.window_frames, fps, width, height, args.signature
        )
        end_signatures[segment.segment_id] = segment_signature(
            segment, "end", args.window_frames, fps, width, height, args.signature
        )

    edges = []
    for from_segment in segments:
        for to_segment in segments:
            if from_segment.segment_id == to_segment.segment_id:
                continue
            edges.append(
                {
                    "from_segment_id": from_segment.segment_id,
                    "to_segment_id": to_segment.segment_id,
                    "from_end_frame_idx": from_segment.end_frame_idx,
                    "to_start_frame_idx": to_segment.start_frame_idx,
                    "mean_abs_diff": mean_abs_diff(
                        end_signatures[from_segment.segment_id],
                        start_signatures[to_segment.segment_id],
                    ),
                }
            )

    write_ranked_edges(out_dir / "ranked_edges.csv", edges, args.top_k, fps)
    order = greedy_order(segments, edges)
    write_order(out_dir / "greedy_order.csv", order)
    metadata = {
        "segments": str(segments_path),
        "source_video": str(source_video),
        "segment_count": len(segments),
        "window_frames": args.window_frames,
        "sample_width": args.sample_width,
        "signature": args.signature,
        "comparison_width": width,
        "comparison_height": height,
        "fps": fps,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"wrote ranked edges: {out_dir / 'ranked_edges.csv'}")
    print(f"wrote greedy order: {out_dir / 'greedy_order.csv'}")


if __name__ == "__main__":
    main()
