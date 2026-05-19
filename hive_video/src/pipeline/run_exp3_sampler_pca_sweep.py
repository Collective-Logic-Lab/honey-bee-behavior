#!/usr/bin/env python3
"""Run Experiment 3 sampler presets for a small PCA-component sweep."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PRESETS = [
    "exp3_sampler_pca1",
    "exp3_sampler_pca2",
    "exp3_sampler_pca3",
    "exp3_sampler_pca5",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Experiment 3 sampler PCA sweep in order. Each preset writes "
            "to a matching output directory under --out-root."
        )
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=Path("data/artifacts/resequenced/reseq_1_start04__20190609_175013_side0_top.mp4"),
    )
    parser.add_argument("--out-root", type=Path, default=Path("data/qc"))
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
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "preset",
                "out_dir",
                "status",
                "started_at_utc",
                "finished_at_utc",
                "return_code",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    repo_hive_video = Path(__file__).resolve().parents[2]
    run_analysis = repo_hive_video / "src" / "analyze" / "run_analysis.py"
    video = args.video.expanduser()
    out_root = args.out_root.expanduser()
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    rows = []
    manifest = out_root / "exp3_sampler_pca_sweep_manifest.csv"
    for preset in PRESETS:
        out_dir = out_root / preset
        if safeword_triggered(safeword_file):
            print(f"safeword detected before {preset}; stopping", flush=True)
            rows.append(
                {
                    "preset": preset,
                    "out_dir": str(out_dir),
                    "status": "skipped_safeword",
                    "started_at_utc": "",
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                    "return_code": "",
                }
            )
            write_manifest(manifest, rows)
            break

        command = [
            sys.executable,
            str(run_analysis),
            preset,
            "--video",
            str(video),
            "--out",
            str(out_dir),
            "--set",
            f"safeword_file={safeword_file}",
        ]
        if args.dry_run:
            command.append("--dry-run")

        started = datetime.now(timezone.utc).isoformat()
        print(f"running {preset}: {out_dir}", flush=True)
        result = subprocess.run(command, check=False)
        finished = datetime.now(timezone.utc).isoformat()
        status = "done" if result.returncode == 0 else "failed"
        rows.append(
            {
                "preset": preset,
                "out_dir": str(out_dir),
                "status": status,
                "started_at_utc": started,
                "finished_at_utc": finished,
                "return_code": result.returncode,
            }
        )
        write_manifest(manifest, rows)
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    print(f"wrote manifest: {manifest}", flush=True)


if __name__ == "__main__":
    main()
