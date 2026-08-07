#!/usr/bin/env python3
"""Experiment 6: one-frame parameter sweep for festoon-formation review."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HIVE_VIDEO_ROOT = Path(__file__).resolve().parents[2]
ANALYZE_DIR = HIVE_VIDEO_ROOT / "src" / "analyze"
if str(ANALYZE_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYZE_DIR))

from annotate_motion_regimes import (  # noqa: E402
    FEATURE_SETS,
    add_neighbor_contrasts,
    cell_slices,
    compute_flows,
    feature_matrix,
    fit_clusters,
    palette,
    read_frames,
    summarize_cell,
)


@dataclass(frozen=True)
class Setting:
    setting_id: int
    window_frames: int
    grid_size: int
    clusters: int
    feature_set: str
    velocity_transform: str
    activity_threshold: float
    angular_feature_weight: float
    neighbor_feature_weight: float
    vertical_feature_weight: float
    method: str = "gmm"
    pca_components: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a deterministic parameter sweep at a few target frames and render one "
            "annotated still per target/setting, plus contact sheets for fast visual review."
        )
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=Path("data/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4"),
    )
    parser.add_argument("--out-root", type=Path, default=Path("data/no-sync/exp6a_frame_sweep_start03"))
    parser.add_argument("--target-frames", default="227250,227840,231546,242063")
    parser.add_argument("--max-settings", type=int, default=1000)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--contact-sheet-cols", type=int, default=5)
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def label_number(value: float | int) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", "p")


def safeword_triggered(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(errors="ignore").casefold()
    except OSError:
        return False
    return "sea cucumber" in text or "seacucubmer" in text


def make_settings(max_settings: int) -> list[Setting]:
    # Broad but deterministic. The full grid is larger than max_settings; striding
    # through it gives coverage without making the output impossible to review.
    full_grid = list(
        itertools.product(
            [25, 50, 125, 250, 500, 1000],
            [32, 48, 64],
            [4, 6, 8, 10, 12],
            ["velocity", "beginner", "exp1", "full"],
            ["raw", "log1p", "sqrt", "asinh"],
            [0.15, 0.30, 0.50],
            [0.0, 1.0, 2.0, 4.0],
            [0.0, 1.0, 2.0, 4.0],
            [0.0, 1.0, 2.0, 4.0],
        )
    )
    if max_settings >= len(full_grid):
        selected = full_grid
    else:
        step = len(full_grid) / max_settings
        selected = [full_grid[min(len(full_grid) - 1, int(i * step))] for i in range(max_settings)]

    forced = [
        (250, 64, 8, "full", "raw", 0.30, 2.0, 1.5, 0.0),
        (250, 64, 8, "full", "raw", 0.30, 3.0, 1.5, 0.0),
        (500, 64, 8, "full", "raw", 0.30, 2.0, 1.5, 1.0),
        (1000, 64, 8, "full", "raw", 0.30, 2.0, 1.5, 2.0),
        (250, 64, 8, "full", "asinh", 0.30, 2.0, 1.5, 2.0),
    ]
    selected = [*forced, *selected]
    deduped = []
    seen = set()
    for item in selected:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
        if len(deduped) >= max_settings:
            break

    return [
        Setting(
            setting_id=index,
            window_frames=item[0],
            grid_size=item[1],
            clusters=item[2],
            feature_set=item[3],
            velocity_transform=item[4],
            activity_threshold=item[5],
            angular_feature_weight=item[6],
            neighbor_feature_weight=item[7],
            vertical_feature_weight=item[8],
        )
        for index, item in enumerate(deduped, start=1)
    ]


def cell_feature_map(features) -> dict[tuple[int, int], object]:
    return {(feature.cell_row, feature.cell_col): feature for feature in features}


def vertical_metrics(features, rows: int, cols: int) -> dict[tuple[int, int], dict[str, float]]:
    by_cell = cell_feature_map(features)
    metrics: dict[tuple[int, int], dict[str, float]] = {}
    for feature in features:
        vertical = [
            by_cell[key]
            for key in ((feature.cell_row - 1, feature.cell_col), (feature.cell_row + 1, feature.cell_col))
            if key in by_cell
        ]
        horizontal = [
            by_cell[key]
            for key in ((feature.cell_row, feature.cell_col - 1), (feature.cell_row, feature.cell_col + 1))
            if key in by_cell
        ]

        def mean_abs_delta(neighbors, attr: str) -> float:
            if not neighbors:
                return 0.0
            value = getattr(feature, attr)
            return float(np.mean([abs(value - getattr(neighbor, attr)) for neighbor in neighbors]))

        vertical_activity = 1.0 / (1.0 + mean_abs_delta(vertical, "active_fraction"))
        horizontal_activity = 1.0 / (1.0 + mean_abs_delta(horizontal, "active_fraction"))
        vertical_alignment = 1.0 / (1.0 + mean_abs_delta(vertical, "alignment"))
        horizontal_alignment = 1.0 / (1.0 + mean_abs_delta(horizontal, "alignment"))
        vertical_direction = 1.0 / (1.0 + mean_abs_delta(vertical, "direction_concentration"))
        horizontal_direction = 1.0 / (1.0 + mean_abs_delta(horizontal, "direction_concentration"))
        column_continuity = sum(neighbor.active_fraction for neighbor in vertical) / max(1, len(vertical))
        strand_score = (
            (vertical_activity - horizontal_activity)
            + (vertical_alignment - horizontal_alignment)
            + (vertical_direction - horizontal_direction)
            + column_continuity
        )
        metrics[(feature.cell_row, feature.cell_col)] = {
            "vertical_activity_coherence": vertical_activity,
            "horizontal_activity_coherence": horizontal_activity,
            "vertical_alignment_coherence": vertical_alignment,
            "horizontal_alignment_coherence": horizontal_alignment,
            "vertical_direction_coherence": vertical_direction,
            "horizontal_direction_coherence": horizontal_direction,
            "column_continuity": column_continuity,
            "vertical_strand_score": strand_score,
        }
    return metrics


def extract_one_window_features(
    flows: list[np.ndarray],
    target_frame: int,
    max_window_frames: int,
    setting: Setting,
) -> tuple[list, dict[tuple[int, int], dict[str, float]]]:
    flow_window = max(1, setting.window_frames - 1)
    flow_stack = np.stack(flows[-flow_window:])
    height, width = flows[0].shape[:2]
    frame_start = target_frame - setting.window_frames + 1
    features = []
    for row, col, y_slice, x_slice in cell_slices(height, width, setting.grid_size, setting.grid_size):
        features.append(
            summarize_cell(
                0,
                frame_start,
                target_frame,
                row,
                col,
                y_slice,
                x_slice,
                flow_stack,
                setting.activity_threshold,
            )
        )
    features = add_neighbor_contrasts(features, setting.grid_size, setting.grid_size)
    vertical = vertical_metrics(features, setting.grid_size, setting.grid_size)
    return features, vertical


def feature_matrix_with_vertical(features, vertical, setting: Setting) -> tuple[np.ndarray, list[str]]:
    x = feature_matrix(features, setting.velocity_transform, setting.feature_set)
    names = list(FEATURE_SETS[setting.feature_set])
    vertical_names = [
        "vertical_activity_coherence",
        "vertical_alignment_coherence",
        "vertical_direction_coherence",
        "column_continuity",
        "vertical_strand_score",
    ]
    vertical_rows = []
    for feature in features:
        values = vertical[(feature.cell_row, feature.cell_col)]
        vertical_rows.append([values[name] for name in vertical_names])
    v = np.array(vertical_rows, dtype=np.float64)
    return np.column_stack([x, v]), [*names, *vertical_names]


def read_target_frame(video: Path, frame_idx: int, width: int) -> tuple[np.ndarray, float]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    height = max(1, round(width * source_height / source_width))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Could not read target frame {frame_idx}")
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA), fps


def draw_still(
    frame: np.ndarray,
    out_path: Path,
    features,
    vertical,
    labels: np.ndarray,
    probs: np.ndarray,
    setting: Setting,
    target_frame: int,
    fps: float,
    top_mask_height: int,
) -> None:
    height, width = frame.shape[:2]
    grid = setting.grid_size
    colors = palette(probs.shape[1])
    overlay = frame.copy()
    for feature, label, prob_row in zip(features, labels, probs, strict=True):
        color = colors[int(label)]
        cell_w = width / grid
        cell_h = height / grid
        x0 = int(feature.cell_col * cell_w)
        y0 = int(feature.cell_row * cell_h)
        x1 = int((feature.cell_col + 1) * cell_w)
        y1 = int((feature.cell_row + 1) * cell_h)
        alpha_signal = max(feature.active_fraction, min(1.0, vertical[(feature.cell_row, feature.cell_col)]["column_continuity"]))
        if alpha_signal > 0.002:
            cv2.rectangle(overlay, (x0, y0), (x1, y1), color, thickness=-1)
        if feature.active_fraction >= 0.005:
            cx = int(feature.x_center)
            cy = int(feature.y_center)
            end = (int(cx + feature.mean_vx * 10), int(cy + feature.mean_vy * 10))
            cv2.arrowedLine(frame, (cx, cy), end, color, 2, tipLength=0.35)
    frame = cv2.addWeighted(overlay, 0.28, frame, 0.72, 0)
    if top_mask_height > 0:
        cv2.rectangle(frame, (0, 0), (width, min(top_mask_height, height)), (0, 0, 0), thickness=-1)
    text_lines = [
        f"frame {target_frame} t={target_frame / fps:.1f}s setting {setting.setting_id:04d}",
        (
            f"w{setting.window_frames} g{grid} k{setting.clusters} {setting.feature_set} "
            f"{setting.velocity_transform} ang{setting.angular_feature_weight:g} "
            f"nbr{setting.neighbor_feature_weight:g} vert{setting.vertical_feature_weight:g}"
        ),
    ]
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1
    y = 26
    for line in text_lines:
        (text_width, text_height), baseline = cv2.getTextSize(line, font, scale, thickness)
        if text_width > width - 24:
            line_scale = scale * (width - 24) / text_width
        else:
            line_scale = scale
        (text_width, text_height), baseline = cv2.getTextSize(line, font, line_scale, thickness)
        x = max(12, (width - text_width) // 2)
        cv2.putText(frame, line, (x, y), font, line_scale, (255, 255, 255), thickness, cv2.LINE_AA)
        y += text_height + baseline + 8
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)


def summarize_scores(features, vertical, labels, probs) -> dict:
    rows = [feature for feature in features if feature.y_center >= 72]
    if not rows:
        return {}
    max_col = max(feature.cell_col for feature in rows)
    max_row = max(feature.cell_row for feature in rows)
    col_mid = (max_col + 1) / 2
    row_mid = (max_row + 1) / 2
    upper_right = [feature for feature in rows if feature.cell_col >= col_mid and feature.cell_row < row_mid]
    lower_right = [feature for feature in rows if feature.cell_col >= col_mid and feature.cell_row >= row_mid]
    label_by_cell = {(feature.cell_row, feature.cell_col): int(label) for feature, label in zip(features, labels, strict=True)}

    def avg_label(region) -> float:
        return float(np.mean([label_by_cell[(feature.cell_row, feature.cell_col)] for feature in region])) if region else math.nan

    def avg_vertical(region, name: str) -> float:
        return float(np.mean([vertical[(feature.cell_row, feature.cell_col)][name] for feature in region])) if region else math.nan

    return {
        "ur_count": len(upper_right),
        "lr_count": len(lower_right),
        "avg_cluster_diff": abs(avg_label(upper_right) - avg_label(lower_right)),
        "ur_vertical_strand_score": avg_vertical(upper_right, "vertical_strand_score"),
        "lr_vertical_strand_score": avg_vertical(lower_right, "vertical_strand_score"),
        "vertical_strand_diff": abs(
            avg_vertical(upper_right, "vertical_strand_score")
            - avg_vertical(lower_right, "vertical_strand_score")
        ),
    }


def make_contact_sheet(image_paths: list[Path], out_path: Path, cols: int) -> None:
    if not image_paths:
        return
    thumbs = []
    for path in image_paths:
        image = Image.open(path).convert("RGB")
        image.thumbnail((360, 340))
        thumbs.append((path, image.copy()))
    cell_w = max(image.width for _, image in thumbs)
    cell_h = max(image.height for _, image in thumbs) + 34
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "black")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    for idx, (path, image) in enumerate(thumbs):
        row = idx // cols
        col = idx % cols
        x = col * cell_w
        y = row * cell_h
        sheet.paste(image, (x, y))
        draw.text((x + 6, y + image.height + 6), path.stem, fill="white", font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def main() -> None:
    args = parse_args()
    started = time.monotonic()
    video = args.video.expanduser()
    out_root = args.out_root.expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file
    target_frames = parse_int_list(args.target_frames)
    settings = make_settings(args.max_settings)
    max_window = max(setting.window_frames for setting in settings)
    manifest_path = out_root / "exp6_frame_sweep_manifest.csv"
    manifest_rows = []

    for target_frame in target_frames:
        if safeword_triggered(safeword_file):
            print(f"safeword detected before target frame {target_frame}; stopping", flush=True)
            break
        print(f"reading max-window frames for target {target_frame}", flush=True)
        start_frame = target_frame - max_window + 1
        frames, fps = read_frames(video, start_frame, max_window, args.flow_scale_width)
        flows = compute_flows(frames)
        target_image, fps = read_target_frame(video, target_frame, args.flow_scale_width)
        frame_dir = out_root / f"frame_{target_frame}"
        images_for_sheet = []
        for setting in settings:
            if safeword_triggered(safeword_file):
                print(f"safeword detected before setting {setting.setting_id}; stopping", flush=True)
                break
            out_path = frame_dir / f"setting_{setting.setting_id:04d}.png"
            if out_path.exists() and not args.overwrite:
                status = "skipped_existing"
            elif args.dry_run:
                status = "dry_run"
            else:
                features, vertical = extract_one_window_features(flows, target_frame, max_window, setting)
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
                    out_path,
                    features,
                    vertical,
                    labels,
                    probs,
                    setting,
                    target_frame,
                    fps,
                    args.top_mask_height,
                )
                status = "done"
                scores = summarize_scores(features, vertical, labels, probs)
                (frame_dir / f"setting_{setting.setting_id:04d}.json").write_text(
                    json.dumps({"setting": asdict(setting), "scores": scores}, indent=2) + "\n"
                )
            images_for_sheet.append(out_path)
            manifest_rows.append(
                {
                    "target_frame": target_frame,
                    "image": str(out_path),
                    "status": status,
                    **asdict(setting),
                }
            )
            if setting.setting_id % 25 == 0:
                print(f"  target {target_frame}: rendered {setting.setting_id}/{len(settings)}", flush=True)
                write_manifest(manifest_path, manifest_rows)
        if not args.dry_run:
            make_contact_sheet(images_for_sheet[:100], frame_dir / "contact_sheet_first100.jpg", args.contact_sheet_cols)
        write_manifest(manifest_path, manifest_rows)

    elapsed = time.monotonic() - started
    print(f"wrote manifest: {manifest_path}")
    print(f"elapsed wall time: {elapsed:.2f}s")


def write_manifest(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
