#!/usr/bin/env python3
"""Run motion-regime annotation on evenly spaced short samples."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from _version import ANALYSIS_VERSION


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run annotate_motion_regimes.py on evenly spaced short frame samples. "
            "This is intended for parameter sweeps that need broad video coverage "
            "without processing the full video."
        )
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument(
        "--duration-frames",
        type=int,
        required=True,
        help="Frame span over which samples are distributed.",
    )
    parser.add_argument("--sample-count", type=int, default=10)
    parser.add_argument("--sample-frames", type=int, default=250)
    parser.add_argument("--window-frames", type=int, default=125)
    parser.add_argument("--stride-frames", type=int, default=1)
    parser.add_argument("--grid-rows", type=int, default=32)
    parser.add_argument("--grid-cols", type=int, default=32)
    parser.add_argument("--clusters", type=int, default=8)
    parser.add_argument("--method", choices=("gmm", "kmeans"), default="gmm")
    parser.add_argument(
        "--gmm-covariance-type",
        choices=("full", "tied", "diag", "spherical"),
        default="diag",
    )
    parser.add_argument("--gmm-reg-covar", type=float, default=1e-4)
    parser.add_argument("--pca-components", type=int, default=0)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--activity-threshold", type=float, default=0.30)
    parser.add_argument("--min-active-fraction", type=float, default=0.005)
    parser.add_argument("--random-state", type=int, default=0)
    parser.add_argument("--angular-feature-weight", type=float, default=2.0)
    parser.add_argument("--neighbor-feature-weight", type=float, default=1.5)
    parser.add_argument(
        "--velocity-transform",
        choices=("raw", "log1p", "sqrt", "asinh"),
        default="raw",
    )
    parser.add_argument(
        "--feature-set",
        choices=("full", "exp1", "velocity", "beginner"),
        default="full",
    )
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--concat-video", action="store_true")
    return parser.parse_args()


def probe_frame_count(video: Path) -> int:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return frame_count


def sample_starts(start_frame: int, duration_frames: int, sample_frames: int, sample_count: int) -> list[int]:
    if sample_count <= 0:
        raise ValueError("--sample-count must be positive")
    if sample_frames <= 0:
        raise ValueError("--sample-frames must be positive")
    if duration_frames < sample_frames:
        return [start_frame]
    last_start = start_frame + duration_frames - sample_frames
    if sample_count == 1:
        return [start_frame + (last_start - start_frame) // 2]
    starts = np.linspace(start_frame, last_start, sample_count)
    return sorted({int(round(value)) for value in starts})


def write_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        fieldnames = [
            "sample_index",
            "start_frame",
            "duration_frames",
            "out_dir",
            "features_csv",
            "overlay_mp4",
            "status",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def concat_videos(out_dir: Path, rows: list[dict]) -> Path | None:
    ready = [Path(row["overlay_mp4"]) for row in rows if row["status"] == "done"]
    if not ready:
        return None
    list_path = out_dir / "sample_overlay_concat_list.txt"
    with list_path.open("w") as f:
        for path in ready:
            escaped = str(path).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
    out_video = out_dir / "motion_regime_overlay_all_samples.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(out_video),
    ]
    print(f"concatenating sample overlays: {out_video}", flush=True)
    subprocess.run(cmd, check=True)
    return out_video


def write_metadata(
    path: Path,
    args: argparse.Namespace,
    video: Path,
    out_dir: Path,
    video_frame_count: int,
    effective_duration_frames: int,
    rows: list[dict],
    concatenated_video: Path | None,
) -> None:
    completed = [row for row in rows if row["status"] == "done"]
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_version": ANALYSIS_VERSION,
        "video": str(video),
        "video_frame_count": video_frame_count,
        "out_dir": str(out_dir),
        "start_frame": args.start_frame,
        "duration_frames": args.duration_frames,
        "effective_duration_frames": effective_duration_frames,
        "sample_count": args.sample_count,
        "sample_frames": args.sample_frames,
        "window_frames": args.window_frames,
        "stride_frames": args.stride_frames,
        "grid_rows": args.grid_rows,
        "grid_cols": args.grid_cols,
        "clusters": args.clusters,
        "method": args.method,
        "gmm_covariance_type": args.gmm_covariance_type,
        "gmm_reg_covar": args.gmm_reg_covar,
        "pca_components": args.pca_components,
        "flow_scale_width": args.flow_scale_width,
        "activity_threshold": args.activity_threshold,
        "min_active_fraction": args.min_active_fraction,
        "random_state": args.random_state,
        "angular_feature_weight": args.angular_feature_weight,
        "neighbor_feature_weight": args.neighbor_feature_weight,
        "velocity_transform": args.velocity_transform,
        "feature_set": args.feature_set,
        "top_mask_height": args.top_mask_height,
        "overwrite": args.overwrite,
        "concat_video": args.concat_video,
        "manifest": str(out_dir / "samples_manifest.csv"),
        "completed_sample_count": len(completed),
        "concatenated_video": str(concatenated_video) if concatenated_video is not None else None,
    }
    path.write_text(json.dumps(metadata, indent=2) + "\n")


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.sample_frames < args.window_frames:
        raise ValueError("--sample-frames must be at least --window-frames")

    frame_count = probe_frame_count(video)
    if frame_count and args.start_frame >= frame_count:
        raise ValueError(f"start frame {args.start_frame:,} is past video end ({frame_count:,} frames)")

    if frame_count:
        available = frame_count - args.start_frame
        effective_duration = min(args.duration_frames, available)
        if effective_duration < args.duration_frames:
            print(
                f"requested sample span extends past video end; "
                f"using {effective_duration:,} available frames",
                flush=True,
            )
    else:
        effective_duration = args.duration_frames

    starts = sample_starts(args.start_frame, effective_duration, args.sample_frames, args.sample_count)
    script = Path(__file__).with_name("annotate_motion_regimes.py")
    rows = []
    for sample_index, start in enumerate(starts):
        sample_out = out_dir / f"sample_{sample_index:03d}_frame_{start:07d}"
        features = sample_out / "motion_regime_features.csv"
        overlay = sample_out / "motion_regime_overlay.mp4"
        if features.exists() and overlay.exists() and not args.overwrite:
            status = "done"
            print(f"skipping existing sample {sample_index}: {sample_out}", flush=True)
        else:
            cmd = [
                sys.executable,
                str(script),
                str(video),
                "--out",
                str(sample_out),
                "--start-frame",
                str(start),
                "--duration-frames",
                str(args.sample_frames),
                "--window-frames",
                str(args.window_frames),
                "--stride-frames",
                str(args.stride_frames),
                "--grid-rows",
                str(args.grid_rows),
                "--grid-cols",
                str(args.grid_cols),
                "--clusters",
                str(args.clusters),
                "--method",
                args.method,
                "--gmm-covariance-type",
                args.gmm_covariance_type,
                "--gmm-reg-covar",
                str(args.gmm_reg_covar),
                "--pca-components",
                str(args.pca_components),
                "--flow-scale-width",
                str(args.flow_scale_width),
                "--activity-threshold",
                str(args.activity_threshold),
                "--min-active-fraction",
                str(args.min_active_fraction),
                "--random-state",
                str(args.random_state),
                "--angular-feature-weight",
                str(args.angular_feature_weight),
                "--neighbor-feature-weight",
                str(args.neighbor_feature_weight),
                "--velocity-transform",
                args.velocity_transform,
                "--feature-set",
                args.feature_set,
                "--top-mask-height",
                str(args.top_mask_height),
            ]
            print(
                f"running sample {sample_index}: start={start:,} "
                f"duration={args.sample_frames:,} out={sample_out}",
                flush=True,
            )
            subprocess.run(cmd, check=True)
            status = "done"
        rows.append(
            {
                "sample_index": sample_index,
                "start_frame": start,
                "duration_frames": args.sample_frames,
                "out_dir": str(sample_out),
                "features_csv": str(features),
                "overlay_mp4": str(overlay),
                "status": status,
            }
        )
        write_manifest(out_dir / "samples_manifest.csv", rows)

    concatenated_video = concat_videos(out_dir, rows) if args.concat_video else None
    write_metadata(
        out_dir / "metadata.json",
        args,
        video,
        out_dir,
        frame_count,
        effective_duration,
        rows,
        concatenated_video,
    )
    print(f"wrote manifest: {out_dir / 'samples_manifest.csv'}")
    print(f"wrote metadata: {out_dir / 'metadata.json'}")


if __name__ == "__main__":
    main()
