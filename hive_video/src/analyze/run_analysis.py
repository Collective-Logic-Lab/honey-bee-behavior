#!/usr/bin/env python3
"""Run named motion-regime analysis presets."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from _version import ANALYSIS_VERSION


RUNNER_VERSION = "0.1.0"


PRESETS: dict[str, dict] = {
    "example_5s_beginner": {
        "description": "Small seed-video example using beginner motion features.",
        "runner": "direct",
        "params": {
            "start_frame": 0,
            "duration_frames": 125,
            "window_frames": 25,
            "stride_frames": 1,
            "grid_rows": 12,
            "grid_cols": 12,
            "clusters": 4,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 4,
            "flow_scale_width": 412,
            "feature_set": "beginner",
        },
    },
    "exp1_reseq_2min_v0p1": {
        "description": "Experiment 1 settings rerun on the resequenced video with top-caption masking.",
        "runner": "direct",
        "params": {
            "start_frame": 0,
            "duration_frames": 3000,
            "window_frames": 125,
            "stride_frames": 25,
            "grid_rows": 16,
            "grid_cols": 16,
            "clusters": 6,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 0,
            "flow_scale_width": 412,
            "feature_set": "exp1",
            "top_mask_height": 72,
        },
    },
    "exp2_reseq_focus_v0p1": {
        "description": "Experiment 2 focused angular/neighbor-synchrony run on the resequenced video.",
        "runner": "direct",
        "params": {
            "start_frame": 14500,
            "duration_frames": 3000,
            "window_frames": 125,
            "stride_frames": 25,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 8,
            "flow_scale_width": 412,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 1.0,
            "neighbor_feature_weight": 1.0,
            "top_mask_height": 72,
        },
    },
    "b1_velocity_only": {
        "description": "Beginner separability demo using only mean local speed.",
        "runner": "direct",
        "params": {
            "start_frame": 0,
            "duration_frames": 125,
            "window_frames": 25,
            "stride_frames": 1,
            "grid_rows": 12,
            "grid_cols": 12,
            "clusters": 4,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 0,
            "flow_scale_width": 412,
            "feature_set": "velocity",
            "velocity_transform": "raw",
        },
    },
    "b2_velocity_angle_crowding": {
        "description": "Beginner demo using speed, activity, alignment, and direction concentration.",
        "runner": "direct",
        "params": {
            "start_frame": 0,
            "duration_frames": 125,
            "window_frames": 25,
            "stride_frames": 1,
            "grid_rows": 12,
            "grid_cols": 12,
            "clusters": 5,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 0,
            "flow_scale_width": 412,
            "feature_set": "beginner",
            "velocity_transform": "raw",
        },
    },
    "full_group_motion_v1": {
        "description": "Full feature set with angular and neighbor features emphasized.",
        "runner": "direct",
        "params": {
            "start_frame": 0,
            "duration_frames": 125,
            "window_frames": 25,
            "stride_frames": 1,
            "grid_rows": 16,
            "grid_cols": 16,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 8,
            "flow_scale_width": 412,
            "feature_set": "full",
            "velocity_transform": "log1p",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
        },
    },
    "long_group_motion_v1": {
        "description": "Chunked long-run version of the full group-motion preset.",
        "runner": "chunks",
        "params": {
            "start_frame": 14500,
            "duration_frames": 180000,
            "chunk_frames": 9000,
            "window_frames": 125,
            "stride_frames": 25,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 8,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "log1p",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "concat_video": True,
        },
    },
    "exp3_reseq_long_w824_ang2_neighbor1p5_v0p1": {
        "description": "Experiment 3 long resequenced-video run with angular and neighbor features emphasized.",
        "runner": "chunks",
        "params": {
            "start_frame": 14500,
            "duration_frames": 180000,
            "chunk_frames": 9000,
            "window_frames": 125,
            "stride_frames": 25,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 8,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
            "concat_video": True,
        },
    },
    "exp3_reseq_matched_30s_w824_ang2_neighbor1p5_v0p1": {
        "description": "Experiment 3 short resequenced-video test around the mapped clear source-video example.",
        "runner": "direct",
        "params": {
            "start_frame": 101125,
            "duration_frames": 750,
            "window_frames": 125,
            "stride_frames": 25,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 8,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
        },
    },
    "exp3_reseq_matched_1min_w824_ang2_neighbor1p5_v0p1": {
        "description": "Experiment 3 one-minute resequenced-video review pass around the mapped clear source-video example.",
        "runner": "direct",
        "params": {
            "start_frame": 0,
            "duration_frames": 100000,
            "window_frames": 125,
            "stride_frames": 10,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 8,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
        },
    },
    "exp3_reseq_full_w824_ang2_neighbor1p5_v0p1": {
        "description": "Experiment 3 full resequenced-video run with the legacy angular/neighbor-weighted settings.",
        "runner": "chunks",
        "params": {
            "start_frame": 0,
            "duration_frames": 10000,
            "window_frames": 125,
            "stride_frames": 25,
            "grid_rows": 64,
            "grid_cols": 64,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 0,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
            "concat_video": True,
        },
    },
    "exp3_sampler": {
        "description": "Experiment 3 sampled resequenced-video parameter probe.",
        "runner": "samples",
        "params": {
            "start_frame": 0,
            "duration_frames": 263474,
            "sample_count": 10,
            "sample_frames": 250,
            "window_frames": 125,
            "stride_frames": 1,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 0,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
            "concat_video": True,
        },
    },
    "exp3_sampler_pca1": {
        "description": "Experiment 3 sampled resequenced-video probe with 1 PCA component.",
        "runner": "samples",
        "params": {
            "start_frame": 0,
            "duration_frames": 263474,
            "sample_count": 10,
            "sample_frames": 250,
            "window_frames": 125,
            "stride_frames": 1,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 1,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
            "overlay_title": "exp3 sampler: PCA=1, 32x32, w824",
            "concat_video": True,
        },
    },
    "exp3_sampler_pca2": {
        "description": "Experiment 3 sampled resequenced-video probe with 2 PCA components.",
        "runner": "samples",
        "params": {
            "start_frame": 0,
            "duration_frames": 263474,
            "sample_count": 10,
            "sample_frames": 250,
            "window_frames": 125,
            "stride_frames": 1,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 2,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
            "overlay_title": "exp3 sampler: PCA=2, 32x32, w824",
            "concat_video": True,
        },
    },
    "exp3_sampler_pca3": {
        "description": "Experiment 3 sampled resequenced-video probe with 3 PCA components.",
        "runner": "samples",
        "params": {
            "start_frame": 0,
            "duration_frames": 263474,
            "sample_count": 10,
            "sample_frames": 250,
            "window_frames": 125,
            "stride_frames": 1,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 3,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
            "overlay_title": "exp3 sampler: PCA=3, 32x32, w824",
            "concat_video": True,
        },
    },
    "exp3_sampler_pca5": {
        "description": "Experiment 3 sampled resequenced-video probe with 5 PCA components.",
        "runner": "samples",
        "params": {
            "start_frame": 0,
            "duration_frames": 263474,
            "sample_count": 10,
            "sample_frames": 250,
            "window_frames": 125,
            "stride_frames": 1,
            "grid_rows": 32,
            "grid_cols": 32,
            "clusters": 8,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 5,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "raw",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
            "overlay_title": "exp3 sampler: PCA=5, 32x32, w824",
            "concat_video": True,
        },
    },
    "exp4_reseq_full_highres_v0p1": {
        "description": "Full resequenced-video velocity-compressed high-resolution group-motion run.",
        "runner": "chunks",
        "params": {
            "start_frame": 0,
            "duration_frames": 263474,
            "chunk_frames": 9000,
            "window_frames": 125,
            "stride_frames": 25,
            "grid_rows": 48,
            "grid_cols": 48,
            "clusters": 10,
            "method": "gmm",
            "gmm_covariance_type": "diag",
            "gmm_reg_covar": 1e-4,
            "pca_components": 10,
            "flow_scale_width": 824,
            "feature_set": "full",
            "velocity_transform": "log1p",
            "angular_feature_weight": 2.0,
            "neighbor_feature_weight": 1.5,
            "top_mask_height": 72,
            "concat_video": True,
        },
    },
}


CLI_NAMES = {
    "activity_threshold": "--activity-threshold",
    "angular_feature_weight": "--angular-feature-weight",
    "chunk_frames": "--chunk-frames",
    "clusters": "--clusters",
    "concat_video": "--concat-video",
    "duration_frames": "--duration-frames",
    "feature_set": "--feature-set",
    "flow_scale_width": "--flow-scale-width",
    "gmm_covariance_type": "--gmm-covariance-type",
    "gmm_reg_covar": "--gmm-reg-covar",
    "grid_cols": "--grid-cols",
    "grid_rows": "--grid-rows",
    "method": "--method",
    "min_active_fraction": "--min-active-fraction",
    "neighbor_feature_weight": "--neighbor-feature-weight",
    "overwrite": "--overwrite",
    "overlay_title": "--overlay-title",
    "pca_components": "--pca-components",
    "random_state": "--random-state",
    "sample_count": "--sample-count",
    "sample_frames": "--sample-frames",
    "safeword_file": "--safeword-file",
    "start_frame": "--start-frame",
    "stride_frames": "--stride-frames",
    "top_mask_height": "--top-mask-height",
    "velocity_transform": "--velocity-transform",
    "window_frames": "--window-frames",
}


BOOLEAN_KEYS = {"concat_video", "overwrite"}

RUNNER_KEYS = {
    "direct": {
        "activity_threshold",
        "angular_feature_weight",
        "clusters",
        "duration_frames",
        "feature_set",
        "flow_scale_width",
        "gmm_covariance_type",
        "gmm_reg_covar",
        "grid_cols",
        "grid_rows",
        "method",
        "min_active_fraction",
        "neighbor_feature_weight",
        "overlay_title",
        "pca_components",
        "random_state",
        "start_frame",
        "stride_frames",
        "top_mask_height",
        "velocity_transform",
        "window_frames",
    },
    "chunks": set(CLI_NAMES),
    "samples": {
        "activity_threshold",
        "angular_feature_weight",
        "clusters",
        "concat_video",
        "duration_frames",
        "feature_set",
        "flow_scale_width",
        "gmm_covariance_type",
        "gmm_reg_covar",
        "grid_cols",
        "grid_rows",
        "method",
        "min_active_fraction",
        "neighbor_feature_weight",
        "overlay_title",
        "overwrite",
        "pca_components",
        "random_state",
        "sample_count",
        "sample_frames",
        "safeword_file",
        "start_frame",
        "stride_frames",
        "top_mask_height",
        "velocity_transform",
        "window_frames",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run named analysis presets. Presets are thin wrappers around "
            "annotate_motion_regimes.py, run_motion_regime_chunks.py, "
            "or run_motion_regime_samples.py."
        )
    )
    parser.add_argument("preset", choices=sorted(PRESETS))
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--runner",
        choices=("preset", "direct", "chunks", "samples"),
        default="preset",
        help="Override the preset runner. 'preset' uses the runner configured by the preset.",
    )
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a preset parameter. May be passed more than once.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved command without running it.")
    return parser.parse_args()


def coerce_value(value: str):
    lowered = value.casefold()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_overrides(values: list[str]) -> dict:
    overrides = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Override must be KEY=VALUE, got {value!r}")
        key, raw = value.split("=", 1)
        key = key.strip().replace("-", "_")
        if key not in CLI_NAMES:
            raise ValueError(f"Unknown preset parameter {key!r}")
        overrides[key] = coerce_value(raw.strip())
    return overrides


def params_to_cli(params: dict, runner: str) -> list[str]:
    allowed = RUNNER_KEYS[runner]
    parts = []
    for key, value in params.items():
        if key not in allowed:
            raise ValueError(f"Preset parameter {key!r} is not supported by runner {runner!r}")
        if key not in CLI_NAMES:
            raise ValueError(f"No CLI mapping for preset parameter {key!r}")
        flag = CLI_NAMES[key]
        if key in BOOLEAN_KEYS:
            if value:
                parts.append(flag)
            continue
        parts.extend([flag, str(value)])
    return parts


def git_commit() -> str | None:
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return output or None


def write_runner_metadata(
    path: Path,
    preset_name: str,
    preset: dict,
    runner: str,
    video: Path,
    out_dir: Path,
    params: dict,
    command: list[str],
    dry_run: bool,
) -> None:
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runner_version": RUNNER_VERSION,
        "analysis_version": ANALYSIS_VERSION,
        "git_commit": git_commit(),
        "preset": preset_name,
        "preset_description": preset["description"],
        "runner": runner,
        "video": str(video),
        "out_dir": str(out_dir),
        "params": params,
        "command": command,
        "dry_run": dry_run,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n")


def main() -> None:
    args = parse_args()
    preset = PRESETS[args.preset]
    params = {**preset["params"], **parse_overrides(args.overrides)}
    runner = preset["runner"] if args.runner == "preset" else args.runner

    script_names = {
        "direct": "annotate_motion_regimes.py",
        "chunks": "run_motion_regime_chunks.py",
        "samples": "run_motion_regime_samples.py",
    }
    script_name = script_names[runner]
    script = Path(__file__).with_name(script_name)
    video = args.video.expanduser()
    out_dir = args.out.expanduser()
    command = [
        sys.executable,
        str(script),
        str(video),
        "--out",
        str(out_dir),
        *params_to_cli(params, runner),
    ]

    write_runner_metadata(
        out_dir / "analysis_run.json",
        args.preset,
        preset,
        runner,
        video,
        out_dir,
        params,
        command,
        args.dry_run,
    )

    print(f"preset: {args.preset}")
    print(f"runner: {runner}")
    print("command:")
    print(" ".join(command))
    if args.dry_run:
        return
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
