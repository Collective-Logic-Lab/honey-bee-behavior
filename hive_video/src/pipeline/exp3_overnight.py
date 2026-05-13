#!/usr/bin/env python3
"""Run an overnight Experiment 3 sampler tour across distinct settings."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


CONFIGS = [
    {
        "name": "01_grid32_pca0",
        "title": "exp3 overnight 01: grid32 PCA0 raw",
        "overrides": {"grid_rows": 32, "grid_cols": 32, "pca_components": 0},
    },
    {
        "name": "02_grid48_pca0",
        "title": "exp3 overnight 02: grid48 PCA0 raw",
        "overrides": {"grid_rows": 48, "grid_cols": 48, "pca_components": 0},
    },
    {
        "name": "03_grid64_pca0",
        "title": "exp3 overnight 03: grid64 PCA0 raw",
        "overrides": {"grid_rows": 64, "grid_cols": 64, "pca_components": 0},
    },
    {
        "name": "04_clusters6",
        "title": "exp3 overnight 04: clusters6 grid32",
        "overrides": {"grid_rows": 32, "grid_cols": 32, "clusters": 6, "pca_components": 0},
    },
    {
        "name": "05_clusters10",
        "title": "exp3 overnight 05: clusters10 grid32",
        "overrides": {"grid_rows": 32, "grid_cols": 32, "clusters": 10, "pca_components": 0},
    },
    {
        "name": "06_activity020",
        "title": "exp3 overnight 06: activity0.20",
        "overrides": {"activity_threshold": 0.20, "pca_components": 0},
    },
    {
        "name": "07_activity050",
        "title": "exp3 overnight 07: activity0.50",
        "overrides": {"activity_threshold": 0.50, "pca_components": 0},
    },
    {
        "name": "08_log1p_velocity",
        "title": "exp3 overnight 08: log1p velocity",
        "overrides": {"velocity_transform": "log1p", "pca_components": 0},
    },
    {
        "name": "09_asinh_velocity",
        "title": "exp3 overnight 09: asinh velocity",
        "overrides": {"velocity_transform": "asinh", "pca_components": 0},
    },
    {
        "name": "10_low_group_weights",
        "title": "exp3 overnight 10: angular1 neighbor1",
        "overrides": {"angular_feature_weight": 1.0, "neighbor_feature_weight": 1.0, "pca_components": 0},
    },
    {
        "name": "11_high_angular",
        "title": "exp3 overnight 11: angular3 neighbor1.5",
        "overrides": {"angular_feature_weight": 3.0, "neighbor_feature_weight": 1.5, "pca_components": 0},
    },
    {
        "name": "12_high_neighbor",
        "title": "exp3 overnight 12: angular2 neighbor3",
        "overrides": {"angular_feature_weight": 2.0, "neighbor_feature_weight": 3.0, "pca_components": 0},
    },
    {
        "name": "13_exp1_features",
        "title": "exp3 overnight 13: exp1 feature set",
        "overrides": {"feature_set": "exp1", "pca_components": 0},
    },
    {
        "name": "14_beginner_features",
        "title": "exp3 overnight 14: beginner features",
        "overrides": {"feature_set": "beginner", "pca_components": 0, "clusters": 6},
    },
    {
        "name": "15_short_window",
        "title": "exp3 overnight 15: window50 sample250",
        "overrides": {"window_frames": 50, "sample_frames": 250, "pca_components": 0},
    },
    {
        "name": "16_long_window",
        "title": "exp3 overnight 16: window250 sample500",
        "overrides": {"window_frames": 250, "sample_frames": 500, "pca_components": 0},
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run 16 distinct Experiment 3 sampler configurations in sequence. "
            "Each configuration writes to a named subdirectory under --out-root."
        )
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=Path("data/artifacts/resequenced/reseq_1_start04__20190609_175013_side0_top.mp4"),
    )
    parser.add_argument("--out-root", type=Path, default=Path("data/qc/exp3_overnight"))
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def safeword_triggered(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(errors="ignore").casefold()
    except OSError:
        return False
    return "sea cucumber" in text or "seacucubmer" in text


def write_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        fieldnames = [
            "index",
            "name",
            "out_dir",
            "status",
            "started_at_utc",
            "finished_at_utc",
            "return_code",
            "title",
            "overrides",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    hive_video_root = Path(__file__).resolve().parents[2]
    run_analysis = hive_video_root / "src" / "analyze" / "run_analysis.py"
    video = args.video.expanduser()
    out_root = args.out_root.expanduser()
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    rows: list[dict] = []
    manifest = out_root / "exp3_overnight_manifest.csv"
    for index, config in enumerate(CONFIGS, start=1):
        out_dir = out_root / config["name"]
        if safeword_triggered(safeword_file):
            print(f"safeword detected before {config['name']}; stopping", flush=True)
            rows.append(
                {
                    "index": index,
                    "name": config["name"],
                    "out_dir": str(out_dir),
                    "status": "skipped_safeword",
                    "started_at_utc": "",
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                    "return_code": "",
                    "title": config["title"],
                    "overrides": repr(config["overrides"]),
                }
            )
            write_manifest(manifest, rows)
            break

        command = [
            sys.executable,
            str(run_analysis),
            "exp3_sampler",
            "--video",
            str(video),
            "--out",
            str(out_dir),
            "--set",
            f"overlay_title={config['title']}",
            "--set",
            f"safeword_file={safeword_file}",
        ]
        for key, value in config["overrides"].items():
            command.extend(["--set", f"{key}={value}"])
        if args.dry_run:
            command.append("--dry-run")

        started = datetime.now(timezone.utc).isoformat()
        print(f"running {index:02d}/16 {config['name']}: {out_dir}", flush=True)
        result = subprocess.run(command, check=False)
        finished = datetime.now(timezone.utc).isoformat()
        status = "done" if result.returncode == 0 else "failed"
        rows.append(
            {
                "index": index,
                "name": config["name"],
                "out_dir": str(out_dir),
                "status": status,
                "started_at_utc": started,
                "finished_at_utc": finished,
                "return_code": result.returncode,
                "title": config["title"],
                "overrides": repr(config["overrides"]),
            }
        )
        write_manifest(manifest, rows)
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    print(f"wrote manifest: {manifest}", flush=True)


if __name__ == "__main__":
    main()
