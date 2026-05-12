#!/usr/bin/env python3
"""Create a review video showing candidate segment joins."""

from __future__ import annotations

import argparse
import csv
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a review MP4 from ranked segment joins. Each join shows a short clip before "
            "the source segment end followed by a short clip after the candidate next segment start."
        )
    )
    parser.add_argument("video", type=Path, help="Source MP4.")
    parser.add_argument("--ranked-edges", type=Path, required=True, help="ranked_edges.csv.")
    parser.add_argument("--out", type=Path, required=True, help="Output review MP4.")
    parser.add_argument("--rank", type=int, default=1, help="Which rank_for_from_segment to review.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of joins to include.")
    parser.add_argument("--seconds-each-side", type=float, default=2.0, help="Clip seconds per side.")
    parser.add_argument("--fps", type=float, default=25.0, help="Video frame rate.")
    parser.add_argument(
        "--scale-width",
        type=int,
        default=824,
        help="Output width; height is computed by ffmpeg to preserve aspect ratio.",
    )
    parser.add_argument(
        "--caption-mode",
        choices=("auto", "drawtext", "pillow", "none"),
        default="auto",
        help=(
            "Caption mode. 'auto' uses drawtext when available, otherwise Pillow-generated "
            "caption bars overlaid with ffmpeg."
        ),
    )
    parser.add_argument(
        "--separator-seconds",
        type=float,
        default=0.08,
        help="Insert a solid separator clip of this duration at each join.",
    )
    parser.add_argument(
        "--separator-color",
        default="green",
        help="ffmpeg color name or hex color for the separator clip.",
    )
    return parser.parse_args()


def read_edges(path: Path, rank: int, limit: int) -> list[dict]:
    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            if int(row["rank_for_from_segment"]) != rank:
                continue
            row["from_segment_id"] = int(row["from_segment_id"])
            row["to_segment_id"] = int(row["to_segment_id"])
            row["from_end_frame_idx"] = int(row["from_end_frame_idx"])
            row["to_start_frame_idx"] = int(row["to_start_frame_idx"])
            row["mean_abs_diff"] = float(row["mean_abs_diff"])
            rows.append(row)
    rows.sort(key=lambda row: row["from_segment_id"])
    return rows[:limit]


def ffmpeg_escape_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def make_clip(
    video: Path,
    out_path: Path,
    start_s: float,
    duration_s: float,
    caption: str,
    scale_width: int,
    caption_mode: str,
    caption_image: Path | None = None,
) -> None:
    if caption_mode == "drawtext":
        safe_caption = ffmpeg_escape_text(caption)
        vf = (
            f"scale={scale_width}:-2,"
            "pad=iw:ih+64:0:64:color=black,"
            f"drawtext=text='{safe_caption}':x=16:y=18:"
            "fontcolor=white:fontsize=24:box=1:boxcolor=black@0.6:boxborderw=8"
        )
        inputs = ["-i", str(video)]
        output_options = ["-vf", vf]
    elif caption_mode == "pillow":
        if caption_image is None:
            raise ValueError("caption_image is required for pillow caption mode")
        inputs = ["-i", str(video), "-i", str(caption_image)]
        filter_complex = (
            f"[0:v]scale={scale_width}:-2[base];"
            "[base][1:v]overlay=0:0:format=auto"
        )
        output_options = ["-filter_complex", filter_complex]
    else:
        inputs = ["-i", str(video)]
        vf = f"scale={scale_width}:-2"
        output_options = ["-vf", vf]
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-ss",
        f"{max(0.0, start_s):.6f}",
        *inputs,
        "-t",
        f"{duration_s:.6f}",
        *output_options,
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def make_caption_image(path: Path, caption: str, width: int, height: int = 72) -> None:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 210))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)
    except OSError:
        font = ImageFont.load_default()

    max_width = width - 32
    words = caption.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    lines = lines[:2]

    y = 10
    for line in lines:
        draw.text((16, y), line, fill=(255, 255, 255, 255), font=font)
        y += 28
    image.save(path)


def make_separator_clip(out_path: Path, duration_s: float, scale_width: int, color: str) -> None:
    # The source video aspect at 824px wide is 752px high; keep that fixed for concat compatibility.
    height = round(scale_width * 1504 / 1648)
    if height % 2:
        height += 1
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={scale_width}x{height}:r=25:d={duration_s}",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def write_concat_list(path: Path, clips: list[Path]) -> None:
    with path.open("w") as f:
        for clip in clips:
            escaped = str(clip).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")


def ffmpeg_has_filter(name: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return any(line.split()[1:2] == [name] for line in result.stdout.splitlines() if line.split())


def write_caption_manifest(path: Path, rows: list[dict]) -> None:
    import csv

    with path.open("w", newline="") as f:
        fieldnames = ["clip_index", "join_index", "side", "review_start_s", "review_stop_s", "caption"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    ranked_edges = args.ranked_edges.expanduser().resolve()
    out = args.out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    edges = read_edges(ranked_edges, args.rank, args.limit)
    if not edges:
        raise RuntimeError("No ranked edges matched the requested rank.")

    if args.caption_mode == "auto":
        caption_mode = "drawtext" if ffmpeg_has_filter("drawtext") else "pillow"
    else:
        caption_mode = args.caption_mode
    if caption_mode == "pillow":
        print("using Pillow-generated caption bars with ffmpeg overlay", flush=True)
    elif caption_mode == "none":
        print("caption overlay disabled; writing sidecar captions only", flush=True)

    caption_rows = []
    with tempfile.TemporaryDirectory(prefix="join_review_") as tmpdir:
        tmp = Path(tmpdir)
        clips = []
        review_time = 0.0
        for join_index, edge in enumerate(edges, start=1):
            before_start = edge["from_end_frame_idx"] / args.fps - args.seconds_each_side
            after_start = edge["to_start_frame_idx"] / args.fps
            shared = (
                f"join {join_index:03d} rank {args.rank} "
                f"S{edge['from_segment_id']} -> S{edge['to_segment_id']} "
                f"diff {edge['mean_abs_diff']:.3f}"
            )
            before_caption = (
                f"{shared} | before end frame {edge['from_end_frame_idx']} "
                f"t={edge['from_end_frame_idx'] / args.fps:.2f}s"
            )
            after_caption = (
                f"{shared} | after start frame {edge['to_start_frame_idx']} "
                f"t={edge['to_start_frame_idx'] / args.fps:.2f}s"
            )
            before_clip = tmp / f"join_{join_index:03d}_before.mp4"
            separator_clip = tmp / f"join_{join_index:03d}_separator.mp4"
            after_clip = tmp / f"join_{join_index:03d}_after.mp4"
            before_caption_image = tmp / f"join_{join_index:03d}_before_caption.png"
            after_caption_image = tmp / f"join_{join_index:03d}_after_caption.png"
            print(f"rendering join {join_index}: {shared}", flush=True)
            if caption_mode == "pillow":
                make_caption_image(before_caption_image, before_caption, args.scale_width)
            make_clip(
                video,
                before_clip,
                before_start,
                args.seconds_each_side,
                before_caption,
                args.scale_width,
                caption_mode,
                before_caption_image if caption_mode == "pillow" else None,
            )
            caption_rows.append(
                {
                    "clip_index": len(clips) + 1,
                    "join_index": join_index,
                    "side": "before",
                    "review_start_s": f"{review_time:.6f}",
                    "review_stop_s": f"{review_time + args.seconds_each_side:.6f}",
                    "caption": before_caption,
                }
            )
            review_time += args.seconds_each_side
            make_separator_clip(
                separator_clip,
                args.separator_seconds,
                args.scale_width,
                args.separator_color,
            )
            caption_rows.append(
                {
                    "clip_index": len(clips) + 2,
                    "join_index": join_index,
                    "side": "separator",
                    "review_start_s": f"{review_time:.6f}",
                    "review_stop_s": f"{review_time + args.separator_seconds:.6f}",
                    "caption": f"{shared} | JOIN MARKER",
                }
            )
            review_time += args.separator_seconds
            if caption_mode == "pillow":
                make_caption_image(after_caption_image, after_caption, args.scale_width)
            make_clip(
                video,
                after_clip,
                after_start,
                args.seconds_each_side,
                after_caption,
                args.scale_width,
                caption_mode,
                after_caption_image if caption_mode == "pillow" else None,
            )
            caption_rows.append(
                {
                    "clip_index": len(clips) + 3,
                    "join_index": join_index,
                    "side": "after",
                    "review_start_s": f"{review_time:.6f}",
                    "review_stop_s": f"{review_time + args.seconds_each_side:.6f}",
                    "caption": after_caption,
                }
            )
            review_time += args.seconds_each_side
            clips.extend([before_clip, separator_clip, after_clip])

        concat_list = tmp / "concat.txt"
        write_concat_list(concat_list, clips)
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(out),
        ]
        subprocess.run(cmd, check=True)

    captions_path = out.with_suffix(".captions.csv")
    write_caption_manifest(captions_path, caption_rows)
    print(f"wrote review video: {out}")
    print(f"wrote captions: {captions_path}")


if __name__ == "__main__":
    main()
