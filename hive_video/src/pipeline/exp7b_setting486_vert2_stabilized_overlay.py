#!/usr/bin/env python3
"""Experiment 7b: stabilized setting-486 overlay with cluster notes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_VIDEO = Path(
    "data/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4"
)
DEFAULT_SOURCE_MANIFEST = Path(
    "data/no-sync/exp6d_focused_sweep_start03/exp6d_focused_sweep_manifest.csv"
)
DEFAULT_OUT = Path(
    "data/no-sync/exp7b_setting486_vert2_stabilized_overlay_start03/"
    "exp7b_setting486_vert2_stabilized_frames228000_231000_endnotes.mp4"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render every frame from 228000 through 231000 with stabilized cluster colors "
            "and an endnote card summarizing what the display clusters measure."
        )
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--start-frame", type=int, default=228000)
    parser.add_argument(
        "--end-frame",
        type=int,
        default=231001,
        help="Exclusive end frame; default includes frame 231000.",
    )
    parser.add_argument("--chunk-target-frames", type=int, default=100)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--min-active-fraction", type=float, default=0.005)
    parser.add_argument("--endnote-seconds", type=float, default=7.0)
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    overlay_script = Path(__file__).with_name("exp6e_profile_overlay.py")
    command = [
        sys.executable,
        str(overlay_script),
        "--video",
        str(args.video),
        "--source-manifest",
        str(args.source_manifest),
        "--out",
        str(args.out),
        "--base-setting-id",
        "486",
        "--vertical-weight",
        "2.0",
        "--start-frame",
        str(args.start_frame),
        "--end-frame",
        str(args.end_frame),
        "--stride",
        "1",
        "--chunk-target-frames",
        str(args.chunk_target_frames),
        "--flow-scale-width",
        str(args.flow_scale_width),
        "--top-mask-height",
        str(args.top_mask_height),
        "--min-active-fraction",
        str(args.min_active_fraction),
        "--safeword-file",
        str(args.safeword_file),
        "--stabilize-colors",
        "--endnotes",
        "--endnote-seconds",
        str(args.endnote_seconds),
    ]
    print("command:", flush=True)
    print(" ".join(command), flush=True)
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
