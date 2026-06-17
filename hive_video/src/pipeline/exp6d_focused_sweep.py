#!/usr/bin/env python3
"""Experiment 6d: focused w500/g64/k13 sweep around visually selected settings."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HIVE_VIDEO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = HIVE_VIDEO_ROOT / "src" / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from exp6_frame_sweep import (  # noqa: E402
    Setting,
    draw_still,
    extract_one_window_features,
    feature_matrix_with_vertical,
    fit_clusters,
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


def parse_float_list(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def parse_str_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def label_number(value: float | int) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", "p")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Experiment 6d: a broad focused permutation search at w500/g64/k13, "
            "with separation scores and a single ordered review video."
        )
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--out-root", type=Path, default=Path("data/no-sync/exp6d_focused_sweep_start03"))
    parser.add_argument("--target-frames", default=DEFAULT_TARGET_FRAMES)
    parser.add_argument("--window-frames", type=int, default=500)
    parser.add_argument("--grid-size", type=int, default=64)
    parser.add_argument("--clusters", type=int, default=13)
    parser.add_argument("--feature-sets", default="exp1,full")
    parser.add_argument("--velocity-transforms", default="log1p,sqrt,asinh")
    parser.add_argument("--activity-values", default="0.15,0.30,0.50")
    parser.add_argument("--angular-values", default="0,1,2,3,4")
    parser.add_argument("--neighbor-values", default="0,1,2,4")
    parser.add_argument("--vertical-values", default="0,1,2,4")
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--seconds-per-image", type=float, default=0.5)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--max-settings", type=int, default=None)
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def make_settings(args: argparse.Namespace) -> list[Setting]:
    values = list(
        itertools.product(
            parse_str_list(args.feature_sets),
            parse_str_list(args.velocity_transforms),
            parse_float_list(args.activity_values),
            parse_float_list(args.angular_values),
            parse_float_list(args.neighbor_values),
            parse_float_list(args.vertical_values),
        )
    )
    if args.max_settings is not None and args.max_settings < len(values):
        step = len(values) / args.max_settings
        values = [values[min(len(values) - 1, int(i * step))] for i in range(args.max_settings)]
    settings = []
    seen = set()
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        feature_set, velocity, activity, angular, neighbor, vertical = item
        settings.append(
            Setting(
                setting_id=len(settings) + 1,
                window_frames=args.window_frames,
                grid_size=args.grid_size,
                clusters=args.clusters,
                feature_set=feature_set,
                velocity_transform=velocity,
                activity_threshold=activity,
                angular_feature_weight=angular,
                neighbor_feature_weight=neighbor,
                vertical_feature_weight=vertical,
            )
        )
    return settings


def cluster_distribution(features, labels, region) -> dict[int, float]:
    label_by_cell = {
        (feature.cell_row, feature.cell_col): int(label)
        for feature, label in zip(features, labels, strict=True)
    }
    counts: dict[int, int] = {}
    for feature in region:
        label = label_by_cell[(feature.cell_row, feature.cell_col)]
        counts[label] = counts.get(label, 0) + 1
    total = sum(counts.values()) or 1
    return {label: count / total for label, count in counts.items()}


def region_scores(features, vertical, labels, probs, exclude_top_pixels: float = 72.0) -> dict:
    rows = [feature for feature in features if feature.y_center >= exclude_top_pixels]
    if not rows:
        return {}
    max_col = max(feature.cell_col for feature in rows)
    max_row = max(feature.cell_row for feature in rows)
    col_mid = (max_col + 1) / 2
    row_mid = (max_row + 1) / 2

    upper = [feature for feature in rows if feature.cell_row < row_mid]
    lower = [feature for feature in rows if feature.cell_row >= row_mid]
    upper_right = [feature for feature in rows if feature.cell_col >= col_mid and feature.cell_row < row_mid]
    lower_right = [feature for feature in rows if feature.cell_col >= col_mid and feature.cell_row >= row_mid]

    label_by_cell = {
        (feature.cell_row, feature.cell_col): int(label)
        for feature, label in zip(features, labels, strict=True)
    }
    index_by_cell = {
        (feature.cell_row, feature.cell_col): idx
        for idx, feature in enumerate(features)
    }

    def avg_label(region) -> float:
        return float(np.mean([label_by_cell[(f.cell_row, f.cell_col)] for f in region])) if region else float("nan")

    def tv_cluster(a, b) -> float:
        a_dist = cluster_distribution(features, labels, a)
        b_dist = cluster_distribution(features, labels, b)
        labels_all = sorted(set(a_dist) | set(b_dist))
        return 0.5 * sum(abs(a_dist.get(label, 0.0) - b_dist.get(label, 0.0)) for label in labels_all)

    def prob_profile(region) -> np.ndarray:
        if not region:
            return np.array([])
        indices = [index_by_cell[(f.cell_row, f.cell_col)] for f in region]
        return np.mean(probs[indices, :], axis=0)

    def tv_prob(a, b) -> float:
        a_prob = prob_profile(a)
        b_prob = prob_profile(b)
        if a_prob.size == 0 or b_prob.size == 0:
            return float("nan")
        return float(0.5 * np.sum(np.abs(a_prob - b_prob)))

    def avg_vertical(region, name: str) -> float:
        return (
            float(np.mean([vertical[(f.cell_row, f.cell_col)][name] for f in region]))
            if region
            else float("nan")
        )

    out = summarize_scores(features, vertical, labels, probs)
    out.update(
        {
            "upper_count": len(upper),
            "lower_count": len(lower),
            "upper_avg_cluster": avg_label(upper),
            "lower_avg_cluster": avg_label(lower),
            "upper_lower_avg_cluster_diff": abs(avg_label(upper) - avg_label(lower)),
            "upper_lower_cluster_tv": tv_cluster(upper, lower),
            "upper_lower_probability_tv": tv_prob(upper, lower),
            "upper_right_lower_right_cluster_tv": tv_cluster(upper_right, lower_right),
            "upper_right_lower_right_probability_tv": tv_prob(upper_right, lower_right),
            "upper_vertical_strand_score": avg_vertical(upper, "vertical_strand_score"),
            "lower_vertical_strand_score": avg_vertical(lower, "vertical_strand_score"),
            "upper_lower_vertical_strand_diff": abs(
                avg_vertical(upper, "vertical_strand_score")
                - avg_vertical(lower, "vertical_strand_score")
            ),
        }
    )
    return out


def write_manifest(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ffconcat_escape(path: Path) -> str:
    return str(path.resolve()).replace("'", "'\\''")


def make_review_video(image_paths: list[Path], out: Path, seconds_per_image: float, fps: int) -> None:
    if not image_paths:
        return
    with tempfile.TemporaryDirectory(prefix="exp6d_review_") as tmpdir:
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
    frames_dir.mkdir(parents=True, exist_ok=True)
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    target_frames = parse_int_list(args.target_frames)
    settings = make_settings(args)
    manifest_path = out_root / "exp6d_focused_sweep_manifest.csv"
    review_video = out_root / "exp6d_focused_sweep_review.mp4"
    ordered_images: list[Path] = []
    manifest_rows: list[dict] = []
    sequence = 0
    total = len(target_frames) * len(settings)

    for target_frame in target_frames:
        if safeword_triggered(safeword_file):
            print(f"safeword detected before target frame {target_frame}; stopping", flush=True)
            break
        print(f"reading frames for target {target_frame}", flush=True)
        start_frame = target_frame - args.window_frames + 1
        frames, fps = read_frames(video, start_frame, args.window_frames, args.flow_scale_width)
        flows = compute_flows(frames)
        target_image, fps = read_target_frame(video, target_frame, args.flow_scale_width)

        for setting in settings:
            sequence += 1
            if safeword_triggered(safeword_file):
                print(f"safeword detected before sequence {sequence}; stopping", flush=True)
                write_manifest(manifest_path, manifest_rows)
                return
            name = (
                f"seq_{sequence:05d}_frame{target_frame}_"
                f"fs{setting.feature_set}_{setting.velocity_transform}_"
                f"a{label_number(setting.activity_threshold)}_"
                f"ang{label_number(setting.angular_feature_weight)}_"
                f"nbr{label_number(setting.neighbor_feature_weight)}_"
                f"vert{label_number(setting.vertical_feature_weight)}"
            )
            image_path = frames_dir / f"{name}.png"
            json_path = frames_dir / f"{name}.json"
            status = "pending"
            scores = {}
            if image_path.exists() and json_path.exists() and not args.overwrite:
                status = "skipped_existing"
                try:
                    scores = json.loads(json_path.read_text()).get("scores", {})
                except Exception:
                    scores = {}
            elif args.dry_run:
                status = "dry_run"
            else:
                features, vertical = extract_one_window_features(
                    flows,
                    target_frame,
                    args.window_frames,
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
                scores = region_scores(features, vertical, labels, probs, args.top_mask_height)
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
                    "image": str(image_path),
                    "json": str(json_path),
                    "status": status,
                    **asdict(setting),
                    **scores,
                }
            )
            if sequence % 25 == 0 or sequence == total:
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
    print(f"settings per frame: {len(settings)}", flush=True)
    print(f"elapsed wall time: {elapsed:.2f}s", flush=True)


if __name__ == "__main__":
    main()
