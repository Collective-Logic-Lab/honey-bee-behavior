#!/usr/bin/env python3
"""Create exploratory motion-regime annotations from local optical-flow features."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class CellFeature:
    window_id: int
    frame_start: int
    frame_stop: int
    frame_mid: int
    cell_row: int
    cell_col: int
    x_center: float
    y_center: float
    mean_vx: float
    mean_vy: float
    mean_speed: float
    mean_speed_sq: float
    std_speed: float
    active_fraction: float
    alignment: float
    direction_concentration: float
    angular_sweep_std: float
    angular_sweep_abs_mean: float
    divergence: float
    curl: float
    neighbor_speed_contrast: float = 0.0
    neighbor_alignment_contrast: float = 0.0
    neighbor_angular_sweep_abs_diff: float = 0.0
    neighbor_direction_concentration_diff: float = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute local boids-like optical-flow features over frame windows, cluster the "
            "cell-window features, and render a colored motion-regime overlay video."
        )
    )
    parser.add_argument("video", type=Path, help="Source MP4.")
    parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    parser.add_argument("--start-frame", type=int, default=0, help="First frame to process.")
    parser.add_argument(
        "--duration-frames",
        type=int,
        default=3000,
        help="Number of frames to process from --start-frame.",
    )
    parser.add_argument(
        "--window-frames",
        type=int,
        default=125,
        help="History window length. At 25 fps, 125 frames is 5 seconds.",
    )
    parser.add_argument(
        "--stride-frames",
        type=int,
        default=25,
        help="Window stride. At 25 fps, 25 frames is 1 second.",
    )
    parser.add_argument("--grid-rows", type=int, default=16)
    parser.add_argument("--grid-cols", type=int, default=16)
    parser.add_argument("--clusters", type=int, default=6)
    parser.add_argument(
        "--method",
        choices=("gmm", "kmeans"),
        default="gmm",
        help="Clustering method for cell-window features.",
    )
    parser.add_argument(
        "--gmm-covariance-type",
        choices=("full", "tied", "diag", "spherical"),
        default="diag",
        help="GMM covariance type. 'diag' is more robust for long chunked runs than 'full'.",
    )
    parser.add_argument(
        "--gmm-reg-covar",
        type=float,
        default=1e-4,
        help="Non-negative regularization added to GMM covariance diagonals.",
    )
    parser.add_argument(
        "--pca-components",
        type=int,
        default=6,
        help="PCA components before clustering. Use 0 to disable PCA.",
    )
    parser.add_argument(
        "--flow-scale-width",
        type=int,
        default=412,
        help="Downsample width for optical flow computation.",
    )
    parser.add_argument(
        "--activity-threshold",
        type=float,
        default=0.30,
        help="Flow speed threshold for active pixels in downsampled pixels/frame.",
    )
    parser.add_argument(
        "--min-active-fraction",
        type=float,
        default=0.005,
        help="Cells below this active fraction are drawn with low opacity.",
    )
    parser.add_argument("--random-state", type=int, default=0)
    parser.add_argument(
        "--angular-feature-weight",
        type=float,
        default=1.0,
        help=(
            "Multiplier applied after scaling to angular/group-motion features "
            "(direction concentration, angular sweep, curl, and angular neighbor contrasts)."
        ),
    )
    parser.add_argument(
        "--neighbor-feature-weight",
        type=float,
        default=1.0,
        help="Multiplier applied after scaling to neighbor-contrast features.",
    )
    parser.add_argument(
        "--velocity-transform",
        choices=("raw", "log1p", "sqrt", "asinh"),
        default="raw",
        help=(
            "Transform velocity/speed feature columns before scaling. Use log1p or asinh "
            "to reduce the influence of a few very fast bees in otherwise empty regions."
        ),
    )
    parser.add_argument(
        "--feature-set",
        choices=("full", "velocity", "beginner"),
        default="full",
        help=(
            "Feature preset used for clustering. 'velocity' uses only mean_speed. "
            "'beginner' uses mean_speed, active_fraction, alignment, and direction_concentration. "
            "The output CSV still includes all computed raw features."
        ),
    )
    return parser.parse_args()


def read_frames(video: Path, start_frame: int, duration_frames: int, width: int) -> tuple[list[np.ndarray], float]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    height = max(1, round(width * source_height / source_width))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    frames: list[np.ndarray] = []
    for _ in range(duration_frames):
        ok, frame = cap.read()
        if not ok:
            break
        resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        frames.append(gray)
    cap.release()
    if len(frames) < 2:
        raise RuntimeError("Need at least two frames for optical flow.")
    return frames, fps


def compute_flows(frames: list[np.ndarray]) -> list[np.ndarray]:
    flows = []
    for i in range(len(frames) - 1):
        flow = cv2.calcOpticalFlowFarneback(
            frames[i],
            frames[i + 1],
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )
        flows.append(flow.astype(np.float32))
        if i and i % 500 == 0:
            print(f"computed optical flow pairs: {i:,}", flush=True)
    return flows


def cell_slices(height: int, width: int, rows: int, cols: int):
    y_edges = np.linspace(0, height, rows + 1, dtype=int)
    x_edges = np.linspace(0, width, cols + 1, dtype=int)
    for row in range(rows):
        for col in range(cols):
            yield row, col, slice(y_edges[row], y_edges[row + 1]), slice(x_edges[col], x_edges[col + 1])


def summarize_cell(
    window_id: int,
    frame_start: int,
    frame_stop: int,
    cell_row: int,
    cell_col: int,
    y_slice: slice,
    x_slice: slice,
    flow_stack: np.ndarray,
    activity_threshold: float,
) -> CellFeature:
    cell = flow_stack[:, y_slice, x_slice, :]
    vx = cell[..., 0]
    vy = cell[..., 1]
    speed = np.sqrt(vx * vx + vy * vy)
    active = speed > activity_threshold
    active_fraction = float(np.mean(active))

    if np.any(active):
        mean_vx = float(np.mean(vx[active]))
        mean_vy = float(np.mean(vy[active]))
        active_speed = speed[active]
    else:
        mean_vx = float(np.mean(vx))
        mean_vy = float(np.mean(vy))
        active_speed = speed.reshape(-1)

    safe_speed = np.where(speed > 1e-6, speed, 1.0)
    unit_x = vx / safe_speed
    unit_y = vy / safe_speed
    alignment = float(np.sqrt(np.mean(unit_x[active]) ** 2 + np.mean(unit_y[active]) ** 2)) if np.any(active) else 0.0

    frame_mean_vx = np.mean(vx, axis=(1, 2))
    frame_mean_vy = np.mean(vy, axis=(1, 2))
    frame_angles = np.arctan2(frame_mean_vy, frame_mean_vx)
    frame_speeds = np.sqrt(frame_mean_vx * frame_mean_vx + frame_mean_vy * frame_mean_vy)
    moving = frame_speeds > activity_threshold
    if np.any(moving):
        direction_concentration = float(
            np.sqrt(np.mean(np.cos(frame_angles[moving])) ** 2 + np.mean(np.sin(frame_angles[moving])) ** 2)
        )
    else:
        direction_concentration = 0.0
    if np.count_nonzero(moving) > 1:
        active_angles = np.unwrap(frame_angles[moving])
        angular_sweeps = np.diff(active_angles)
        angular_sweep_std = float(np.std(angular_sweeps))
        angular_sweep_abs_mean = float(np.mean(np.abs(angular_sweeps)))
    else:
        angular_sweep_std = 0.0
        angular_sweep_abs_mean = 0.0

    mean_flow = np.mean(cell, axis=0)
    d_vx_dx = np.gradient(mean_flow[..., 0], axis=1)
    d_vy_dy = np.gradient(mean_flow[..., 1], axis=0)
    d_vy_dx = np.gradient(mean_flow[..., 1], axis=1)
    d_vx_dy = np.gradient(mean_flow[..., 0], axis=0)
    divergence = float(np.mean(d_vx_dx + d_vy_dy))
    curl = float(np.mean(d_vy_dx - d_vx_dy))

    y_center = (y_slice.start + y_slice.stop - 1) / 2
    x_center = (x_slice.start + x_slice.stop - 1) / 2
    return CellFeature(
        window_id=window_id,
        frame_start=frame_start,
        frame_stop=frame_stop,
        frame_mid=(frame_start + frame_stop) // 2,
        cell_row=cell_row,
        cell_col=cell_col,
        x_center=x_center,
        y_center=y_center,
        mean_vx=mean_vx,
        mean_vy=mean_vy,
        mean_speed=float(np.mean(active_speed)),
        mean_speed_sq=float(np.mean(active_speed * active_speed)),
        std_speed=float(np.std(active_speed)),
        active_fraction=active_fraction,
        alignment=alignment,
        direction_concentration=direction_concentration,
        angular_sweep_std=angular_sweep_std,
        angular_sweep_abs_mean=angular_sweep_abs_mean,
        divergence=divergence,
        curl=curl,
    )


def add_neighbor_contrasts(features: list[CellFeature], rows: int, cols: int) -> list[CellFeature]:
    by_window: dict[int, dict[tuple[int, int], CellFeature]] = {}
    for feature in features:
        by_window.setdefault(feature.window_id, {})[(feature.cell_row, feature.cell_col)] = feature

    updated = []
    for feature in features:
        neighbors = []
        window = by_window[feature.window_id]
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                key = (feature.cell_row + dr, feature.cell_col + dc)
                if 0 <= key[0] < rows and 0 <= key[1] < cols and key in window:
                    neighbors.append(window[key])
        if neighbors:
            speed_contrast = feature.mean_speed - float(np.mean([n.mean_speed for n in neighbors]))
            alignment_contrast = feature.alignment - float(np.mean([n.alignment for n in neighbors]))
            angular_sweep_diff = float(
                np.mean([abs(feature.angular_sweep_abs_mean - n.angular_sweep_abs_mean) for n in neighbors])
            )
            direction_concentration_diff = feature.direction_concentration - float(
                np.mean([n.direction_concentration for n in neighbors])
            )
        else:
            speed_contrast = 0.0
            alignment_contrast = 0.0
            angular_sweep_diff = 0.0
            direction_concentration_diff = 0.0
        updated.append(
            CellFeature(
                **{
                    **feature.__dict__,
                    "neighbor_speed_contrast": speed_contrast,
                    "neighbor_alignment_contrast": alignment_contrast,
                    "neighbor_angular_sweep_abs_diff": angular_sweep_diff,
                    "neighbor_direction_concentration_diff": direction_concentration_diff,
                }
            )
        )
    return updated


def extract_features(
    flows: list[np.ndarray],
    start_frame: int,
    window_frames: int,
    stride_frames: int,
    grid_rows: int,
    grid_cols: int,
    activity_threshold: float,
) -> list[CellFeature]:
    # A 125-frame frame window contains 124 frame-to-frame flow fields.
    flow_window = max(1, window_frames - 1)
    height, width = flows[0].shape[:2]
    features = []
    window_id = 0
    for local_start in range(0, len(flows) - flow_window + 1, stride_frames):
        local_stop = local_start + flow_window
        flow_stack = np.stack(flows[local_start:local_stop])
        frame_start = start_frame + local_start
        frame_stop = start_frame + local_start + window_frames - 1
        for row, col, y_slice, x_slice in cell_slices(height, width, grid_rows, grid_cols):
            features.append(
                summarize_cell(
                    window_id,
                    frame_start,
                    frame_stop,
                    row,
                    col,
                    y_slice,
                    x_slice,
                    flow_stack,
                    activity_threshold,
                )
            )
        if window_id and window_id % 25 == 0:
            print(f"computed feature windows: {window_id:,}", flush=True)
        window_id += 1
    return add_neighbor_contrasts(features, grid_rows, grid_cols)


FEATURE_NAMES = [
    "x_center",
    "y_center",
    "mean_vx",
    "mean_vy",
    "mean_speed",
    "mean_speed_sq",
    "std_speed",
    "active_fraction",
    "alignment",
    "direction_concentration",
    "angular_sweep_std",
    "angular_sweep_abs_mean",
    "divergence",
    "curl",
    "neighbor_speed_contrast",
    "neighbor_alignment_contrast",
    "neighbor_angular_sweep_abs_diff",
    "neighbor_direction_concentration_diff",
]

FEATURE_SETS = {
    "full": FEATURE_NAMES,
    "velocity": ["mean_speed"],
    "beginner": ["mean_speed", "active_fraction", "alignment", "direction_concentration"],
}


def feature_matrix(
    features: list[CellFeature],
    velocity_transform: str = "raw",
    feature_set: str = "full",
) -> np.ndarray:
    x = np.array(
        [
            [
                f.x_center,
                f.y_center,
                f.mean_vx,
                f.mean_vy,
                f.mean_speed,
                f.mean_speed_sq,
                f.std_speed,
                f.active_fraction,
                f.alignment,
                f.direction_concentration,
                f.angular_sweep_std,
                f.angular_sweep_abs_mean,
                f.divergence,
                f.curl,
                f.neighbor_speed_contrast,
                f.neighbor_alignment_contrast,
                f.neighbor_angular_sweep_abs_diff,
                f.neighbor_direction_concentration_diff,
            ]
            for f in features
        ],
        dtype=np.float64,
    )
    apply_velocity_transform(x, velocity_transform)
    selected_indices = [FEATURE_NAMES.index(name) for name in FEATURE_SETS[feature_set]]
    return x[:, selected_indices]


SIGNED_VELOCITY_FEATURES = {
    "mean_vx",
    "mean_vy",
    "neighbor_speed_contrast",
}

NONNEGATIVE_VELOCITY_FEATURES = {
    "mean_speed",
    "mean_speed_sq",
    "std_speed",
}


ANGULAR_FEATURES = {
    "direction_concentration",
    "angular_sweep_std",
    "angular_sweep_abs_mean",
    "curl",
    "neighbor_angular_sweep_abs_diff",
    "neighbor_direction_concentration_diff",
}


NEIGHBOR_FEATURES = {
    "neighbor_speed_contrast",
    "neighbor_alignment_contrast",
    "neighbor_angular_sweep_abs_diff",
    "neighbor_direction_concentration_diff",
}


def transform_nonnegative(values: np.ndarray, transform: str) -> np.ndarray:
    values = np.clip(values, 0.0, None)
    if transform == "raw":
        return values
    if transform == "log1p":
        return np.log1p(values)
    if transform == "sqrt":
        return np.sqrt(values)
    if transform == "asinh":
        return np.arcsinh(values)
    raise ValueError(transform)


def transform_signed(values: np.ndarray, transform: str) -> np.ndarray:
    if transform == "raw":
        return values
    magnitude = np.abs(values)
    if transform == "log1p":
        return np.sign(values) * np.log1p(magnitude)
    if transform == "sqrt":
        return np.sign(values) * np.sqrt(magnitude)
    if transform == "asinh":
        return np.arcsinh(values)
    raise ValueError(transform)


def apply_velocity_transform(x: np.ndarray, transform: str) -> None:
    for idx, name in enumerate(FEATURE_NAMES):
        if name in SIGNED_VELOCITY_FEATURES:
            x[:, idx] = transform_signed(x[:, idx], transform)
        elif name in NONNEGATIVE_VELOCITY_FEATURES:
            x[:, idx] = transform_nonnegative(x[:, idx], transform)


def apply_feature_weights(
    x: np.ndarray,
    feature_names: list[str],
    angular_feature_weight: float,
    neighbor_feature_weight: float,
) -> None:
    angular_features = {
        "direction_concentration",
        "angular_sweep_std",
        "angular_sweep_abs_mean",
        "curl",
        "neighbor_angular_sweep_abs_diff",
        "neighbor_direction_concentration_diff",
    }
    neighbor_features = {
        "neighbor_speed_contrast",
        "neighbor_alignment_contrast",
        "neighbor_angular_sweep_abs_diff",
        "neighbor_direction_concentration_diff",
    }
    for idx, name in enumerate(feature_names):
        if name in angular_features:
            x[:, idx] *= angular_feature_weight
        if name in neighbor_features:
            x[:, idx] *= neighbor_feature_weight


def fit_clusters(
    x: np.ndarray,
    method: str,
    clusters: int,
    pca_components: int,
    random_state: int,
    gmm_covariance_type: str,
    gmm_reg_covar: float,
    angular_feature_weight: float,
    neighbor_feature_weight: float,
    feature_names: list[str],
) -> tuple[np.ndarray, np.ndarray, object]:
    scaler = StandardScaler()
    z = scaler.fit_transform(x)
    apply_feature_weights(z, feature_names, angular_feature_weight, neighbor_feature_weight)

    pca = None
    if pca_components > 0:
        pca = PCA(n_components=min(pca_components, z.shape[1]), random_state=random_state)
        z = pca.fit_transform(z)

    if method == "gmm":
        attempted = []
        model = None
        for covariance_type, reg_covar in [
            (gmm_covariance_type, gmm_reg_covar),
            ("diag", max(gmm_reg_covar, 1e-3)),
            ("spherical", max(gmm_reg_covar, 1e-3)),
        ]:
            attempted.append({"covariance_type": covariance_type, "reg_covar": reg_covar})
            candidate = GaussianMixture(
                n_components=clusters,
                covariance_type=covariance_type,
                random_state=random_state,
                reg_covar=reg_covar,
            )
            try:
                candidate.fit(z)
            except ValueError as exc:
                print(
                    f"GMM fit failed for covariance_type={covariance_type} "
                    f"reg_covar={reg_covar}: {exc}",
                    flush=True,
                )
                continue
            model = candidate
            break
        if model is None:
            raise RuntimeError(f"All GMM fit attempts failed: {attempted}")
        probs = model.predict_proba(z)
        labels = np.argmax(probs, axis=1)
    else:
        model = KMeans(n_clusters=clusters, n_init=20, random_state=random_state)
        labels = model.fit_predict(z)
        probs = np.zeros((len(labels), clusters), dtype=np.float32)
        probs[np.arange(len(labels)), labels] = 1.0
    return labels, probs, {"scaler": scaler, "pca": pca, "model": model}


def write_features(path: Path, features: list[CellFeature], labels: np.ndarray, probs: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base_fields = list(CellFeature.__dataclass_fields__.keys())
    prob_fields = [f"p_cluster_{i}" for i in range(probs.shape[1])]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*base_fields, "cluster", "cluster_probability", *prob_fields])
        writer.writeheader()
        for feature, label, prob_row in zip(features, labels, probs, strict=True):
            row = feature.__dict__.copy()
            row["cluster"] = int(label)
            row["cluster_probability"] = float(np.max(prob_row))
            for i, prob in enumerate(prob_row):
                row[f"p_cluster_{i}"] = float(prob)
            writer.writerow(row)


def palette(n: int) -> list[tuple[int, int, int]]:
    colors = []
    for i in range(n):
        hue = int(180 * i / max(1, n))
        hsv = np.uint8([[[hue, 220, 255]]])
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
        colors.append((int(bgr[0]), int(bgr[1]), int(bgr[2])))
    return colors


def draw_overlay(
    video: Path,
    out_path: Path,
    features: list[CellFeature],
    labels: np.ndarray,
    probs: np.ndarray,
    start_frame: int,
    fps: float,
    scale_width: int,
    grid_rows: int,
    grid_cols: int,
    min_active_fraction: float,
) -> None:
    by_window: dict[int, list[tuple[CellFeature, int, float]]] = {}
    for feature, label, prob_row in zip(features, labels, probs, strict=True):
        by_window.setdefault(feature.window_id, []).append((feature, int(label), float(np.max(prob_row))))

    cap = cv2.VideoCapture(str(video))
    source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale_height = max(1, round(scale_width * source_height / source_width))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(out_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (scale_width, scale_height),
    )
    colors = palette(probs.shape[1])

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    for window_id in sorted(by_window):
        frame_idx = by_window[window_id][0][0].frame_mid
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.resize(frame, (scale_width, scale_height), interpolation=cv2.INTER_AREA)
        overlay = frame.copy()
        for feature, label, probability in by_window[window_id]:
            color = colors[label]
            cell_w = scale_width / grid_cols
            cell_h = scale_height / grid_rows
            x0 = int(feature.cell_col * cell_w)
            y0 = int(feature.cell_row * cell_h)
            x1 = int((feature.cell_col + 1) * cell_w)
            y1 = int((feature.cell_row + 1) * cell_h)
            alpha = 0.08 + 0.30 * min(1.0, max(feature.active_fraction, min_active_fraction) * 10)
            cv2.rectangle(overlay, (x0, y0), (x1, y1), color, thickness=-1)
            cx = int(feature.x_center)
            cy = int(feature.y_center)
            vx = feature.mean_vx * 10
            vy = feature.mean_vy * 10
            end = (int(cx + vx), int(cy + vy))
            if feature.active_fraction >= min_active_fraction:
                cv2.arrowedLine(frame, (cx, cy), end, color, 2, tipLength=0.35)
        frame = cv2.addWeighted(overlay, 0.28, frame, 0.72, 0)
        text = f"window {window_id} frame {frame_idx} t={frame_idx / fps:.1f}s"
        cv2.putText(frame, text, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()
    cap.release()


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    frames, fps = read_frames(video, args.start_frame, args.duration_frames, args.flow_scale_width)
    print(f"read frames: {len(frames):,} at fps={fps:.3f}", flush=True)
    flows = compute_flows(frames)
    print(f"computed flows: {len(flows):,}", flush=True)
    features = extract_features(
        flows,
        args.start_frame,
        args.window_frames,
        args.stride_frames,
        args.grid_rows,
        args.grid_cols,
        args.activity_threshold,
    )
    print(f"feature rows: {len(features):,}", flush=True)
    feature_names = FEATURE_SETS[args.feature_set]
    x = feature_matrix(features, args.velocity_transform, args.feature_set)
    labels, probs, _ = fit_clusters(
        x,
        args.method,
        args.clusters,
        args.pca_components,
        args.random_state,
        args.gmm_covariance_type,
        args.gmm_reg_covar,
        args.angular_feature_weight,
        args.neighbor_feature_weight,
        feature_names,
    )
    write_features(out_dir / "motion_regime_features.csv", features, labels, probs)
    draw_overlay(
        video,
        out_dir / "motion_regime_overlay.mp4",
        features,
        labels,
        probs,
        args.start_frame,
        fps,
        args.flow_scale_width,
        args.grid_rows,
        args.grid_cols,
        args.min_active_fraction,
    )
    metadata = {
        "video": str(video),
        "start_frame": args.start_frame,
        "duration_frames": args.duration_frames,
        "fps": fps,
        "window_frames": args.window_frames,
        "stride_frames": args.stride_frames,
        "grid_rows": args.grid_rows,
        "grid_cols": args.grid_cols,
        "clusters": args.clusters,
        "method": args.method,
        "gmm_covariance_type": args.gmm_covariance_type,
        "gmm_reg_covar": args.gmm_reg_covar,
        "pca_components": args.pca_components,
        "activity_threshold": args.activity_threshold,
        "flow_scale_width": args.flow_scale_width,
        "angular_feature_weight": args.angular_feature_weight,
        "neighbor_feature_weight": args.neighbor_feature_weight,
        "velocity_transform": args.velocity_transform,
        "feature_set": args.feature_set,
        "feature_names": feature_names,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"wrote features: {out_dir / 'motion_regime_features.csv'}")
    print(f"wrote overlay: {out_dir / 'motion_regime_overlay.mp4'}")


if __name__ == "__main__":
    main()
