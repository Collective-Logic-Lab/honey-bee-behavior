#!/usr/bin/env python3
"""Build video segment boundaries from ranked frame-to-frame jump candidates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a segments CSV from discontinuity candidates."
    )
    parser.add_argument("video", type=Path, help="Input video file.")
    parser.add_argument(
        "--jumps",
        type=Path,
        required=True,
        help=(
            "CSV with jump candidates or event summaries. For event summaries, use "
            "--input-kind events."
        ),
    )
    parser.add_argument("--out", type=Path, required=True, help="Output segments CSV.")
    parser.add_argument(
        "--top-n",
        type=int,
        default=146,
        help="Use this many strongest discontinuities from the jump CSV.",
    )
    parser.add_argument(
        "--input-kind",
        choices=("jumps", "events", "cut-review"),
        default="jumps",
        help=(
            "Interpret --jumps as raw candidates, summarized events, or a manually "
            "verified cut-review CSV."
        ),
    )
    parser.add_argument(
        "--single-jump-events-only",
        action="store_true",
        help="When --input-kind events, use only events with jump_count == 1.",
    )
    parser.add_argument(
        "--max-duration-frames",
        type=int,
        default=None,
        help="When --input-kind events, keep only events at or below this duration.",
    )
    parser.add_argument(
        "--frame-count",
        type=int,
        default=None,
        help=(
            "Known decoded frame count. If omitted, estimate from duration * fps. "
            "This avoids slow ffprobe -count_frames scans."
        ),
    )
    parser.add_argument(
        "--count-frames",
        action="store_true",
        help="Use ffprobe -count_frames for an exact frame count. This can be slow.",
    )
    parser.add_argument(
        "--extra-cut-prev-frame",
        type=int,
        action="append",
        default=[],
        help=(
            "Force an additional cut after this previous-frame index. May be passed "
            "more than once for diagnosed discontinuities that were filtered out of "
            "the ranked event selection."
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


def probe_video(video: Path, count_frames: bool = False) -> tuple[int | None, float, float | None]:
    print(f"probing video metadata: {video}", flush=True)
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
    ]
    if count_frames:
        print("counting frames with ffprobe -count_frames; this may take a while", flush=True)
        cmd.append("-count_frames")
    cmd.append(str(video))
    data = run_json(
        cmd
    )
    stream = next(s for s in data["streams"] if s.get("codec_type") == "video")
    fps = parse_fps(stream.get("avg_frame_rate") or stream["r_frame_rate"])
    duration = data.get("format", {}).get("duration")
    duration_s = float(duration) if duration is not None else None
    frame_count = stream.get("nb_read_frames") or stream.get("nb_frames")
    return int(frame_count) if frame_count is not None else None, fps, duration_s


def read_jump_prev_frames(
    path: Path,
    top_n: int,
    input_kind: str,
    single_jump_events_only: bool,
    max_duration_frames: int | None,
) -> list[int]:
    print(f"reading {input_kind}: {path}", flush=True)
    rows = []
    verified_cuts: list[int] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        if input_kind == "cut-review":
            required = {"keep", "prev_frame_idx"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"Verified cut review is missing columns {sorted(missing)}: {path}"
                )
        for row in reader:
            if input_kind == "cut-review":
                keep = (row.get("keep") or "").strip().casefold()
                if keep in {"0", "false", "no", "n", ""}:
                    continue
                if keep not in {"1", "true", "yes", "y"}:
                    raise ValueError(
                        f"Invalid keep value {row.get('keep')!r}; use 1 or 0 in {path}"
                    )
                cut = int(row["prev_frame_idx"])
                if cut < 0:
                    raise ValueError(f"Cut frame must be non-negative, got {cut} in {path}")
                verified_cuts.append(cut)
                continue
            if input_kind == "events":
                jump_count = int(row["jump_count"])
                duration_frames = int(row["duration_frames"])
                if single_jump_events_only and jump_count != 1:
                    continue
                if max_duration_frames is not None and duration_frames > max_duration_frames:
                    continue
                rows.append(
                    {
                        "prev_frame_idx": int(row["peak_prev_frame_idx"]),
                        "mean_abs_diff": float(row["avg_mean_abs_diff"]),
                    }
                )
                continue
            rows.append(
                {
                    "prev_frame_idx": int(row["prev_frame_idx"]),
                    "mean_abs_diff": float(row["mean_abs_diff"]),
                }
            )
    if input_kind == "cut-review":
        duplicates = sorted(
            cut for cut in set(verified_cuts) if verified_cuts.count(cut) > 1
        )
        if duplicates:
            raise ValueError(f"Verified cut review contains duplicate cuts: {duplicates}")
        cuts = sorted(verified_cuts)
        if not cuts:
            raise ValueError(f"Verified cut review selects no cuts: {path}")
        print(f"read {len(cuts)} manually verified cuts", flush=True)
        return cuts
    rows.sort(key=lambda r: r["mean_abs_diff"], reverse=True)
    selected = rows[:top_n]
    cut_frames = sorted({row["prev_frame_idx"] for row in selected})
    print(f"read {len(rows)} eligible rows; selected {len(cut_frames)} unique cuts", flush=True)
    return cut_frames


def write_segments(
    out_path: Path,
    video: Path,
    frame_count: int,
    fps: float,
    duration_s: float | None,
    cut_prev_frames: list[int],
) -> None:
    print(f"writing segments: {out_path}", flush=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "segment_id",
                "source_video",
                "start_frame_idx",
                "end_frame_idx",
                "start_time_s",
                "end_time_s",
                "duration_frames",
                "duration_s",
                "cut_after_frame_idx",
                "next_segment_start_frame_idx",
            ],
        )
        writer.writeheader()
        start = 0
        for segment_id, cut in enumerate([*cut_prev_frames, frame_count - 1]):
            end = min(cut, frame_count - 1)
            if end < start:
                continue
            next_start = end + 1 if end + 1 < frame_count else ""
            duration_frames = end - start + 1
            writer.writerow(
                {
                    "segment_id": segment_id,
                    "source_video": str(video),
                    "start_frame_idx": start,
                    "end_frame_idx": end,
                    "start_time_s": f"{start / fps:.6f}",
                    "end_time_s": f"{end / fps:.6f}",
                    "duration_frames": duration_frames,
                    "duration_s": f"{duration_frames / fps:.6f}",
                    "cut_after_frame_idx": end if next_start != "" else "",
                    "next_segment_start_frame_idx": next_start,
                }
            )
            start = end + 1
    metadata = {
        "video": str(video),
        "frame_count": frame_count,
        "fps": fps,
        "duration_s": duration_s,
        "cut_count": len(cut_prev_frames),
        "segment_count": len(cut_prev_frames) + 1,
    }
    out_path.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    jumps = args.jumps.expanduser().resolve()
    out = args.out.expanduser().resolve()

    probed_frame_count, fps, duration_s = probe_video(video, count_frames=args.count_frames)
    if args.frame_count is not None:
        frame_count = args.frame_count
        print(f"using provided frame count: {frame_count}", flush=True)
    elif probed_frame_count is not None:
        frame_count = probed_frame_count
        print(f"using probed frame count: {frame_count}", flush=True)
    elif duration_s is not None:
        frame_count = math.ceil(duration_s * fps)
        print(
            "estimated frame count from duration * fps: "
            f"{duration_s:.6f} * {fps:.6f} = {frame_count}",
            flush=True,
        )
    else:
        raise RuntimeError("Could not determine frame count; pass --frame-count.")
    cut_prev_frames = read_jump_prev_frames(
        jumps,
        args.top_n,
        args.input_kind,
        args.single_jump_events_only,
        args.max_duration_frames,
    )
    if args.extra_cut_prev_frame:
        before = len(cut_prev_frames)
        cut_prev_frames = sorted({*cut_prev_frames, *args.extra_cut_prev_frame})
        print(
            f"added {len(cut_prev_frames) - before} forced cuts from --extra-cut-prev-frame",
            flush=True,
        )
    invalid_cuts = [cut for cut in cut_prev_frames if cut < 0 or cut >= frame_count - 1]
    if invalid_cuts:
        raise ValueError(
            f"Cut frames must be between 0 and {frame_count - 2}; got {invalid_cuts}"
        )
    write_segments(out, video, frame_count, fps, duration_s, cut_prev_frames)
    print(f"video frames: {frame_count}")
    print(f"selected cuts: {len(cut_prev_frames)}")
    print(f"wrote segments: {out}")


if __name__ == "__main__":
    main()
