#!/usr/bin/env python3
"""Score upper-right/lower-right clustering separation for sampler runs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure clustering separation between upper-right and lower-right "
            "quadrants for sample runs at a target frame."
        )
    )
    parser.add_argument("--root", type=Path, default=Path("data/experiments/exp3_overnight"))
    parser.add_argument("--target-frame", type=int, default=87950)
    parser.add_argument(
        "--exclude-top-pixels",
        type=float,
        default=72.0,
        help="Exclude feature cells whose y_center falls inside this top caption band.",
    )
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def find_feature_file(run_dir: Path, target_frame: int) -> Path | None:
    candidates = sorted(run_dir.glob("sample_*_frame_*/motion_regime_features.csv"))
    containing = []
    nearest = []
    for path in candidates:
        try:
            start = int(path.parent.name.rsplit("_", 1)[1])
        except ValueError:
            continue
        metadata = load_json(path.parent / "metadata.json")
        duration = int(metadata.get("duration_frames") or metadata.get("sample_frames") or 250)
        if start <= target_frame < start + duration:
            containing.append(path)
        nearest.append((abs(target_frame - start), path))
    if containing:
        return containing[0]
    if nearest:
        return sorted(nearest)[0][1]
    return None


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["_frame_start"] = int(float(row["frame_start"]))
        row["_frame_stop"] = int(float(row["frame_stop"]))
        row["_frame_mid"] = int(float(row["frame_mid"]))
    return rows


def selected_rows(rows: list[dict], target_frame: int) -> tuple[list[dict], list[dict], int | None]:
    containing = [row for row in rows if row["_frame_start"] <= target_frame <= row["_frame_stop"]]
    if containing:
        nearest_mid = min({row["_frame_mid"] for row in containing}, key=lambda value: abs(value - target_frame))
    elif rows:
        nearest_mid = min({row["_frame_mid"] for row in rows}, key=lambda value: abs(value - target_frame))
    else:
        nearest_mid = None
    nearest = [row for row in rows if row["_frame_mid"] == nearest_mid] if nearest_mid is not None else []
    return containing, nearest, nearest_mid


def score(rows: list[dict], exclude_top_pixels: float) -> dict | None:
    if not rows:
        return None
    rows = [row for row in rows if float(row["y_center"]) >= exclude_top_pixels]
    if not rows:
        return None
    max_col = max(int(row["cell_col"]) for row in rows)
    max_row = max(int(row["cell_row"]) for row in rows)
    col_mid = (max_col + 1) / 2
    row_mid = (max_row + 1) / 2
    upper_right = [
        row for row in rows if int(row["cell_col"]) >= col_mid and int(row["cell_row"]) < row_mid
    ]
    lower_right = [
        row for row in rows if int(row["cell_col"]) >= col_mid and int(row["cell_row"]) >= row_mid
    ]

    def avg_cluster(region: list[dict]) -> float:
        return sum(int(row["cluster"]) for row in region) / len(region) if region else math.nan

    def cluster_distribution(region: list[dict]) -> dict[int, float]:
        counts = Counter(int(row["cluster"]) for row in region)
        total = sum(counts.values()) or 1
        return {label: count / total for label, count in counts.items()}

    upper_dist = cluster_distribution(upper_right)
    lower_dist = cluster_distribution(lower_right)
    labels = sorted(set(upper_dist) | set(lower_dist))
    cluster_tv = 0.5 * sum(abs(upper_dist.get(label, 0.0) - lower_dist.get(label, 0.0)) for label in labels)

    prob_cols = [key for key in rows[0] if key.startswith("p_cluster_")]

    def prob_profile(region: list[dict]) -> list[float]:
        if not region:
            return []
        return [sum(float(row[col]) for row in region) / len(region) for col in prob_cols]

    upper_prob = prob_profile(upper_right)
    lower_prob = prob_profile(lower_right)
    prob_tv = (
        0.5 * sum(abs(upper - lower) for upper, lower in zip(upper_prob, lower_prob))
        if upper_prob and lower_prob
        else math.nan
    )
    upper_avg = avg_cluster(upper_right)
    lower_avg = avg_cluster(lower_right)
    return {
        "ur_count": len(upper_right),
        "lr_count": len(lower_right),
        "ur_avg_cluster": upper_avg,
        "lr_avg_cluster": lower_avg,
        "avg_cluster_diff": abs(upper_avg - lower_avg),
        "cluster_tv_distance": cluster_tv,
        "probability_tv_distance": prob_tv,
        "ur_mode_cluster": max(upper_dist, key=upper_dist.get) if upper_dist else "",
        "lr_mode_cluster": max(lower_dist, key=lower_dist.get) if lower_dist else "",
    }


def main() -> None:
    args = parse_args()
    root = args.root.expanduser()
    out = args.out.expanduser() if args.out else root / f"frame{args.target_frame}_quadrant_metrics.csv"
    rows_out = []
    for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        feature_file = find_feature_file(run_dir, args.target_frame)
        if feature_file is None:
            continue
        rows = load_rows(feature_file)
        containing, nearest, nearest_mid = selected_rows(rows, args.target_frame)
        metadata = load_json(run_dir / "metadata.json")
        for kind, selected in (("containing", containing), ("nearest_mid", nearest)):
            metric = score(selected, args.exclude_top_pixels)
            if metric is None:
                continue
            rows_out.append(
                {
                    "run": run_dir.name,
                    "metric_kind": kind,
                    "target_frame": args.target_frame,
                    "exclude_top_pixels": args.exclude_top_pixels,
                    "nearest_frame_mid": nearest_mid,
                    "nearest_mid_abs_diff": abs(nearest_mid - args.target_frame)
                    if nearest_mid is not None
                    else "",
                    "selected_window_count": len({row["_frame_mid"] for row in selected}),
                    "grid_rows": metadata.get("grid_rows", ""),
                    "grid_cols": metadata.get("grid_cols", ""),
                    "clusters": metadata.get("clusters", ""),
                    "pca_components": metadata.get("pca_components", ""),
                    "feature_set": metadata.get("feature_set", ""),
                    "velocity_transform": metadata.get("velocity_transform", ""),
                    "activity_threshold": metadata.get("activity_threshold", ""),
                    "angular_feature_weight": metadata.get("angular_feature_weight", ""),
                    "neighbor_feature_weight": metadata.get("neighbor_feature_weight", ""),
                    "feature_csv": str(feature_file),
                    **metric,
                }
            )

    fields = [
        "run",
        "metric_kind",
        "target_frame",
        "exclude_top_pixels",
        "nearest_frame_mid",
        "nearest_mid_abs_diff",
        "selected_window_count",
        "avg_cluster_diff",
        "ur_avg_cluster",
        "lr_avg_cluster",
        "cluster_tv_distance",
        "probability_tv_distance",
        "ur_mode_cluster",
        "lr_mode_cluster",
        "ur_count",
        "lr_count",
        "grid_rows",
        "grid_cols",
        "clusters",
        "pca_components",
        "feature_set",
        "velocity_transform",
        "activity_threshold",
        "angular_feature_weight",
        "neighbor_feature_weight",
        "feature_csv",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"wrote metrics: {out}")

    ranked = [row for row in rows_out if row["metric_kind"] == "nearest_mid"]
    for row in sorted(ranked, key=lambda item: float(item["avg_cluster_diff"]), reverse=True)[:10]:
        print(
            f"{row['run']:22s} avgdiff={float(row['avg_cluster_diff']):.3f} "
            f"probTV={float(row['probability_tv_distance']):.3f} "
            f"clusterTV={float(row['cluster_tv_distance']):.3f}"
        )


if __name__ == "__main__":
    main()
