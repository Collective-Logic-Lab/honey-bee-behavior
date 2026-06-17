#!/usr/bin/env python3
"""Pipeline 1: source-synchronous fixed-GMM honey bee motion-regime overlays.

This is the first cleaned-up pipeline version of the Experiment 9 sync-fix path.
It renders source-synchronous overlay videos, optionally renders side-by-side
source/overlay diptychs, and can write summary or per-frame cluster statistics.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

HIVE_VIDEO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = HIVE_VIDEO_ROOT / "src" / "pipeline"
ANALYZE_DIR = HIVE_VIDEO_ROOT / "src" / "analyze"
for path in (PIPELINE_DIR, ANALYZE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from annotate_motion_regimes import apply_feature_weights, compute_flows, fit_clusters, palette  # noqa: E402
from exp6_frame_sweep import (  # noqa: E402
    Setting,
    extract_one_window_features,
    feature_matrix_with_vertical,
    read_frames,
    safeword_triggered,
)
from exp6e_vertical_weight_sweep import read_base_settings  # noqa: E402


DEFAULT_PROFILE_0486 = Setting(
    setting_id=486,
    window_frames=500,
    grid_size=64,
    clusters=13,
    feature_set="exp1",
    velocity_transform="asinh",
    activity_threshold=0.15,
    angular_feature_weight=0.0,
    neighbor_feature_weight=1.0,
    vertical_feature_weight=2.0,
    method="gmm",
    pca_components=0,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Pipeline 1: a source-synchronous fixed-GMM motion-regime overlay. "
            "By default this uses the profile 0486 parameters that isolated the start03 festoon."
        )
    )
    parser.add_argument("--video", type=Path, required=True, help="Resequenced source MP4.")
    parser.add_argument("--out-root", type=Path, required=True, help="Output artifact directory.")
    parser.add_argument("--run-label", default="", help="Short label used in metadata and filenames.")
    parser.add_argument("--source-manifest", type=Path, default=None)
    parser.add_argument("--profile-id", type=int, default=486)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument(
        "--end-frame",
        type=int,
        default=None,
        help="Exclusive end frame. Defaults to the probed source-video frame count.",
    )
    parser.add_argument("--frame-count", type=int, default=None, help="Alternative to --end-frame.")
    parser.add_argument("--mode", choices=("fixed", "decay", "both"), default="both")
    parser.add_argument("--decay-half-life-frames", type=float, default=125.0)
    parser.add_argument("--fit-sample-stride", type=int, default=250)
    parser.add_argument("--chunk-target-frames", type=int, default=250)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--min-active-fraction", type=float, default=0.005)
    parser.add_argument("--diptych", action="store_true", help="Also write source/overlay side-by-side MP4s.")
    parser.add_argument(
        "--stats",
        choices=("none", "summary", "per-frame"),
        default="summary",
        help="Write no stats, aggregate cluster summary, or per-frame cluster stats plus summary.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    parser.add_argument("--window-frames", type=int, default=None)
    parser.add_argument("--grid-size", type=int, default=None)
    parser.add_argument("--clusters", type=int, default=None)
    parser.add_argument("--feature-set", choices=("velocity", "beginner", "exp1", "full"), default=None)
    parser.add_argument("--velocity-transform", choices=("raw", "log1p", "sqrt", "asinh"), default=None)
    parser.add_argument("--activity-threshold", type=float, default=None)
    parser.add_argument("--angular-feature-weight", type=float, default=None)
    parser.add_argument("--neighbor-feature-weight", type=float, default=None)
    parser.add_argument("--vertical-feature-weight", type=float, default=None)
    parser.add_argument("--pca-components", type=int, default=None)
    return parser.parse_args()


def probe_video(video: Path) -> tuple[int, float, int, int]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return frame_count, fps, width, height


def read_profile(args: argparse.Namespace) -> Setting:
    if args.source_manifest is not None:
        setting = read_base_settings(args.source_manifest.expanduser(), [args.profile_id])[0]
        if args.profile_id == 486 and args.vertical_feature_weight is None:
            setting = replace(setting, vertical_feature_weight=2.0)
    elif args.profile_id == 486:
        setting = DEFAULT_PROFILE_0486
    else:
        raise ValueError("--source-manifest is required for profile ids other than 486")

    overrides = {
        "window_frames": args.window_frames,
        "grid_size": args.grid_size,
        "clusters": args.clusters,
        "feature_set": args.feature_set,
        "velocity_transform": args.velocity_transform,
        "activity_threshold": args.activity_threshold,
        "angular_feature_weight": args.angular_feature_weight,
        "neighbor_feature_weight": args.neighbor_feature_weight,
        "vertical_feature_weight": args.vertical_feature_weight,
        "pca_components": args.pca_components,
    }
    clean = {key: value for key, value in overrides.items() if value is not None}
    return replace(setting, **clean)


def branch_names(mode: str) -> list[tuple[str, float]]:
    if mode == "fixed":
        return [("fixed", 0.0)]
    if mode == "decay":
        return [("decay", None)]
    return [("fixed", 0.0), ("decay", None)]


def resolve_range(args: argparse.Namespace, frame_count: int) -> tuple[int, int]:
    start = max(0, args.start_frame)
    if args.frame_count is not None:
        end = start + args.frame_count
    elif args.end_frame is not None:
        end = args.end_frame
    else:
        end = frame_count
    if frame_count:
        end = min(end, frame_count)
    if end <= start:
        raise ValueError(f"Empty frame range: start={start}, end={end}")
    return start, end


def output_stem(branch: str, start: int, end: int, decay_half_life: float) -> str:
    if branch == "fixed":
        return f"pipeline_1_fixed_frames{start}_{end - 1}"
    label = f"h{decay_half_life:g}".replace(".", "p")
    return f"pipeline_1_decay_{label}_frames{start}_{end - 1}"


def read_color_frames(video: Path, start_frame: int, end_frame: int, width: int) -> tuple[list[np.ndarray], float]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    height = max(1, round(width * source_height / source_width))
    frames = []
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    for _ in range(start_frame, end_frame):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA))
    cap.release()
    return frames, fps


def draw_caption(frame: np.ndarray, lines: list[str], top_mask_height: int) -> None:
    height, width = frame.shape[:2]
    if top_mask_height > 0:
        cv2.rectangle(frame, (0, 0), (width, min(top_mask_height, height)), (0, 0, 0), thickness=-1)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1
    y = 26
    for line in lines:
        (text_width, text_height), baseline = cv2.getTextSize(line, font, scale, thickness)
        line_scale = scale * min(1.0, (width - 24) / max(1, text_width))
        (text_width, text_height), baseline = cv2.getTextSize(line, font, line_scale, thickness)
        x = max(12, (width - text_width) // 2)
        cv2.putText(frame, line, (x, y), font, line_scale, (255, 255, 255), thickness, cv2.LINE_AA)
        y += text_height + baseline + 8


def draw_warmup_frame(frame: np.ndarray, target_frame: int, fps: float, setting: Setting, top_mask_height: int) -> np.ndarray:
    draw_caption(
        frame,
        [
            f"source_frame {target_frame} t={target_frame / fps:.3f}s warmup",
            f"waiting for {setting.window_frames}-frame lookback window",
        ],
        top_mask_height,
    )
    return frame


def draw_overlay_frame(
    frame: np.ndarray,
    features,
    vertical,
    labels: np.ndarray,
    probs: np.ndarray,
    setting: Setting,
    target_frame: int,
    fps: float,
    top_mask_height: int,
    min_active_fraction: float,
) -> np.ndarray:
    height, width = frame.shape[:2]
    colors = palette(probs.shape[1])
    overlay = frame.copy()
    cell_w = width / setting.grid_size
    cell_h = height / setting.grid_size
    for feature, label in zip(features, labels, strict=True):
        color = colors[int(label) % len(colors)]
        x0 = int(feature.cell_col * cell_w)
        y0 = int(feature.cell_row * cell_h)
        x1 = int((feature.cell_col + 1) * cell_w)
        y1 = int((feature.cell_row + 1) * cell_h)
        alpha_signal = max(
            feature.active_fraction,
            min(1.0, vertical[(feature.cell_row, feature.cell_col)]["column_continuity"]),
        )
        if alpha_signal > 0.002:
            cv2.rectangle(overlay, (x0, y0), (x1, y1), color, thickness=-1)
        if feature.active_fraction >= min_active_fraction:
            cx = int(feature.x_center)
            cy = int(feature.y_center)
            end = (int(cx + feature.mean_vx * 10), int(cy + feature.mean_vy * 10))
            cv2.arrowedLine(frame, (cx, cy), end, color, 2, tipLength=0.35)
    frame = cv2.addWeighted(overlay, 0.28, frame, 0.72, 0)
    draw_caption(
        frame,
        [
            (
                f"source_frame {target_frame} t={target_frame / fps:.3f}s "
                f"window {target_frame - setting.window_frames + 1}-{target_frame} "
                f"base {setting.setting_id:04d}"
            ),
            (
                f"w{setting.window_frames} g{setting.grid_size} k{setting.clusters} "
                f"{setting.feature_set} {setting.velocity_transform} "
                f"ang{setting.angular_feature_weight:g} nbr{setting.neighbor_feature_weight:g} "
                f"vert{setting.vertical_feature_weight:g}"
            ),
        ],
        top_mask_height,
    )
    return frame


def predict_with_fixed_model(x: np.ndarray, feature_names: list[str], bundle: object, setting: Setting) -> tuple[np.ndarray, np.ndarray]:
    z = bundle["scaler"].transform(x)
    apply_feature_weights(
        z,
        feature_names,
        setting.angular_feature_weight,
        setting.neighbor_feature_weight,
        setting.vertical_feature_weight,
    )
    if bundle.get("pca") is not None:
        z = bundle["pca"].transform(z)
    model = bundle["model"]
    probs = model.predict_proba(z)
    labels = np.argmax(probs, axis=1)
    return labels, probs


def fit_fixed_model(
    video: Path,
    valid_targets: list[int],
    setting: Setting,
    flow_scale_width: int,
    sample_stride: int,
    decay_half_life_frames: float,
    safeword_file: Path,
) -> tuple[object, list[str], int]:
    sample_targets = valid_targets[:: max(1, sample_stride)]
    if not sample_targets:
        raise ValueError("No valid target frames available for fixed-GMM fitting")
    matrices = []
    feature_names = None
    total = len(sample_targets)
    for index, target_frame in enumerate(sample_targets, start=1):
        if safeword_triggered(safeword_file):
            raise RuntimeError("safeword detected while fitting fixed model")
        read_start = target_frame - setting.window_frames + 1
        gray_frames, _ = read_frames(video, read_start, setting.window_frames, flow_scale_width)
        flows = compute_flows(gray_frames)
        features, vertical = extract_one_window_features(
            flows,
            target_frame,
            setting.window_frames,
            setting,
            decay_half_life_frames,
        )
        x, feature_names = feature_matrix_with_vertical(features, vertical, setting)
        matrices.append(x)
        print(f"fixed-model sample {index:,}/{total:,} target_frame={target_frame}", flush=True)
    x_fit = np.vstack(matrices)
    _, _, bundle = fit_clusters(
        x_fit,
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
    return bundle, feature_names, len(sample_targets)


def init_summary_stats(cluster_count: int) -> list[dict[str, float]]:
    return [
        {
            "label": float(label),
            "count": 0.0,
            "mean_probability": 0.0,
            "mean_speed": 0.0,
            "active_fraction": 0.0,
            "alignment": 0.0,
            "direction_concentration": 0.0,
            "column_continuity": 0.0,
            "vertical_strand_score": 0.0,
        }
        for label in range(cluster_count)
    ]


def update_stats(stats: list[dict[str, float]], features, vertical, labels: np.ndarray, probs: np.ndarray) -> None:
    for feature, label, prob_row in zip(features, labels, probs, strict=True):
        row = stats[int(label)]
        row["count"] += 1
        row["mean_probability"] += float(np.max(prob_row))
        row["mean_speed"] += feature.mean_speed
        row["active_fraction"] += feature.active_fraction
        row["alignment"] += feature.alignment
        row["direction_concentration"] += feature.direction_concentration
        vertical_values = vertical[(feature.cell_row, feature.cell_col)]
        row["column_continuity"] += vertical_values["column_continuity"]
        row["vertical_strand_score"] += vertical_values["vertical_strand_score"]


def per_frame_rows(target_frame: int, features, vertical, labels: np.ndarray, probs: np.ndarray) -> list[dict[str, float]]:
    grouped: dict[int, dict[str, float]] = {}
    for feature, label, prob_row in zip(features, labels, probs, strict=True):
        row = grouped.setdefault(
            int(label),
            {
                "source_frame": float(target_frame),
                "cluster": float(label),
                "count": 0.0,
                "mean_probability": 0.0,
                "mean_speed": 0.0,
                "active_fraction": 0.0,
                "alignment": 0.0,
                "vertical_strand_score": 0.0,
                "column_continuity": 0.0,
            },
        )
        row["count"] += 1
        row["mean_probability"] += float(np.max(prob_row))
        row["mean_speed"] += feature.mean_speed
        row["active_fraction"] += feature.active_fraction
        row["alignment"] += feature.alignment
        vertical_values = vertical[(feature.cell_row, feature.cell_col)]
        row["vertical_strand_score"] += vertical_values["vertical_strand_score"]
        row["column_continuity"] += vertical_values["column_continuity"]
    rows = []
    for row in grouped.values():
        count = row["count"] or 1.0
        for key in (
            "mean_probability",
            "mean_speed",
            "active_fraction",
            "alignment",
            "vertical_strand_score",
            "column_continuity",
        ):
            row[key] /= count
        rows.append(row)
    return sorted(rows, key=lambda item: int(item["cluster"]))


def write_summary_stats(path: Path, stats: list[dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = sum(row["count"] for row in stats) or 1.0
    fieldnames = [
        "cluster",
        "count",
        "share",
        "mean_probability",
        "mean_speed",
        "active_fraction",
        "alignment",
        "direction_concentration",
        "column_continuity",
        "vertical_strand_score",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in stats:
            count = row["count"] or 1.0
            writer.writerow(
                {
                    "cluster": int(row["label"]),
                    "count": int(row["count"]),
                    "share": row["count"] / total,
                    "mean_probability": row["mean_probability"] / count,
                    "mean_speed": row["mean_speed"] / count,
                    "active_fraction": row["active_fraction"] / count,
                    "alignment": row["alignment"] / count,
                    "direction_concentration": row["direction_concentration"] / count,
                    "column_continuity": row["column_continuity"] / count,
                    "vertical_strand_score": row["vertical_strand_score"] / count,
                }
            )


def append_csv(path: Path, rows: list[dict[str, float]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def render_branch(
    args: argparse.Namespace,
    video: Path,
    out_root: Path,
    setting: Setting,
    start: int,
    end: int,
    branch: str,
    decay_half_life: float,
    fps: float,
    source_width: int,
    source_height: int,
    safeword_file: Path,
) -> dict:
    scale_width = args.flow_scale_width
    scale_height = max(1, round(scale_width * source_height / source_width))
    stem = output_stem(branch, start, end, decay_half_life)
    overlay_path = out_root / f"{stem}.mp4"
    diptych_path = out_root / f"{stem}_diptych.mp4"
    summary_path = out_root / f"{stem}_cluster_summary.csv"
    per_frame_path = out_root / f"{stem}_per_frame_cluster_stats.csv"

    print(f"fitting Pipeline 1 {branch} model", flush=True)
    all_targets = list(range(start, end))
    valid_targets = [frame for frame in all_targets if frame >= setting.window_frames - 1]
    fixed_bundle, _, fit_samples = fit_fixed_model(
        video,
        valid_targets,
        setting,
        scale_width,
        args.fit_sample_stride,
        decay_half_life,
        safeword_file,
    )

    overlay_writer = cv2.VideoWriter(
        str(overlay_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (scale_width, scale_height),
    )
    if not overlay_writer.isOpened():
        raise RuntimeError(f"Could not open writer: {overlay_path}")
    diptych_writer = None
    if args.diptych:
        diptych_writer = cv2.VideoWriter(
            str(diptych_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (scale_width * 2, scale_height),
        )
        if not diptych_writer.isOpened():
            raise RuntimeError(f"Could not open writer: {diptych_path}")

    stats = init_summary_stats(setting.clusters)
    written = 0
    started = time.monotonic()

    for chunk_start in range(start, end, args.chunk_target_frames):
        if safeword_triggered(safeword_file):
            print("safeword detected; stopping branch cleanly", flush=True)
            break
        chunk_end = min(end, chunk_start + args.chunk_target_frames)
        chunk_targets = list(range(chunk_start, chunk_end))
        color_frames, _ = read_color_frames(video, chunk_start, chunk_end, scale_width)
        if len(color_frames) != len(chunk_targets):
            print(
                f"warning: read {len(color_frames)} color frames for {len(chunk_targets)} targets",
                flush=True,
            )
            chunk_targets = chunk_targets[: len(color_frames)]

        valid_chunk_targets = [frame for frame in chunk_targets if frame >= setting.window_frames - 1]
        flows = None
        read_start = None
        if valid_chunk_targets:
            read_start = valid_chunk_targets[0] - setting.window_frames + 1
            read_stop = valid_chunk_targets[-1]
            gray_frames, _ = read_frames(video, read_start, read_stop - read_start + 1, scale_width)
            flows = compute_flows(gray_frames)

        for target_frame, source_frame in zip(chunk_targets, color_frames, strict=False):
            if target_frame < setting.window_frames - 1:
                overlay_frame = draw_warmup_frame(
                    source_frame.copy(),
                    target_frame,
                    fps,
                    setting,
                    args.top_mask_height,
                )
            else:
                assert flows is not None
                assert read_start is not None
                local_start = target_frame - setting.window_frames + 1 - read_start
                local_stop = target_frame - read_start
                flow_slice = flows[local_start:local_stop]
                features, vertical = extract_one_window_features(
                    flow_slice,
                    target_frame,
                    setting.window_frames,
                    setting,
                    decay_half_life,
                )
                x, feature_names = feature_matrix_with_vertical(features, vertical, setting)
                labels, probs = predict_with_fixed_model(x, feature_names, fixed_bundle, setting)
                update_stats(stats, features, vertical, labels, probs)
                if args.stats == "per-frame":
                    append_csv(per_frame_path, per_frame_rows(target_frame, features, vertical, labels, probs))
                overlay_frame = draw_overlay_frame(
                    source_frame.copy(),
                    features,
                    vertical,
                    labels,
                    probs,
                    setting,
                    target_frame,
                    fps,
                    args.top_mask_height,
                    args.min_active_fraction,
                )

            overlay_writer.write(overlay_frame)
            if diptych_writer is not None:
                diptych_writer.write(np.hstack([source_frame, overlay_frame]))
            written += 1

        print(f"{branch}: wrote {written:,}/{end - start:,} source-synchronous frames", flush=True)

    overlay_writer.release()
    if diptych_writer is not None:
        diptych_writer.release()
    if args.stats in {"summary", "per-frame"}:
        write_summary_stats(summary_path, stats)

    elapsed = time.monotonic() - started
    return {
        "branch": branch,
        "decay_half_life_frames": decay_half_life,
        "overlay_video": str(overlay_path),
        "diptych_video": str(diptych_path) if args.diptych else None,
        "cluster_summary_csv": str(summary_path) if args.stats in {"summary", "per-frame"} else None,
        "per_frame_cluster_stats_csv": str(per_frame_path) if args.stats == "per-frame" else None,
        "written_frames": written,
        "fit_sample_count": fit_samples,
        "elapsed_seconds": elapsed,
    }


def main() -> None:
    args = parse_args()
    started = time.monotonic()
    video = args.video.expanduser()
    out_root = args.out_root.expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    frame_count, fps, source_width, source_height = probe_video(video)
    start, end = resolve_range(args, frame_count)
    setting = read_profile(args)
    branches = [
        (name, args.decay_half_life_frames if decay is None else decay)
        for name, decay in branch_names(args.mode)
    ]
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline": "pipeline_1",
        "run_label": args.run_label,
        "video": str(video),
        "video_frame_count": frame_count,
        "fps": fps,
        "source_width": source_width,
        "source_height": source_height,
        "start_frame": start,
        "end_frame_exclusive": end,
        "frame_count": end - start,
        "profile": asdict(setting),
        "mode": args.mode,
        "branches": [{"branch": name, "decay_half_life_frames": decay} for name, decay in branches],
        "fit_sample_stride": args.fit_sample_stride,
        "chunk_target_frames": args.chunk_target_frames,
        "flow_scale_width": args.flow_scale_width,
        "top_mask_height": args.top_mask_height,
        "diptych": args.diptych,
        "stats": args.stats,
        "dry_run": args.dry_run,
    }
    metadata_path = out_root / "pipeline_1_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

    print(json.dumps(metadata, indent=2), flush=True)
    if args.dry_run:
        print(f"dry run only; wrote metadata plan: {metadata_path}", flush=True)
        return

    outputs = []
    for branch, decay_half_life in branches:
        outputs.append(
            render_branch(
                args,
                video,
                out_root,
                setting,
                start,
                end,
                branch,
                decay_half_life,
                fps,
                source_width,
                source_height,
                safeword_file,
            )
        )
    metadata["outputs"] = outputs
    metadata["elapsed_seconds"] = time.monotonic() - started
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"wrote metadata: {metadata_path}", flush=True)


if __name__ == "__main__":
    main()
