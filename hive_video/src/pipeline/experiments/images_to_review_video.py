#!/usr/bin/env python3
"""Render ordered Experiment 6 still frames into an MP4 review movie."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


SETTING_RE = re.compile(r"setting_(\d+)\.png$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create an MP4 from setting_####.png files in a folder. Frames are sorted "
            "by setting number and held for a configurable number of seconds."
        )
    )
    parser.add_argument("image_dir", type=Path, help="Folder containing setting_####.png files.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output MP4. Default: <image_dir>/review_movie.mp4",
    )
    parser.add_argument(
        "--seconds-per-image",
        type=float,
        default=1.0,
        help="Seconds to display each overlay image.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Output video frame rate.",
    )
    parser.add_argument(
        "--pattern",
        default="setting_*.png",
        help="Glob pattern for input images.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setting_number(path: Path) -> int:
    match = SETTING_RE.search(path.name)
    if not match:
        return 10**12
    return int(match.group(1))


def ffconcat_escape(path: Path) -> str:
    return str(path.resolve()).replace("'", "'\\''")


def main() -> None:
    args = parse_args()
    image_dir = args.image_dir.expanduser().resolve()
    if not image_dir.is_dir():
        raise SystemExit(f"not a directory: {image_dir}")
    images = sorted(image_dir.glob(args.pattern), key=setting_number)
    if not images:
        raise SystemExit(f"no images matched {args.pattern!r} in {image_dir}")

    out = args.out.expanduser().resolve() if args.out else image_dir / "review_movie.mp4"
    if out.exists() and not args.overwrite:
        raise SystemExit(f"output exists: {out}; use --overwrite")
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"images: {len(images)}")
    print(f"seconds per image: {args.seconds_per_image}")
    print(f"output: {out}")

    with tempfile.TemporaryDirectory(prefix="image_review_") as tmpdir:
        concat_path = Path(tmpdir) / "images.ffconcat"
        with concat_path.open("w") as f:
            f.write("ffconcat version 1.0\n")
            for image in images:
                f.write(f"file '{ffconcat_escape(image)}'\n")
                f.write(f"duration {args.seconds_per_image:.6f}\n")
            # ffmpeg concat demuxer needs the final file repeated for its duration.
            f.write(f"file '{ffconcat_escape(images[-1])}'\n")

        command = [
            "ffmpeg",
            "-y" if args.overwrite else "-n",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-r",
            str(args.fps),
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
        print(" ".join(command))
        if args.dry_run:
            return
        subprocess.run(command, check=True)

    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
