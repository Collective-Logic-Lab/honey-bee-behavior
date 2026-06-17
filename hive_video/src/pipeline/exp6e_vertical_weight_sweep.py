#!/usr/bin/env python3
"""Experiment 6e: repaired vertical-feature weight sweep for selected profiles."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

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
)
from annotate_motion_regimes import compute_flows  # noqa: E402
from exp6d_focused_sweep import (  # noqa: E402
    label_number,
    make_review_video,
    region_scores,
    write_manifest,
)


DEFAULT_VIDEO = Path(
    "data/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4"
)
DEFAULT_SOURCE_MANIFEST = Path(
    "data/no-sync/exp6d_focused_sweep_start03/exp6d_focused_sweep_manifest.csv"
)
DEFAULT_TARGET_FRAMES = "220000,225004,226604,227250,227840,231546,242063"
DEFAULT_BASE_SETTING_IDS = "486,325,289,1221,150,490,994,1281,1150,1337,926,70,857,1138"
DEFAULT_VERTICAL_VALUES = "0,0.125,0.25,0.5,0.75,1,1.5,2,3,4,6,8"


def parse_float_list(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Experiment 6e: selected Experiment 6d profiles crossed with a repaired "
            "vertical_feature_weight sweep. Vertical features are now weighted after "
            "standardization, so nonzero weight values are meaningful."
        )
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--out-root", type=Path, default=Path("data/no-sync/exp6e_vertical_weight_sweep_start03"))
    parser.add_argument("--target-frames", default=DEFAULT_TARGET_FRAMES)
    parser.add_argument("--base-setting-ids", default=DEFAULT_BASE_SETTING_IDS)
    parser.add_argument("--vertical-values", default=DEFAULT_VERTICAL_VALUES)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--seconds-per-image", type=float, default=0.5)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_base_settings(path: Path, base_setting_ids: list[int]) -> list[Setting]:
    by_id: dict[int, dict] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                setting_id = int(row["setting_id"])
            except (KeyError, ValueError):
                continue
            by_id.setdefault(setting_id, row)

    settings = []
    missing = []
    for setting_id in base_setting_ids:
        row = by_id.get(setting_id)
        if row is None:
            missing.append(setting_id)
            continue
        settings.append(
            Setting(
                setting_id=setting_id,
                window_frames=int(float(row["window_frames"])),
                grid_size=int(float(row["grid_size"])),
                clusters=int(float(row["clusters"])),
                feature_set=row["feature_set"],
                velocity_transform=row["velocity_transform"],
                activity_threshold=float(row["activity_threshold"]),
                angular_feature_weight=float(row["angular_feature_weight"]),
                neighbor_feature_weight=float(row["neighbor_feature_weight"]),
                vertical_feature_weight=0.0,
                method=row.get("method", "gmm") or "gmm",
                pca_components=int(float(row.get("pca_components", 0) or 0)),
            )
        )
    if missing:
        raise ValueError(f"Missing base setting ids in {path}: {missing}")
    return settings


def main() -> None:
    args = parse_args()
    started = time.monotonic()
    video = args.video.expanduser()
    source_manifest = args.source_manifest.expanduser()
    out_root = args.out_root.expanduser()
    frames_dir = out_root / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    target_frames = parse_int_list(args.target_frames)
    base_setting_ids = parse_int_list(args.base_setting_ids)
    vertical_values = parse_float_list(args.vertical_values)
    base_settings = read_base_settings(source_manifest, base_setting_ids)
    max_window = max(setting.window_frames for setting in base_settings)

    manifest_path = out_root / "exp6e_vertical_weight_sweep_manifest.csv"
    review_video = out_root / "exp6e_vertical_weight_sweep_review.mp4"
    ordered_images: list[Path] = []
    manifest_rows: list[dict] = []
    sequence = 0
    total = len(target_frames) * len(base_settings) * len(vertical_values)

    for target_frame in target_frames:
        if safeword_triggered(safeword_file):
            print(f"safeword detected before target frame {target_frame}; stopping", flush=True)
            break
        print(f"reading frames for target {target_frame}", flush=True)
        start_frame = target_frame - max_window + 1
        frames, fps = read_frames(video, start_frame, max_window, args.flow_scale_width)
        flows = compute_flows(frames)
        target_image, fps = read_target_frame(video, target_frame, args.flow_scale_width)

        for base_setting in base_settings:
            for vertical_value in vertical_values:
                sequence += 1
                if safeword_triggered(safeword_file):
                    print(f"safeword detected before sequence {sequence}; stopping", flush=True)
                    write_manifest(manifest_path, manifest_rows)
                    return

                setting = replace(base_setting, vertical_feature_weight=vertical_value)
                name = (
                    f"seq_{sequence:05d}_frame{target_frame}_"
                    f"base{base_setting.setting_id:04d}_"
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
                    scores = region_scores(features, vertical, labels, probs, args.top_mask_height)
                    json_path.write_text(
                        json.dumps(
                            {
                                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                                "target_frame": target_frame,
                                "sequence": sequence,
                                "base_setting_id": base_setting.setting_id,
                                "setting": asdict(setting),
                                "scores": scores,
                                "note": "vertical_feature_weight applied after StandardScaler",
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
                        "base_setting_id": base_setting.setting_id,
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
    print(f"base profiles: {len(base_settings)}", flush=True)
    print(f"vertical values: {len(vertical_values)}", flush=True)
    print(f"settings per frame: {len(base_settings) * len(vertical_values)}", flush=True)
    print(f"elapsed wall time: {elapsed:.2f}s", flush=True)


if __name__ == "__main__":
    main()
