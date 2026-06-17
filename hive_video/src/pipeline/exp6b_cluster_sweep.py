#!/usr/bin/env python3
"""Experiment 6b: cluster-count sweep for selected Experiment 6 settings."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

HIVE_VIDEO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = HIVE_VIDEO_ROOT / "src" / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from exp6_frame_sweep import (  # noqa: E402
    draw_still,
    extract_one_window_features,
    feature_matrix_with_vertical,
    fit_clusters,
    make_settings,
    parse_int_list,
    read_frames,
    read_target_frame,
    safeword_triggered,
    summarize_scores,
)
from annotate_motion_regimes import compute_flows  # noqa: E402


DEFAULT_VIDEO = Path(
    "data/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4"
)
DEFAULT_TARGET_FRAMES = "220000,225004,226604,227250,227840,231546,242063"
DEFAULT_SETTING_IDS = "327,550,768,772,780,924"
DEFAULT_CLUSTERS = "6,8,10,12,15,18"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "For selected Experiment 6 setting IDs, rerun each setting at several cluster "
            "counts for each target frame, then make a 0.5 second-per-image review MP4."
        )
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--out-root", type=Path, default=Path("data/no-sync/exp6b_cluster_sweep_start03"))
    parser.add_argument("--target-frames", default=DEFAULT_TARGET_FRAMES)
    parser.add_argument("--setting-ids", default=DEFAULT_SETTING_IDS)
    parser.add_argument("--clusters", default=DEFAULT_CLUSTERS)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--seconds-per-image", type=float, default=0.5)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def write_manifest(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ffconcat_escape(path: Path) -> str:
    return str(path.resolve()).replace("'", "'\\''")


def make_review_video(image_paths: list[Path], out: Path, seconds_per_image: float, fps: int) -> None:
    if not image_paths:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="exp6b_review_") as tmpdir:
        concat_path = Path(tmpdir) / "images.ffconcat"
        with concat_path.open("w") as f:
            f.write("ffconcat version 1.0\n")
            for image_path in image_paths:
                f.write(f"file '{ffconcat_escape(image_path)}'\n")
                f.write(f"duration {seconds_per_image:.6f}\n")
            f.write(f"file '{ffconcat_escape(image_paths[-1])}'\n")
        command = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-r",
            str(fps),
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
        subprocess.run(command, check=True)


def main() -> None:
    args = parse_args()
    started = time.monotonic()
    video = args.video.expanduser()
    out_root = args.out_root.expanduser()
    frames_dir = out_root / "frames"
    out_root.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    target_frames = parse_int_list(args.target_frames)
    setting_ids = sorted(parse_int_list(args.setting_ids))
    cluster_values = parse_int_list(args.clusters)
    settings_by_id = {setting.setting_id: setting for setting in make_settings(1000)}
    missing = [setting_id for setting_id in setting_ids if setting_id not in settings_by_id]
    if missing:
        raise SystemExit(f"unknown Experiment 6 setting IDs: {missing}")
    base_settings = [settings_by_id[setting_id] for setting_id in setting_ids]
    max_window = max(setting.window_frames for setting in base_settings)

    manifest_path = out_root / "exp6b_cluster_sweep_manifest.csv"
    review_video = out_root / "exp6b_cluster_sweep_review.mp4"
    manifest_rows: list[dict] = []
    ordered_images: list[Path] = []
    sequence = 0
    total = len(target_frames) * len(base_settings) * len(cluster_values)

    for target_frame in target_frames:
        if safeword_triggered(safeword_file):
            print(f"safeword detected before target frame {target_frame}; stopping", flush=True)
            break
        print(f"reading max-window frames for target {target_frame}", flush=True)
        start_frame = target_frame - max_window + 1
        frames, fps = read_frames(video, start_frame, max_window, args.flow_scale_width)
        flows = compute_flows(frames)
        target_image, fps = read_target_frame(video, target_frame, args.flow_scale_width)

        for base_setting in base_settings:
            for cluster_count in cluster_values:
                sequence += 1
                setting = replace(base_setting, clusters=cluster_count)
                image_path = (
                    frames_dir
                    / f"seq_{sequence:04d}_frame{target_frame}_setting{setting.setting_id:04d}_k{cluster_count:02d}.png"
                )
                json_path = image_path.with_suffix(".json")
                status = "pending"
                scores = {}
                if safeword_triggered(safeword_file):
                    print(f"safeword detected before sequence {sequence}; stopping", flush=True)
                    write_manifest(manifest_path, manifest_rows)
                    return
                if image_path.exists() and json_path.exists() and not args.overwrite:
                    status = "skipped_existing"
                elif args.dry_run:
                    status = "dry_run"
                else:
                    features, vertical = extract_one_window_features(
                        flows,
                        target_frame,
                        max_window,
                        setting,
                    )
                    x, feature_names = feature_matrix_with_vertical(features, vertical, setting)
                    labels, probs, _ = fit_clusters(
                        x,
                        setting.method,
                        setting.clusters,
                        setting.pca_components,
                        0,
                        "diag",
                        1e-4,
                        setting.angular_feature_weight,
                        setting.neighbor_feature_weight,
                        feature_names,
                        setting.vertical_feature_weight,
                    )
                    draw_still(
                        target_image.copy(),
                        image_path,
                        features,
                        vertical,
                        labels,
                        probs,
                        setting,
                        target_frame,
                        fps,
                        args.top_mask_height,
                    )
                    scores = summarize_scores(features, vertical, labels, probs)
                    json_path.write_text(
                        json.dumps(
                            {
                                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                                "target_frame": target_frame,
                                "sequence": sequence,
                                "setting": asdict(setting),
                                "scores": scores,
                            },
                            indent=2,
                        )
                        + "\n"
                    )
                    status = "done"
                ordered_images.append(image_path)
                manifest_rows.append(
                    {
                        "sequence": sequence,
                        "target_frame": target_frame,
                        "setting_id": setting.setting_id,
                        "clusters": setting.clusters,
                        "image": str(image_path),
                        "json": str(json_path),
                        "status": status,
                        **asdict(setting),
                        **scores,
                    }
                )
                if sequence % 12 == 0 or sequence == total:
                    print(f"rendered {sequence}/{total}", flush=True)
                    write_manifest(manifest_path, manifest_rows)

    write_manifest(manifest_path, manifest_rows)
    if not args.dry_run:
        print(f"writing review video: {review_video}", flush=True)
        make_review_video(ordered_images, review_video, args.seconds_per_image, args.fps)

    elapsed = time.monotonic() - started
    print(f"wrote manifest: {manifest_path}", flush=True)
    if not args.dry_run:
        print(f"wrote review video: {review_video}", flush=True)
    print(f"elapsed wall time: {elapsed:.2f}s", flush=True)


if __name__ == "__main__":
    main()
