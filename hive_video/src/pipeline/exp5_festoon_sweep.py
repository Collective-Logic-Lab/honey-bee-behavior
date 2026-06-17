#!/usr/bin/env python3
"""Run focused Experiment 5 overlays for the start03 festoon-formation interval."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_VIDEO = Path(
    "data/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4"
)
DEFAULT_OUT_ROOT = Path("data/no-sync/exp5_festoon_sweep_start03")


def parse_float_list(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a 5 x 5 x 3 focused motion-regime sweep over the start03 "
            "festoon-formation interval. The swept frame values are applied as "
            "window_frames for continuous 10,000-frame overlay clips."
        )
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--start-frame", type=int, default=218000)
    parser.add_argument("--duration-frames", type=int, default=10000)
    parser.add_argument("--stride-frames", type=int, default=10)
    parser.add_argument("--window-frames", default="250,500,1000")
    parser.add_argument("--angular-values", default="1.0,1.5,2.0,2.5,3.0")
    parser.add_argument("--neighbor-values", default="0.75,1.0,1.5,2.0,3.0")
    parser.add_argument("--grid-rows", type=int, default=64)
    parser.add_argument("--grid-cols", type=int, default=64)
    parser.add_argument("--clusters", type=int, default=8)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def write_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "index",
        "name",
        "out_dir",
        "status",
        "started_at_utc",
        "finished_at_utc",
        "return_code",
        "start_frame",
        "duration_frames",
        "window_frames",
        "stride_frames",
        "grid_rows",
        "grid_cols",
        "clusters",
        "angular_feature_weight",
        "neighbor_feature_weight",
        "command",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    hive_video_root = Path(__file__).resolve().parents[2]
    run_analysis = hive_video_root / "src" / "analyze" / "run_analysis.py"

    video = args.video.expanduser()
    out_root = args.out_root.expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    manifest = out_root / "exp5_festoon_sweep_manifest.csv"

    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    window_values = parse_int_list(args.window_frames)
    angular_values = parse_float_list(args.angular_values)
    neighbor_values = parse_float_list(args.neighbor_values)

    rows: list[dict] = []
    total = len(window_values) * len(angular_values) * len(neighbor_values)
    index = 0
    for window_frames in window_values:
        for angular in angular_values:
            for neighbor in neighbor_values:
                index += 1
                name = (
                    f"w{window_frames}_ang{label_number(angular)}_"
                    f"nbr{label_number(neighbor)}"
                )
                out_dir = out_root / name
                overlay = out_dir / "motion_regime_overlay.mp4"
                metadata = out_dir / "metadata.json"

                base_row = {
                    "index": index,
                    "name": name,
                    "out_dir": str(out_dir),
                    "start_frame": args.start_frame,
                    "duration_frames": args.duration_frames,
                    "window_frames": window_frames,
                    "stride_frames": args.stride_frames,
                    "grid_rows": args.grid_rows,
                    "grid_cols": args.grid_cols,
                    "clusters": args.clusters,
                    "angular_feature_weight": angular,
                    "neighbor_feature_weight": neighbor,
                }

                if safeword_triggered(safeword_file):
                    rows.append(
                        {
                            **base_row,
                            "status": "skipped_safeword",
                            "started_at_utc": "",
                            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                            "return_code": "",
                            "command": "",
                        }
                    )
                    write_manifest(manifest, rows)
                    print(f"safeword detected before {name}; stopping", flush=True)
                    print(f"wrote manifest: {manifest}", flush=True)
                    return

                title = (
                    f"exp5 start03 {args.start_frame}-{args.start_frame + args.duration_frames} "
                    f"w{window_frames} stride{args.stride_frames} "
                    f"ang{angular:g} nbr{neighbor:g}"
                )
                command = [
                    sys.executable,
                    str(run_analysis),
                    "full_group_motion_v1",
                    "--runner",
                    "direct",
                    "--video",
                    str(video),
                    "--out",
                    str(out_dir),
                    "--set",
                    f"start_frame={args.start_frame}",
                    "--set",
                    f"duration_frames={args.duration_frames}",
                    "--set",
                    f"window_frames={window_frames}",
                    "--set",
                    f"stride_frames={args.stride_frames}",
                    "--set",
                    f"grid_rows={args.grid_rows}",
                    "--set",
                    f"grid_cols={args.grid_cols}",
                    "--set",
                    f"clusters={args.clusters}",
                    "--set",
                    "pca_components=0",
                    "--set",
                    f"flow_scale_width={args.flow_scale_width}",
                    "--set",
                    "feature_set=full",
                    "--set",
                    "velocity_transform=raw",
                    "--set",
                    f"angular_feature_weight={angular}",
                    "--set",
                    f"neighbor_feature_weight={neighbor}",
                    "--set",
                    "top_mask_height=72",
                    "--set",
                    f"overlay_title={title}",
                ]
                if args.dry_run:
                    command.append("--dry-run")
                if overlay.exists() and metadata.exists() and not args.overwrite and not args.dry_run:
                    rows.append(
                        {
                            **base_row,
                            "status": "skipped_existing",
                            "started_at_utc": "",
                            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                            "return_code": "",
                            "command": " ".join(command),
                        }
                    )
                    write_manifest(manifest, rows)
                    print(f"skipping existing {index:02d}/{total} {name}", flush=True)
                    continue

                print(f"running {index:02d}/{total} {name}: {out_dir}", flush=True)
                started = datetime.now(timezone.utc).isoformat()
                result = subprocess.run(command, check=False)
                finished = datetime.now(timezone.utc).isoformat()
                status = "done" if result.returncode == 0 else "failed"
                rows.append(
                    {
                        **base_row,
                        "status": status,
                        "started_at_utc": started,
                        "finished_at_utc": finished,
                        "return_code": result.returncode,
                        "command": " ".join(command),
                    }
                )
                write_manifest(manifest, rows)
                if result.returncode != 0:
                    raise SystemExit(result.returncode)

    print(f"wrote manifest: {manifest}", flush=True)


if __name__ == "__main__":
    main()
