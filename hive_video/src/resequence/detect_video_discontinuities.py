#!/usr/bin/env python3
"""Detect likely visual discontinuities in a video by streaming frame differences."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    duration_s: float | None


@dataclass(frozen=True)
class FrameDistance:
    prev_frame_idx: int
    next_frame_idx: int
    prev_time_s: float
    next_time_s: float
    mean_abs_diff: float
    boundary_number: int | None = None
    expected_prev_frame_idx: int | None = None
    offset_from_expected: int | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stream a video through ffmpeg, compute downsampled grayscale frame-to-frame "
            "distances, and save likely discontinuity boundaries."
        )
    )
    parser.add_argument("video", type=Path, help="Input video file.")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for CSVs and candidate before/after frames.",
    )
    parser.add_argument(
        "--sample-width",
        type=int,
        default=128,
        help="Width for downsampled grayscale comparison frames.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=100,
        help="Number of highest-distance candidate boundaries to save.",
    )
    parser.add_argument(
        "--mad-z",
        type=float,
        default=12.0,
        help="Robust z threshold based on median absolute deviation. Higher is stricter.",
    )
    parser.add_argument(
        "--min-distance",
        type=float,
        default=None,
        help=(
            "Absolute minimum mean absolute difference for a candidate jump. "
            "When set, the effective threshold is max(MAD threshold, min-distance)."
        ),
    )
    parser.add_argument(
        "--threshold-mode",
        choices=("mad", "absolute", "max"),
        default="max",
        help=(
            "How to apply thresholds: 'mad' uses only --mad-z, 'absolute' uses only "
            "--min-distance, and 'max' uses the stricter of both when --min-distance is set."
        ),
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Optional cap for quick smoke tests.",
    )
    parser.add_argument(
        "--keep-all-distances",
        action="store_true",
        help="Write every consecutive-frame distance, not just top candidates.",
    )
    parser.add_argument(
        "--progress-every-frames",
        type=int,
        default=5_000,
        help="Print progress after this many decoded frames. Use 0 to disable.",
    )
    parser.add_argument(
        "--progress-every-seconds",
        type=float,
        default=10.0,
        help="Print progress after this many wall-clock seconds. Use 0 to disable.",
    )
    parser.add_argument(
        "--expected-interval-frames",
        type=int,
        default=None,
        help=(
            "Score only frame-to-frame distances near expected regular boundaries. "
            "For 10 realtime minutes at 3 encoded frames per realtime second, use 1800."
        ),
    )
    parser.add_argument(
        "--boundary-neighborhood",
        type=int,
        default=10,
        help=(
            "When --expected-interval-frames is set, keep distances whose previous frame "
            "is within this many frames of each expected previous-boundary frame."
        ),
    )
    return parser.parse_args()


def run_json(cmd: list[str]) -> dict:
    output = subprocess.check_output(cmd, text=True)
    return json.loads(output)


def parse_fps(value: str) -> float:
    if "/" in value:
        num, den = value.split("/", 1)
        return float(num) / float(den)
    return float(value)


def probe_video(video: Path) -> VideoInfo:
    data = run_json(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video),
        ]
    )
    video_stream = next(s for s in data["streams"] if s.get("codec_type") == "video")
    fps = parse_fps(video_stream.get("avg_frame_rate") or video_stream["r_frame_rate"])
    duration = data.get("format", {}).get("duration") or video_stream.get("duration")
    return VideoInfo(
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=fps,
        duration_s=float(duration) if duration is not None else None,
    )


def comparison_size(info: VideoInfo, sample_width: int) -> tuple[int, int]:
    height = max(1, round(sample_width * info.height / info.width))
    return sample_width, height


def stream_gray_frames(video: Path, width: int, height: int, max_frames: int | None = None):
    frame_size = width * height
    cmd = [
        "ffmpeg",
        "-v",
        "quiet",
        "-i",
        str(video),
        "-vf",
        f"scale={width}:{height},format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    assert proc.stdout is not None
    stopped_early = False
    try:
        idx = 0
        while max_frames is None or idx < max_frames:
            frame = proc.stdout.read(frame_size)
            if not frame:
                break
            if len(frame) != frame_size:
                raise RuntimeError(f"Incomplete raw frame: expected {frame_size}, got {len(frame)}")
            yield frame
            idx += 1
        if max_frames is not None and idx >= max_frames:
            stopped_early = True
            proc.terminate()
    finally:
        proc.stdout.close()
        return_code = proc.wait()
        if return_code and not stopped_early:
            raise subprocess.CalledProcessError(return_code, cmd)


def mean_abs_diff(a: bytes, b: bytes) -> float:
    a_array = np.frombuffer(a, dtype=np.uint8).astype(np.int16)
    b_array = np.frombuffer(b, dtype=np.uint8).astype(np.int16)
    return float(np.mean(np.abs(a_array - b_array)))


def robust_threshold(values: list[float], mad_z: float) -> tuple[float, float, float]:
    median = statistics.median(values)
    deviations = [abs(v - median) for v in values]
    mad = statistics.median(deviations)
    if mad == 0:
        return median, mad, math.inf
    # 1.4826 makes MAD comparable to standard deviation for normal data.
    return median, mad, median + mad_z * 1.4826 * mad


def effective_threshold(mad_threshold: float, min_distance: float | None, mode: str) -> float:
    if mode == "mad":
        return mad_threshold
    if min_distance is None:
        if mode == "absolute":
            raise ValueError("--threshold-mode absolute requires --min-distance")
        return mad_threshold
    if mode == "absolute":
        return min_distance
    return max(mad_threshold, min_distance)


def write_distances(path: Path, rows: list[FrameDistance], include_expected: bool = False) -> None:
    fieldnames = [
        "prev_frame_idx",
        "next_frame_idx",
        "prev_time_s",
        "next_time_s",
        "mean_abs_diff",
    ]
    if include_expected:
        fieldnames = [
            "boundary_number",
            "expected_prev_frame_idx",
            "offset_from_expected",
            *fieldnames,
        ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = {
                "prev_frame_idx": row.prev_frame_idx,
                "next_frame_idx": row.next_frame_idx,
                "prev_time_s": f"{row.prev_time_s:.6f}",
                "next_time_s": f"{row.next_time_s:.6f}",
                "mean_abs_diff": f"{row.mean_abs_diff:.6f}",
            }
            if include_expected:
                out = {
                    "boundary_number": row.boundary_number,
                    "expected_prev_frame_idx": row.expected_prev_frame_idx,
                    "offset_from_expected": row.offset_from_expected,
                    **out,
                }
            writer.writerow(out)


def extract_boundary_frames(video: Path, out_dir: Path, candidates: list[FrameDistance]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for rank, row in enumerate(candidates):
        frames = (
            ("prev", row.prev_frame_idx, row.prev_time_s),
            ("next", row.next_frame_idx, row.next_time_s),
        )
        for label, frame_idx, time_s in frames:
            out_path = out_dir / f"boundary_{rank:03d}_{label}_frame_{frame_idx:07d}.jpg"
            cmd = [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                f"{time_s:.6f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(out_path),
            ]
            subprocess.run(cmd, check=True)


def format_seconds(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "unknown"
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def print_progress(frame_idx: int, info: VideoInfo, started_at: float, finished: bool = False) -> None:
    elapsed = time.monotonic() - started_at
    decoded_fps = frame_idx / elapsed if elapsed > 0 else float("nan")
    video_time_s = frame_idx / info.fps
    parts = [
        f"frames={frame_idx:,}",
        f"video_time={format_seconds(video_time_s)}",
        f"elapsed={format_seconds(elapsed)}",
        f"decode_fps={decoded_fps:.1f}",
    ]
    if info.duration_s:
        percent = min(100.0, 100.0 * video_time_s / info.duration_s)
        remaining_frames = max(0.0, (info.duration_s - video_time_s) * info.fps)
        eta_s = remaining_frames / decoded_fps if decoded_fps > 0 else None
        parts.extend([f"progress={percent:.2f}%", f"eta={format_seconds(eta_s)}"])
    label = "finished" if finished else "progress"
    print(f"{label}: " + " ".join(parts), flush=True)


def expected_boundary_metadata(
    prev_frame_idx: int, interval_frames: int, neighborhood: int
) -> tuple[int, int, int] | None:
    if interval_frames <= 0:
        raise ValueError("--expected-interval-frames must be positive")
    if neighborhood < 0:
        raise ValueError("--boundary-neighborhood must be non-negative")

    # Boundary 1 is between frames interval-1 and interval.
    nearest_boundary = round((prev_frame_idx + 1) / interval_frames)
    if nearest_boundary < 1:
        return None
    expected_prev = nearest_boundary * interval_frames - 1
    offset = prev_frame_idx - expected_prev
    if abs(offset) > neighborhood:
        return None
    return nearest_boundary, expected_prev, offset


def summarize_expected_boundaries(rows: list[FrameDistance]) -> list[FrameDistance]:
    best_by_boundary: dict[int, FrameDistance] = {}
    for row in rows:
        if row.boundary_number is None:
            continue
        current = best_by_boundary.get(row.boundary_number)
        if current is None or row.mean_abs_diff > current.mean_abs_diff:
            best_by_boundary[row.boundary_number] = row
    return [best_by_boundary[k] for k in sorted(best_by_boundary)]


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    info = probe_video(video)
    width, height = comparison_size(info, args.sample_width)

    distances: list[FrameDistance] = []
    prev = None
    prev_idx = None
    started_at = time.monotonic()
    last_progress_frame = 0
    last_progress_at = started_at
    for idx, frame in enumerate(stream_gray_frames(video, width, height, args.max_frames)):
        if prev is not None and prev_idx is not None:
            distance = mean_abs_diff(prev, frame)
            boundary_info = None
            if args.expected_interval_frames is not None:
                boundary_info = expected_boundary_metadata(
                    prev_idx,
                    args.expected_interval_frames,
                    args.boundary_neighborhood,
                )
                if boundary_info is None:
                    prev = frame
                    prev_idx = idx
                    continue
            boundary_number, expected_prev, offset = (
                boundary_info if boundary_info is not None else (None, None, None)
            )
            distances.append(
                FrameDistance(
                    prev_frame_idx=prev_idx,
                    next_frame_idx=idx,
                    prev_time_s=prev_idx / info.fps,
                    next_time_s=idx / info.fps,
                    mean_abs_diff=distance,
                    boundary_number=boundary_number,
                    expected_prev_frame_idx=expected_prev,
                    offset_from_expected=offset,
                )
            )
        prev = frame
        prev_idx = idx
        now = time.monotonic()
        frame_due = (
            args.progress_every_frames > 0
            and idx - last_progress_frame >= args.progress_every_frames
        )
        time_due = (
            args.progress_every_seconds > 0
            and now - last_progress_at >= args.progress_every_seconds
        )
        if idx and (frame_due or time_due):
            print_progress(idx, info, started_at)
            last_progress_frame = idx
            last_progress_at = now

    if not distances:
        raise RuntimeError("No frame distances were computed.")
    if prev_idx is not None:
        print_progress(prev_idx, info, started_at, finished=True)

    values = [row.mean_abs_diff for row in distances]
    median, mad, mad_threshold = robust_threshold(values, args.mad_z)
    threshold = effective_threshold(mad_threshold, args.min_distance, args.threshold_mode)
    ranked = sorted(distances, key=lambda row: row.mean_abs_diff, reverse=True)
    if args.expected_interval_frames is not None:
        candidates = summarize_expected_boundaries(distances)
        candidates = sorted(candidates, key=lambda row: row.boundary_number or 0)
    else:
        candidates = [row for row in ranked if row.mean_abs_diff >= threshold]
        candidates = candidates[: args.top_n] if candidates else ranked[: args.top_n]

    metadata = {
        "video": str(video),
        "source_width": info.width,
        "source_height": info.height,
        "fps": info.fps,
        "duration_s": info.duration_s,
        "comparison_width": width,
        "comparison_height": height,
        "frames_compared": len(distances),
        "distance_median": median,
        "distance_mad": mad,
        "mad_threshold": mad_threshold,
        "min_distance": args.min_distance,
        "threshold_mode": args.threshold_mode,
        "candidate_threshold": threshold,
        "top_n": args.top_n,
        "mad_z": args.mad_z,
        "expected_interval_frames": args.expected_interval_frames,
        "boundary_neighborhood": args.boundary_neighborhood,
        "mode": "expected_boundaries" if args.expected_interval_frames is not None else "detect",
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    include_expected = args.expected_interval_frames is not None
    if args.keep_all_distances:
        path = "expected_boundary_neighborhood_distances.csv" if include_expected else "frame_distances.csv"
        write_distances(out_dir / path, distances, include_expected=include_expected)
    write_distances(out_dir / "candidates.csv", candidates, include_expected=include_expected)
    extract_boundary_frames(video, out_dir / "candidates", candidates)

    print(f"video: {video}")
    print(f"fps: {info.fps:.6f}; comparison frames: {width}x{height}")
    print(f"computed {len(distances)} frame-to-frame distances")
    print(
        f"median={median:.6f}; mad={mad:.6f}; "
        f"mad_threshold={mad_threshold:.6f}; effective_threshold={threshold:.6f}"
    )
    print(f"saved {len(candidates)} candidates to {out_dir / 'candidates.csv'}")


if __name__ == "__main__":
    main()
