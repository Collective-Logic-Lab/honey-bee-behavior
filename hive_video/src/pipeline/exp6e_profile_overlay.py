#!/usr/bin/env python3
"""Render a repaired Experiment 6e profile overlay video for a frame interval."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

HIVE_VIDEO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = HIVE_VIDEO_ROOT / "src" / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from exp6_frame_sweep import (  # noqa: E402
    extract_one_window_features,
    feature_matrix_with_vertical,
    fit_clusters,
    read_frames,
    safeword_triggered,
)
from annotate_motion_regimes import apply_feature_weights, compute_flows, palette  # noqa: E402
from exp6e_vertical_weight_sweep import (  # noqa: E402
    DEFAULT_SOURCE_MANIFEST,
    DEFAULT_VIDEO,
    read_base_settings,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a full overlay video for one Experiment 6e profile.")
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-setting-id", type=int, default=486)
    parser.add_argument("--vertical-weight", type=float, default=1.0)
    parser.add_argument("--start-frame", type=int, default=215000)
    parser.add_argument("--end-frame", type=int, default=235000, help="Exclusive end frame.")
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--chunk-target-frames", type=int, default=250)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--min-active-fraction", type=float, default=0.005)
    parser.add_argument(
        "--decay-half-life-frames",
        type=float,
        default=0.0,
        help="Use exponential temporal decay inside each lookback window; 0 keeps a flat window.",
    )
    parser.add_argument(
        "--fixed-gmm",
        action="store_true",
        help="Fit one model on sampled target frames, then reuse it for every rendered frame.",
    )
    parser.add_argument(
        "--fit-sample-stride",
        type=int,
        default=25,
        help="When --fixed-gmm is used, fit on every Nth target frame.",
    )
    parser.add_argument(
        "--stabilize-colors",
        action="store_true",
        help="Map each frame's cluster ids onto the previous frame's display ids by cell-label overlap.",
    )
    parser.add_argument(
        "--endnotes",
        action="store_true",
        help="Append cluster-interpretation cards computed from the rendered interval.",
    )
    parser.add_argument("--endnote-seconds", type=float, default=5.0)
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    return parser.parse_args()


def read_color_frames(video: Path, start_frame: int, end_frame: int, stride: int, width: int) -> tuple[list[np.ndarray], float]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    height = max(1, round(width * source_height / source_width))
    frames = []
    for frame_idx in range(start_frame, end_frame, stride):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA))
    cap.release()
    return frames, fps


def scaled_video_size(video: Path, width: int) -> tuple[int, int, float]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return width, max(1, round(width * source_height / source_width)), fps


def draw_overlay_frame(
    frame: np.ndarray,
    features,
    vertical,
    labels: np.ndarray,
    probs: np.ndarray,
    setting,
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
        color = colors[int(label)]
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

    if top_mask_height > 0:
        cv2.rectangle(frame, (0, 0), (width, min(top_mask_height, height)), (0, 0, 0), thickness=-1)
    lines = [
        f"frame {target_frame} t={target_frame / fps:.1f}s base {setting.setting_id:04d}",
        (
            f"w{setting.window_frames} g{setting.grid_size} k{setting.clusters} "
            f"{setting.feature_set} {setting.velocity_transform} "
            f"ang{setting.angular_feature_weight:g} nbr{setting.neighbor_feature_weight:g} "
            f"vert{setting.vertical_feature_weight:g}"
        ),
    ]
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
    return frame


def stabilize_labels_to_previous(
    labels: np.ndarray,
    previous_display_labels: np.ndarray | None,
    cluster_count: int,
) -> np.ndarray:
    """Relabel current clusters to preserve display colors across adjacent frames."""
    if previous_display_labels is None:
        return labels.astype(int, copy=True)

    labels = labels.astype(int, copy=False)
    previous_display_labels = previous_display_labels.astype(int, copy=False)
    counts = np.zeros((cluster_count, cluster_count), dtype=np.int64)
    for current_label, previous_label in zip(labels, previous_display_labels, strict=True):
        if 0 <= current_label < cluster_count and 0 <= previous_label < cluster_count:
            counts[current_label, previous_label] += 1

    mapping: dict[int, int] = {}
    used_current: set[int] = set()
    used_display: set[int] = set()
    candidates = [
        (int(counts[current_label, display_label]), current_label, display_label)
        for current_label in range(cluster_count)
        for display_label in range(cluster_count)
    ]
    for count, current_label, display_label in sorted(candidates, reverse=True):
        if count <= 0:
            break
        if current_label in used_current or display_label in used_display:
            continue
        mapping[current_label] = display_label
        used_current.add(current_label)
        used_display.add(display_label)

    unused_display = [label for label in range(cluster_count) if label not in used_display]
    for current_label in range(cluster_count):
        if current_label not in mapping:
            mapping[current_label] = unused_display.pop(0) if unused_display else current_label

    return np.array([mapping.get(int(label), int(label)) for label in labels], dtype=int)


def predict_with_fixed_model(
    x: np.ndarray,
    feature_names: list[str],
    model_bundle: object,
    setting,
) -> tuple[np.ndarray, np.ndarray]:
    z = model_bundle["scaler"].transform(x)
    apply_feature_weights(
        z,
        feature_names,
        setting.angular_feature_weight,
        setting.neighbor_feature_weight,
        setting.vertical_feature_weight,
    )
    if model_bundle.get("pca") is not None:
        z = model_bundle["pca"].transform(z)
    model = model_bundle["model"]
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(z)
        labels = np.argmax(probs, axis=1)
    else:
        labels = model.predict(z)
        probs = np.zeros((len(labels), setting.clusters), dtype=np.float32)
        probs[np.arange(len(labels)), labels] = 1.0
    return labels, probs


def fit_fixed_model(
    video: Path,
    target_frames: list[int],
    setting,
    flow_scale_width: int,
    sample_stride: int,
    decay_half_life_frames: float,
    safeword_file: Path,
) -> tuple[object, list[str]]:
    sample_targets = target_frames[:: max(1, sample_stride)]
    matrices = []
    feature_names = None
    total = len(sample_targets)
    for idx, target_frame in enumerate(sample_targets, start=1):
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
        print(f"fixed-model sample {idx:,}/{total:,} target_frame={target_frame}", flush=True)
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
    return bundle, feature_names


def make_cluster_stats(cluster_count: int) -> list[dict[str, float]]:
    return [
        {
            "count": 0.0,
            "mean_speed": 0.0,
            "active_fraction": 0.0,
            "alignment": 0.0,
            "direction_concentration": 0.0,
            "column_continuity": 0.0,
            "vertical_strand_score": 0.0,
            "upper_right_count": 0.0,
            "lower_right_count": 0.0,
        }
        for _ in range(cluster_count)
    ]


def update_cluster_stats(
    stats: list[dict[str, float]],
    features,
    vertical,
    display_labels: np.ndarray,
    top_mask_height: int,
) -> None:
    visible = [feature for feature in features if feature.y_center >= top_mask_height]
    if not visible:
        return
    max_col = max(feature.cell_col for feature in visible)
    max_row = max(feature.cell_row for feature in visible)
    col_mid = (max_col + 1) / 2
    row_mid = (max_row + 1) / 2
    for feature, label in zip(features, display_labels, strict=True):
        if feature.y_center < top_mask_height:
            continue
        row = stats[int(label)]
        row["count"] += 1
        row["mean_speed"] += feature.mean_speed
        row["active_fraction"] += feature.active_fraction
        row["alignment"] += feature.alignment
        row["direction_concentration"] += feature.direction_concentration
        vertical_values = vertical[(feature.cell_row, feature.cell_col)]
        row["column_continuity"] += vertical_values["column_continuity"]
        row["vertical_strand_score"] += vertical_values["vertical_strand_score"]
        if feature.cell_col >= col_mid and feature.cell_row < row_mid:
            row["upper_right_count"] += 1
        if feature.cell_col >= col_mid and feature.cell_row >= row_mid:
            row["lower_right_count"] += 1


def mean_cluster_stats(stats: list[dict[str, float]]) -> list[dict[str, float]]:
    total = sum(row["count"] for row in stats) or 1.0
    means = []
    for label, row in enumerate(stats):
        count = row["count"] or 1.0
        means.append(
            {
                "label": float(label),
                "count": row["count"],
                "share": row["count"] / total,
                "mean_speed": row["mean_speed"] / count,
                "active_fraction": row["active_fraction"] / count,
                "alignment": row["alignment"] / count,
                "direction_concentration": row["direction_concentration"] / count,
                "column_continuity": row["column_continuity"] / count,
                "vertical_strand_score": row["vertical_strand_score"] / count,
                "upper_right_share": row["upper_right_count"] / count,
                "lower_right_share": row["lower_right_count"] / count,
            }
        )
    return means


def put_text_lines(
    frame: np.ndarray,
    lines: list[str],
    x: int,
    y: int,
    scale: float,
    color: tuple[int, int, int] = (235, 235, 235),
    thickness: int = 1,
    line_gap: int = 8,
) -> int:
    font = cv2.FONT_HERSHEY_SIMPLEX
    for line in lines:
        (_, text_height), baseline = cv2.getTextSize(line, font, scale, thickness)
        cv2.putText(frame, line, (x, y), font, scale, color, thickness, cv2.LINE_AA)
        y += text_height + baseline + line_gap
    return y


def endnote_frames(
    width: int,
    height: int,
    fps: float,
    seconds: float,
    setting,
    start_frame: int,
    end_frame: int,
    stabilized: bool,
    stats: list[dict[str, float]],
) -> list[np.ndarray]:
    colors = palette(len(stats))
    means = mean_cluster_stats(stats)
    page = np.zeros((height, width, 3), dtype=np.uint8)
    page[:] = (10, 10, 10)
    lines = [
        "Experiment cluster notes",
        f"frames {start_frame}-{end_frame - 1}; base {setting.setting_id:04d}; stabilized colors: {stabilized}",
        (
            f"w{setting.window_frames} g{setting.grid_size} k{setting.clusters} "
            f"{setting.feature_set} {setting.velocity_transform} "
            f"activity>{setting.activity_threshold:g} ang{setting.angular_feature_weight:g} "
            f"nbr{setting.neighbor_feature_weight:g} vert{setting.vertical_feature_weight:g}"
        ),
        "Rows are means over visible grid cells assigned to each stabilized display color.",
        "C  color  share  speed  active  align  dir  strand  column  UR  LR",
    ]
    y = put_text_lines(page, lines, 24, 36, 0.47)
    row_scale = 0.42
    row_h = 34
    for row in means:
        label = int(row["label"])
        color = colors[label]
        y += 3
        if y > height - row_h:
            break
        cv2.rectangle(page, (64, y - 16), (88, y + 8), color, thickness=-1)
        text = (
            f"{label:02d}        "
            f"{row['share'] * 100:5.1f}%  "
            f"{row['mean_speed']:5.2f}  "
            f"{row['active_fraction']:5.3f}  "
            f"{row['alignment']:5.3f}  "
            f"{row['direction_concentration']:5.3f}  "
            f"{row['vertical_strand_score']:6.3f}  "
            f"{row['column_continuity']:6.3f}  "
            f"{row['upper_right_share']:4.2f}  "
            f"{row['lower_right_share']:4.2f}"
        )
        cv2.putText(page, text, (24, y), cv2.FONT_HERSHEY_SIMPLEX, row_scale, (235, 235, 235), 1, cv2.LINE_AA)
        y += row_h
    note = "UR/LR are upper-right/lower-right shares after excluding the caption band."
    cv2.putText(page, note, (24, height - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (210, 210, 210), 1, cv2.LINE_AA)
    return [page.copy() for _ in range(max(1, int(round(fps * seconds))))]


def main() -> None:
    args = parse_args()
    started = time.monotonic()
    video = args.video.expanduser()
    out = args.out.expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    base_setting = read_base_settings(args.source_manifest.expanduser(), [args.base_setting_id])[0]
    setting = replace(base_setting, vertical_feature_weight=args.vertical_weight)
    first_target = max(args.start_frame, setting.window_frames - 1)
    target_frames = list(range(first_target, args.end_frame, args.stride))
    if not target_frames:
        raise ValueError("No target frames to render")

    scale_width, scale_height, fps = scaled_video_size(video, args.flow_scale_width)
    writer = cv2.VideoWriter(
        str(out),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps / max(1, args.stride),
        (scale_width, scale_height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Could not open output video writer: {out}")

    written = 0
    previous_display_labels: np.ndarray | None = None
    cluster_stats = make_cluster_stats(setting.clusters)
    fixed_bundle = None
    if args.fixed_gmm:
        print("fitting fixed model", flush=True)
        fixed_bundle, _ = fit_fixed_model(
            video,
            target_frames,
            setting,
            args.flow_scale_width,
            args.fit_sample_stride,
            args.decay_half_life_frames,
            safeword_file,
        )
    for chunk_start in range(0, len(target_frames), args.chunk_target_frames):
        if safeword_triggered(safeword_file):
            print("safeword detected; stopping", flush=True)
            break
        chunk_targets = target_frames[chunk_start : chunk_start + args.chunk_target_frames]
        read_start = chunk_targets[0] - setting.window_frames + 1
        read_stop = chunk_targets[-1]
        gray_frames, _ = read_frames(video, read_start, read_stop - read_start + 1, args.flow_scale_width)
        flows = compute_flows(gray_frames)
        color_frames, fps = read_color_frames(
            video,
            chunk_targets[0],
            chunk_targets[-1] + 1,
            args.stride,
            args.flow_scale_width,
        )

        for target_frame, frame in zip(chunk_targets, color_frames, strict=False):
            local_start = target_frame - setting.window_frames + 1 - read_start
            local_stop = target_frame - read_start
            flow_slice = flows[local_start:local_stop]
            features, vertical = extract_one_window_features(
                flow_slice,
                target_frame,
                setting.window_frames,
                setting,
                args.decay_half_life_frames,
            )
            x, feature_names = feature_matrix_with_vertical(features, vertical, setting)
            if fixed_bundle is not None:
                labels, probs = predict_with_fixed_model(x, feature_names, fixed_bundle, setting)
            else:
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
            display_labels = (
                stabilize_labels_to_previous(labels, previous_display_labels, probs.shape[1])
                if args.stabilize_colors
                else labels
            )
            previous_display_labels = display_labels
            update_cluster_stats(cluster_stats, features, vertical, display_labels, args.top_mask_height)
            writer.write(
                draw_overlay_frame(
                    frame,
                    features,
                    vertical,
                    display_labels,
                    probs,
                    setting,
                    target_frame,
                    fps,
                    args.top_mask_height,
                    args.min_active_fraction,
                )
            )
            written += 1
        print(f"wrote {written:,}/{len(target_frames):,} overlay frames", flush=True)

    if args.endnotes and written:
        for frame in endnote_frames(
            scale_width,
            scale_height,
            fps / max(1, args.stride),
            args.endnote_seconds,
            setting,
            target_frames[0],
            target_frames[min(written, len(target_frames)) - 1] + 1,
            args.stabilize_colors,
            cluster_stats,
        ):
            writer.write(frame)

    writer.release()
    print(f"wrote overlay video: {out}", flush=True)
    print(f"elapsed wall time: {time.monotonic() - started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
