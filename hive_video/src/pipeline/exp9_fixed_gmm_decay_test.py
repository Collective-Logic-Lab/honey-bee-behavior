#!/usr/bin/env python3
"""Experiment 9: fixed-GMM and fixed-GMM-with-decay overlay diagnostics."""

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
DEFAULT_OUT_ROOT = Path("data/no-sync/exp9_fixed_gmm_decay_test_start03")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render two 500-frame diagnostic videos for setting 486, vert=2.0: "
            "one using a fixed GMM and one using a fixed GMM plus temporal decay."
        )
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--start-frame", type=int, default=225000)
    parser.add_argument("--frame-count", type=int, default=500)
    parser.add_argument("--decay-half-life-frames", type=float, default=125.0)
    parser.add_argument("--fit-sample-stride", type=int, default=25)
    parser.add_argument("--chunk-target-frames", type=int, default=100)
    parser.add_argument("--flow-scale-width", type=int, default=824)
    parser.add_argument("--top-mask-height", type=int, default=72)
    parser.add_argument("--min-active-fraction", type=float, default=0.005)
    parser.add_argument("--endnote-seconds", type=float, default=7.0)
    parser.add_argument("--safeword-file", type=Path, default=Path(".safeword"))
    parser.add_argument(
        "--only",
        choices=["both", "fixed", "decay"],
        default="both",
        help="Run both diagnostics or only one branch.",
    )
    return parser.parse_args()


def run_overlay(args: argparse.Namespace, out: Path, decay_half_life_frames: float) -> None:
    overlay_script = Path(__file__).with_name("exp6e_profile_overlay.py")
    end_frame = args.start_frame + args.frame_count
    command = [
        sys.executable,
        str(overlay_script),
        "--video",
        str(args.video),
        "--source-manifest",
        str(args.source_manifest),
        "--out",
        str(out),
        "--base-setting-id",
        "486",
        "--vertical-weight",
        "2.0",
        "--start-frame",
        str(args.start_frame),
        "--end-frame",
        str(end_frame),
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
        "--fixed-gmm",
        "--fit-sample-stride",
        str(args.fit_sample_stride),
        "--endnotes",
        "--endnote-seconds",
        str(args.endnote_seconds),
    ]
    if decay_half_life_frames > 0:
        command.extend(["--decay-half-life-frames", str(decay_half_life_frames)])
    print("command:", flush=True)
    print(" ".join(command), flush=True)
    subprocess.run(command, check=True)


def main() -> None:
    args = parse_args()
    out_root = args.out_root.expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    frame_end_inclusive = args.start_frame + args.frame_count - 1

    if args.only in {"both", "fixed"}:
        run_overlay(
            args,
            out_root / f"exp9_fixed_gmm_frames{args.start_frame}_{frame_end_inclusive}.mp4",
            0.0,
        )
    if args.only in {"both", "decay"}:
        run_overlay(
            args,
            out_root
            / (
                f"exp9_fixed_gmm_decay_h{args.decay_half_life_frames:g}_"
                f"frames{args.start_frame}_{frame_end_inclusive}.mp4"
            ),
            args.decay_half_life_frames,
        )


if __name__ == "__main__":
    main()
