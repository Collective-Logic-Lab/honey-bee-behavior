#!/usr/bin/env python3
"""Score one Experiment 6e profile over a long frame range."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import cv2

HIVE_VIDEO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = HIVE_VIDEO_ROOT / "src" / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from exp6_frame_sweep import (  # noqa: E402
    extract_one_window_features,
    feature_matrix_with_vertical,
    fit_clusters,
    parse_int_list,
    read_frames,
    safeword_triggered,
)
from annotate_motion_regimes import compute_flows  # noqa: E402
from exp6d_focused_sweep import region_scores, write_manifest  # noqa: E402
from exp6e_vertical_weight_sweep import (  # noqa: E402
    DEFAULT_BASE_SETTING_IDS,
    DEFAULT_SOURCE_MANIFEST,
    DEFAULT_VERTICAL_VALUES,
    DEFAULT_VIDEO,
    parse_float_list,
    read_base_settings,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute avg_cluster_diff and related separation scores for one selected "
            "Experiment 6e profile over a long frame interval. Intended for Slurm array use."
        )
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-setting-id", type=int, default=None)
    parser.add_argument("--vertical-weight", type=float, default=None)
    parser.add_argument(
        "--profile-index",
        type=int,
        default=None,
        help=(
            "Zero-based index into base_setting_ids x vertical_values. Useful for "
            "SLURM_ARRAY_TASK_ID."
        ),
    )
    parser.add_argument("--base-setting-ids", default=DEFAULT_BASE_SETTING_IDS)
    parser.add_argument("--vertical-values", default=DEFAULT_VERTICAL_VALUES)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument(
        "--end-frame",
        type=int,
        default=None,
        help="Exclusive end frame. Defaults to the video frame count.",
    )
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--chunk-target-frames", type=int, default=1000)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def video_frame_count(path: Path) -> int:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {path}")
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return count


def resolve_profile(args: argparse.Namespace):
    base_ids = parse_int_list(args.base_setting_ids)
    vertical_values = parse_float_list(args.vertical_values)

    if args.profile_index is not None:
        combinations = [(base_id, vertical) for base_id in base_ids for vertical in vertical_values]
        if not 0 <= args.profile_index < len(combinations):
            raise ValueError(
                f"profile-index {args.profile_index} outside 0..{len(combinations) - 1}"
            )
        base_setting_id, vertical_weight = combinations[args.profile_index]
    else:
        if args.base_setting_id is None or args.vertical_weight is None:
            raise ValueError("Provide either --profile-index or both --base-setting-id and --vertical-weight")
        base_setting_id = args.base_setting_id
        vertical_weight = args.vertical_weight

    base_setting = read_base_settings(args.source_manifest.expanduser(), [base_setting_id])[0]
    return replace(base_setting, vertical_feature_weight=vertical_weight), base_setting_id


def existing_frames(path: Path) -> set[int]:
    if not path.exists():
        return set()
    with path.open(newline="") as f:
        return {int(row["target_frame"]) for row in csv.DictReader(f) if row.get("target_frame")}


def append_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    started = time.monotonic()
    video = args.video.expanduser()
    out = args.out.expanduser()
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    frame_count = video_frame_count(video)
    end_frame = frame_count if args.end_frame is None else min(args.end_frame, frame_count)
    setting, base_setting_id = resolve_profile(args)
    first_target = max(args.start_frame, setting.window_frames - 1)
    target_frames = list(range(first_target, end_frame, args.stride))
    if not args.overwrite:
        done = existing_frames(out)
        target_frames = [frame for frame in target_frames if frame not in done]

    print(
        f"scoring base={base_setting_id} vertical={setting.vertical_feature_weight:g} "
        f"frames={len(target_frames):,} window={setting.window_frames}",
        flush=True,
    )

    for chunk_start in range(0, len(target_frames), args.chunk_target_frames):
        if safeword_triggered(safeword_file):
            print("safeword detected; stopping", flush=True)
            break

        chunk_targets = target_frames[chunk_start : chunk_start + args.chunk_target_frames]
        read_start = chunk_targets[0] - setting.window_frames + 1
        read_stop = chunk_targets[-1]
        frames, _ = read_frames(video, read_start, read_stop - read_start + 1, args.flow_scale_width)
        flows = compute_flows(frames)
        chunk_rows = []

        for target_frame in chunk_targets:
            local_start = target_frame - setting.window_frames + 1 - read_start
            local_stop = target_frame - read_start
            flow_slice = flows[local_start:local_stop]
            features, vertical = extract_one_window_features(
                flow_slice,
                target_frame,
                setting.window_frames,
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
            scores = region_scores(features, vertical, labels, probs, args.top_mask_height)
            chunk_rows.append(
                {
                    "target_frame": target_frame,
                    "target_time_seconds": target_frame / 25.0,
                    "base_setting_id": base_setting_id,
                    **asdict(setting),
                    **scores,
                }
            )

        append_rows(out, chunk_rows)
        print(
            f"wrote {chunk_start + len(chunk_targets):,}/{len(target_frames):,} rows to {out}",
            flush=True,
        )

    print(f"elapsed wall time: {time.monotonic() - started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
