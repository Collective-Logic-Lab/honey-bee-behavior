"""Build the local staging tree for Hive Video Distribution 1.

The staging tree mirrors the remote distribution layout. It intentionally omits
the Git-tracked seed video and the small example experiment, and includes only
the selected Experiment 3 overnight runs used in the notebook figure.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_STAGE = Path("distribution-1")
SELECTED_EXP3_RUNS = ("09_asinh_velocity", "11_high_angular", "16_long_window")


def copy_or_link_file(src: Path, dst: Path, mode: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()

    if mode == "copy":
        shutil.copy2(src, dst)
        return

    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path, mode: str) -> list[str]:
    copied: list[str] = []
    for path in sorted(src.rglob("*")):
        if path.is_dir() or path.name == ".DS_Store":
            continue
        rel = path.relative_to(src)
        copy_or_link_file(path, dst / rel, mode)
        copied.append(str((dst / rel).as_posix()))
    return copied


def require_dir(path: Path) -> None:
    if not path.is_dir():
        raise SystemExit(f"missing required directory: {path}")


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"missing required file: {path}")


def write_readme(path: Path) -> None:
    path.write_text(
        """# Hive Video Distribution 1

This distribution contains the larger artifacts needed by the Hive Video
notebooks. It is designed to be synced into the repository's `hive_video/data`
directory by `uv run python get_dist_1.py`.

Included:
- resequenced video artifacts under `data/artifacts/resequenced`
- Experiment 1 and Experiment 2 outputs
- selected Experiment 3 overnight outputs for runs 09, 11, and 16
- Experiment 3 summary figure and quadrant metric tables

Not included:
- `data/raw/start04_sample_5s.mp4`, which is tracked directly in Git
- `data/experiments/experiment_example_5s`, which is tracked directly in Git
- the full Experiment 3 overnight sweep, which remains available separately
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage Hive Video Distribution 1 files.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=DEFAULT_STAGE)
    parser.add_argument(
        "--mode",
        choices=("hardlink", "copy"),
        default="hardlink",
        help="Use hardlinks when possible to avoid duplicating large local files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Remove the existing staging directory before rebuilding it.",
    )
    args = parser.parse_args()

    data_dir = args.data_dir
    out = args.out
    if out.exists():
        if not args.overwrite:
            raise SystemExit(f"staging directory already exists: {out}; use --overwrite")
        shutil.rmtree(out)

    payload_root = out / "data"
    copied: list[str] = []

    artifacts_src = data_dir / "artifacts" / "resequenced"
    require_dir(artifacts_src)
    copied.extend(copy_tree(artifacts_src, payload_root / "artifacts" / "resequenced", args.mode))

    for name in ("exp1_reseq_2min_v0p1", "exp2_reseq_focus_v0p1"):
        src = data_dir / "experiments" / name
        require_dir(src)
        copied.extend(copy_tree(src, payload_root / "experiments" / name, args.mode))

    exp3_src = data_dir / "experiments" / "exp3_overnight"
    require_dir(exp3_src)
    exp3_dst = payload_root / "experiments" / "exp3_overnight"
    for name in SELECTED_EXP3_RUNS:
        src = exp3_src / name
        require_dir(src)
        copied.extend(copy_tree(src, exp3_dst / name, args.mode))

    for filename in (
        "exp3.png",
        "frame87900_quadrant_metrics_exclude_top72.csv",
        "frame87950_quadrant_metrics_exclude_top72.csv",
    ):
        src = exp3_src / filename
        require_file(src)
        copy_or_link_file(src, exp3_dst / filename, args.mode)
        copied.append(str((exp3_dst / filename).as_posix()))

    manifest = {
        "name": "distribution-1",
        "version": "v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "data_root": "data",
        "omitted_git_tracked": [
            "data/raw/start04_sample_5s.mp4",
            "data/experiments/experiment_example_5s",
        ],
        "selected_exp3_runs": list(SELECTED_EXP3_RUNS),
        "files": sorted(copied),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_readme(out / "README.md")

    print(f"wrote {len(copied)} files to {out}")
    print("sync with:")
    print(
        "hf sync "
        f"{out.as_posix()} "
        "hf://buckets/collective-logic-lab/honey-bee/distributions/distribution-1/v1 "
        '--exclude "**/.DS_Store"'
    )


if __name__ == "__main__":
    main()
