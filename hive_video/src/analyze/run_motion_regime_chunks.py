#!/usr/bin/env python3
"""Run motion-regime annotation over a long video range in resumable chunks."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from _version import ANALYSIS_VERSION


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run annotate_motion_regimes.py over a long frame range as smaller chunks. "
            "This avoids holding the full video range and optical-flow stack in memory."
        )
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--duration-frames", type=int, required=True)
    parser.add_argument("--chunk-frames", type=int, default=9000)
    parser.add_argument("--window-frames", type=int, default=125)
    parser.add_argument("--stride-frames", type=int, default=25)
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
    parser.add_argument("--pca-components", type=int, default=8)
    parser.add_argument("--flow-scale-width", type=int, default=412)
    parser.add_argument("--activity-threshold", type=float, default=0.30)
    parser.add_argument("--min-active-fraction", type=float, default=0.005)
    parser.add_argument("--random-state", type=int, default=0)
    parser.add_argument("--angular-feature-weight", type=float, default=1.0)
    parser.add_argument("--neighbor-feature-weight", type=float, default=1.0)
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
    parser.add_argument(
        "--top-mask-height",
        type=int,
        default=0,
        help="Opaque black band, in output pixels, drawn across the top of chunk overlays.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--concat-video", action="store_true")
    parser.add_argument(
        "--safeword-file",
        type=Path,
        default=Path(".safeword"),
        help=(
            "Stop cleanly if this file contains 'sea cucumber' or 'seacucubmer' "
            "case-insensitively. Checked between chunks."
        ),
    )
    return parser.parse_args()


def write_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        fieldnames = [
            "chunk_index",
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
    list_path = out_dir / "overlay_concat_list.txt"
    with list_path.open("w") as f:
        for path in ready:
            escaped = str(path).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
    out_video = out_dir / "motion_regime_overlay_all_chunks.mp4"
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
    print(f"concatenating overlays: {out_video}", flush=True)
    subprocess.run(cmd, check=True)
    return out_video


def safeword_triggered(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(errors="ignore").casefold()
    except OSError:
        return False
    return "sea cucumber" in text or "seacucubmer" in text


def write_run_metadata(
    path: Path,
    args: argparse.Namespace,
    video: Path,
    out_dir: Path,
    safeword_file: Path,
    chunks: list[dict],
    concatenated_video: Path | None,
    stopped_by_safeword: bool,
) -> None:
    completed = [row for row in chunks if row["status"] == "done"]
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_version": ANALYSIS_VERSION,
        "video": str(video),
        "out_dir": str(out_dir),
        "start_frame": args.start_frame,
        "duration_frames": args.duration_frames,
        "chunk_frames": args.chunk_frames,
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
        "safeword_file": str(safeword_file),
        "stopped_by_safeword": stopped_by_safeword,
        "chunk_count": len(chunks),
        "completed_chunk_count": len(completed),
        "chunks_manifest": str(out_dir / "chunks_manifest.csv"),
        "concatenated_video": str(concatenated_video) if concatenated_video is not None else None,
    }
    path.write_text(json.dumps(metadata, indent=2) + "\n")


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    script = Path(__file__).with_name("annotate_motion_regimes.py")
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file
    chunks = []
    remaining = args.duration_frames
    start = args.start_frame
    chunk_index = 0
    stopped_by_safeword = False
    while remaining > 0:
        if safeword_triggered(safeword_file):
            print(f"safeword detected before chunk {chunk_index}; stopping cleanly", flush=True)
            stopped_by_safeword = True
            break
        duration = min(args.chunk_frames, remaining)
        chunk_out = out_dir / f"chunk_{chunk_index:04d}_frame_{start:07d}"
        features = chunk_out / "motion_regime_features.csv"
        overlay = chunk_out / "motion_regime_overlay.mp4"
        status = "pending"
        if features.exists() and overlay.exists() and not args.overwrite:
            status = "done"
            print(f"skipping existing chunk {chunk_index}: {chunk_out}", flush=True)
        else:
            cmd = [
                sys.executable,
                str(script),
                str(video),
                "--out",
                str(chunk_out),
                "--start-frame",
                str(start),
                "--duration-frames",
                str(duration),
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
                f"running chunk {chunk_index}: start={start:,} duration={duration:,} out={chunk_out}",
                flush=True,
            )
            subprocess.run(cmd, check=True)
            status = "done"

        chunks.append(
            {
                "chunk_index": chunk_index,
                "start_frame": start,
                "duration_frames": duration,
                "out_dir": str(chunk_out),
                "features_csv": str(features),
                "overlay_mp4": str(overlay),
                "status": status,
            }
        )
        write_manifest(out_dir / "chunks_manifest.csv", chunks)
        if safeword_triggered(safeword_file):
            print(f"safeword detected after chunk {chunk_index}; stopping cleanly", flush=True)
            stopped_by_safeword = True
            break
        start += duration
        remaining -= duration
        chunk_index += 1

    concatenated_video = concat_videos(out_dir, chunks) if args.concat_video else None
    write_run_metadata(
        out_dir / "metadata.json",
        args,
        video,
        out_dir,
        safeword_file,
        chunks,
        concatenated_video,
        stopped_by_safeword,
    )
    print(f"wrote manifest: {out_dir / 'chunks_manifest.csv'}")
    print(f"wrote metadata: {out_dir / 'metadata.json'}")


if __name__ == "__main__":
    main()
