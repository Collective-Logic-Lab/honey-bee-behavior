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
    "pca_components": "--pca-components",
    "random_state": "--random-state",
    "safeword_file": "--safeword-file",
    "start_frame": "--start-frame",
    "stride_frames": "--stride-frames",
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
        "pca_components",
        "random_state",
        "start_frame",
        "stride_frames",
        "velocity_transform",
        "window_frames",
    },
    "chunks": set(CLI_NAMES),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run named analysis presets. Presets are thin wrappers around "
            "annotate_motion_regimes.py or run_motion_regime_chunks.py."
        )
    )
    parser.add_argument("preset", choices=sorted(PRESETS))
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--runner",
        choices=("preset", "direct", "chunks"),
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

    script_name = "annotate_motion_regimes.py" if runner == "direct" else "run_motion_regime_chunks.py"
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
