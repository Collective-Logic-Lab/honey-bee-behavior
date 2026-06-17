#!/usr/bin/env python3
"""Summarize Experiment 6d frame scores into ranked parameter profiles."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


PARAM_COLUMNS = [
    "window_frames",
    "grid_size",
    "clusters",
    "feature_set",
    "velocity_transform",
    "activity_threshold",
    "angular_feature_weight",
    "neighbor_feature_weight",
    "vertical_feature_weight",
    "method",
    "pca_components",
]

SCORE_COLUMNS = [
    "avg_cluster_diff",
    "upper_lower_avg_cluster_diff",
    "upper_right_lower_right_cluster_tv",
    "upper_right_lower_right_probability_tv",
    "upper_lower_cluster_tv",
    "upper_lower_probability_tv",
    "vertical_strand_diff",
    "upper_lower_vertical_strand_diff",
]

PRIMARY_SCORE = "avg_cluster_diff"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Filter redundant Experiment 6d rows, rank settings within each frame, "
            "and summarize parameter profiles across frames."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/no-sync/exp6d_focused_sweep_start03/exp6d_focused_sweep_manifest.csv"),
    )
    parser.add_argument(
        "--out-summary",
        type=Path,
        default=Path("data/no-sync/exp6d_focused_sweep_start03/exp6d_profile_summary.csv"),
    )
    parser.add_argument(
        "--out-frame-scores",
        type=Path,
        default=Path("data/no-sync/exp6d_focused_sweep_start03/exp6d_filtered_frame_scores.csv"),
    )
    parser.add_argument(
        "--omit-vertical-weights",
        default="2.0,4.0",
        help="Comma-separated vertical_feature_weight values to omit.",
    )
    return parser.parse_args()


def as_float(value: str) -> float:
    if value == "" or value is None:
        return math.nan
    return float(value)


def normalize_number(value: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def profile_key(row: dict) -> tuple:
    return tuple(normalize_number(row[col]) for col in PARAM_COLUMNS)


def profile_label(row: dict) -> str:
    return (
        f"w{normalize_number(row['window_frames'])}_g{normalize_number(row['grid_size'])}_"
        f"k{normalize_number(row['clusters'])}_{row['feature_set']}_{row['velocity_transform']}_"
        f"a{normalize_number(row['activity_threshold'])}_"
        f"ang{normalize_number(row['angular_feature_weight'])}_"
        f"nbr{normalize_number(row['neighbor_feature_weight'])}_"
        f"vert{normalize_number(row['vertical_feature_weight'])}"
    )


def mean(values: list[float]) -> float:
    clean = [value for value in values if not math.isnan(value)]
    return statistics.mean(clean) if clean else math.nan


def stdev(values: list[float]) -> float:
    clean = [value for value in values if not math.isnan(value)]
    return statistics.stdev(clean) if len(clean) > 1 else 0.0 if clean else math.nan


def rank_desc(rows: list[dict], metric: str) -> None:
    ranked = sorted(
        rows,
        key=lambda row: (as_float(row.get(metric, "")) if row.get(metric, "") != "" else -math.inf),
        reverse=True,
    )
    previous_value = None
    previous_rank = 0
    for idx, row in enumerate(ranked, start=1):
        value = as_float(row.get(metric, ""))
        if previous_value is None or value != previous_value:
            previous_rank = idx
            previous_value = value
        row[f"{metric}_rank"] = previous_rank


def read_rows(path: Path, omit_vertical: set[float]) -> list[dict]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    filtered = []
    for row in rows:
        if row.get("status") not in {"done", "skipped_existing"}:
            continue
        vertical = as_float(row.get("vertical_feature_weight", ""))
        if vertical in omit_vertical:
            continue
        filtered.append(row)
    return filtered


def write_csv(path: Path, rows: list[dict]) -> None:
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


def main() -> None:
    args = parse_args()
    omit_vertical = {float(value.strip()) for value in args.omit_vertical_weights.split(",") if value.strip()}
    rows = read_rows(args.manifest.expanduser(), omit_vertical)
    by_frame: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_frame[row["target_frame"]].append(row)

    for frame_rows in by_frame.values():
        for metric in SCORE_COLUMNS:
            rank_desc(frame_rows, metric)

    frame_score_rows = []
    for target_frame in sorted(by_frame, key=lambda value: int(value)):
        for row in sorted(by_frame[target_frame], key=lambda item: int(item[f"{PRIMARY_SCORE}_rank"])):
            out = dict(row)
            out["profile_label"] = profile_label(row)
            frame_score_rows.append(out)
    write_csv(args.out_frame_scores.expanduser(), frame_score_rows)

    grouped: dict[tuple, list[dict]] = defaultdict(list)
    exemplar: dict[tuple, dict] = {}
    for row in frame_score_rows:
        key = profile_key(row)
        grouped[key].append(row)
        exemplar.setdefault(key, row)

    target_frames = sorted(by_frame, key=lambda value: int(value))
    summary_rows = []
    for key, group in grouped.items():
        first = exemplar[key]
        summary = {
            "profile_label": profile_label(first),
            "frames_observed": len(group),
            "setting_ids": ";".join(row["setting_id"] for row in sorted(group, key=lambda row: int(row["target_frame"]))),
            **{col: first[col] for col in PARAM_COLUMNS},
        }
        primary_scores = [as_float(row[PRIMARY_SCORE]) for row in group]
        primary_ranks = [float(row[f"{PRIMARY_SCORE}_rank"]) for row in group]
        summary["mean_rank"] = mean(primary_ranks)
        summary["std_rank"] = stdev(primary_ranks)
        summary["best_rank"] = min(primary_ranks)
        summary["worst_rank"] = max(primary_ranks)
        summary["mean_score"] = mean(primary_scores)
        summary["std_score"] = stdev(primary_scores)
        best_row = min(group, key=lambda row: int(row[f"{PRIMARY_SCORE}_rank"]))
        summary["best_frame"] = best_row["target_frame"]
        summary["best_frame_setting_id"] = best_row["setting_id"]
        summary["best_frame_rank"] = best_row[f"{PRIMARY_SCORE}_rank"]
        summary["best_frame_score"] = best_row[PRIMARY_SCORE]

        for metric in SCORE_COLUMNS:
            values = [as_float(row.get(metric, "")) for row in group]
            ranks = [float(row[f"{metric}_rank"]) for row in group if row.get(f"{metric}_rank", "") != ""]
            summary[f"{metric}_mean"] = mean(values)
            summary[f"{metric}_std"] = stdev(values)
            summary[f"{metric}_mean_rank"] = mean(ranks)
            summary[f"{metric}_std_rank"] = stdev(ranks)

        by_target = {row["target_frame"]: row for row in group}
        for target_frame in target_frames:
            row = by_target.get(target_frame)
            summary[f"frame_{target_frame}_setting_id"] = row.get("setting_id", "") if row else ""
            summary[f"frame_{target_frame}_score"] = row.get(PRIMARY_SCORE, "") if row else ""
            summary[f"frame_{target_frame}_rank"] = row.get(f"{PRIMARY_SCORE}_rank", "") if row else ""

        summary_rows.append(summary)

    summary_rows.sort(key=lambda row: (float(row["mean_rank"]), -float(row["mean_score"])))
    for idx, row in enumerate(summary_rows, start=1):
        row["overall_rank_by_mean_rank"] = idx
    summary_rows.sort(key=lambda row: (-float(row["mean_score"]), float(row["mean_rank"])))
    for idx, row in enumerate(summary_rows, start=1):
        row["overall_rank_by_mean_score"] = idx
    summary_rows.sort(key=lambda row: int(row["overall_rank_by_mean_rank"]))
    write_csv(args.out_summary.expanduser(), summary_rows)

    print(f"input rows: {sum(len(v) for v in by_frame.values())}")
    print(f"profile rows: {len(summary_rows)}")
    print(f"wrote frame scores: {args.out_frame_scores}")
    print(f"wrote profile summary: {args.out_summary}")


if __name__ == "__main__":
    main()
