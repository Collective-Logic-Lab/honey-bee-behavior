#!/usr/bin/env python3
"""Experiment 9 sync-fix smoke test for one source-synchronous overlay frame."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_VIDEO = Path("data/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4")
DEFAULT_OUT_DIR = Path("data/no-sync/exp9_sync_fix_frame238847")
DEFAULT_FRAME = 238847


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render exactly one source-synchronous overlay frame with the profile 0486 flat "
            "fixed-GMM settings, for comparison against the resequenced source video."
        )
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--frame", type=int, default=DEFAULT_FRAME)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    overlay_script = Path(__file__).with_name("exp6e_profile_overlay.py")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"exp9_sync_fix_profile0486_flat_source_frame{args.frame}.mp4"
    command = [
        sys.executable,
        str(overlay_script),
        "--video",
        str(args.video),
        "--out",
        str(out),
        "--base-setting-id",
        "486",
        "--vertical-weight",
        "2.0",
        "--start-frame",
        str(args.frame),
        "--end-frame",
        str(args.frame + 1),
        "--stride",
        "1",
        "--source-synchronous-output",
        "--chunk-target-frames",
        "1",
        "--flow-scale-width",
        "824",
        "--top-mask-height",
        "72",
        "--fixed-gmm",
        "--fit-sample-stride",
        "1",
    ]
    print("command:")
    print(" ".join(command))
    subprocess.run(command, check=True)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
