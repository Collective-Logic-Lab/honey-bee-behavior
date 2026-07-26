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
            "Build a review MP4 from ranked segment joins. Each join shows a short "
            "clip before the source segment end followed by a short clip after the "
            "candidate next segment start."
        )
    )
    parser.add_argument("video", type=Path, help="Source MP4.")
    parser.add_argument("--ranked-edges", type=Path, required=True, help="ranked_edges.csv.")
    parser.add_argument(
        "--segments",
        type=Path,
        help="segments.csv; required with --order-csv.",
    )
    parser.add_argument(
        "--order-csv",
        type=Path,
        help=(
            "Review the exact consecutive joins in this proposed order. Requires "
            "--segments and includes every join unless --limit is set."
        ),
    )
    parser.add_argument("--out", type=Path, required=True, help="Output review MP4.")
    parser.add_argument(
        "--rank",
        type=int,
        default=1,
        help="Which rank_for_from_segment to review.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum joins to include. Candidate-rank review defaults to 20; exact-order "
            "review defaults to all joins."
        ),
    )
    parser.add_argument(
        "--seconds-each-side",
        type=float,
        default=2.0,
        help="Clip seconds per side.",
    )
    parser.add_argument("--fps", type=float, default=25.0, help="Video frame rate.")
    parser.add_argument(
        "--scale-width",
        type=int,
        default=824,
        help="Output width; height is computed by ffmpeg to preserve aspect ratio.",
    )
    parser.add_argument(
        "--caption-height",
        type=int,
        default=40,
        help="Height in pixels of the top caption strip; use 0 with --caption-mode none.",
    )
    parser.add_argument(
        "--caption-font-size",
        type=int,
        default=16,
        help="Caption font size in pixels.",
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


def read_edges(path: Path, rank: int, limit: int | None) -> list[dict]:
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
    return rows if limit is None else rows[:limit]


def read_order_edges(
    segments_path: Path,
    order_path: Path,
    ranked_edges_path: Path,
    limit: int | None,
) -> list[dict]:
    segments: dict[int, dict[str, int]] = {}
    with segments_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            segment_id = int(row["segment_id"])
            if segment_id in segments:
                raise ValueError(f"Duplicate segment_id {segment_id} in {segments_path}")
            segments[segment_id] = {
                "start_frame_idx": int(row["start_frame_idx"]),
                "end_frame_idx": int(row["end_frame_idx"]),
            }

    order: list[tuple[int, int]] = []
    with order_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            order.append((int(row["order"]), int(row["segment_id"])))
    order.sort()
    if len(order) < 2:
        raise ValueError(f"Order must contain at least two segments: {order_path}")
    order_values = [row[0] for row in order]
    if order_values != list(range(len(order))):
        raise ValueError(
            f"Order values must be contiguous 0..{len(order) - 1}, got {order_values}"
        )
    segment_ids = [row[1] for row in order]
    if len(segment_ids) != len(set(segment_ids)):
        raise ValueError(f"Order contains duplicate segment IDs: {order_path}")
    missing = sorted(set(segment_ids) - set(segments))
    if missing:
        raise ValueError(f"Order references unknown segment IDs {missing}: {order_path}")
    omitted = sorted(set(segments) - set(segment_ids))
    if omitted:
        raise ValueError(f"Order omits segment IDs {omitted}: {order_path}")

    ranked: dict[tuple[int, int], dict[str, float | int]] = {}
    with ranked_edges_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            key = (int(row["from_segment_id"]), int(row["to_segment_id"]))
            ranked[key] = {
                "rank_for_from_segment": int(row["rank_for_from_segment"]),
                "mean_abs_diff": float(row["mean_abs_diff"]),
            }

    edges = []
    for from_segment_id, to_segment_id in zip(segment_ids, segment_ids[1:]):
        score = ranked.get((from_segment_id, to_segment_id), {})
        edges.append(
            {
                "from_segment_id": from_segment_id,
                "to_segment_id": to_segment_id,
                "from_end_frame_idx": segments[from_segment_id]["end_frame_idx"],
                "to_start_frame_idx": segments[to_segment_id]["start_frame_idx"],
                "rank_for_from_segment": score.get("rank_for_from_segment"),
                "mean_abs_diff": score.get("mean_abs_diff"),
            }
        )
    return edges if limit is None else edges[:limit]


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
    caption_height: int,
    caption_font_size: int,
    caption_image: Path | None = None,
) -> None:
    if caption_mode == "drawtext":
        safe_caption = ffmpeg_escape_text(caption)
        vf = (
            f"scale={scale_width}:-2,"
            f"pad=iw:ih+{caption_height}:0:{caption_height}:color=black,"
            f"drawtext=text='{safe_caption}':x=12:y=10:"
            f"fontcolor=white:fontsize={caption_font_size}"
        )
        inputs = ["-i", str(video)]
        output_options = ["-vf", vf]
    elif caption_mode == "pillow":
        if caption_image is None:
            raise ValueError("caption_image is required for pillow caption mode")
        inputs = ["-i", str(video), "-i", str(caption_image)]
        filter_complex = (
            f"[0:v]scale={scale_width}:-2,"
            f"pad=iw:ih+{caption_height}:0:{caption_height}:color=black[base];"
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


def make_caption_image(
    path: Path,
    caption: str,
    width: int,
    height: int,
    font_size: int,
) -> None:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 210))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    max_width = width - 24
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

    y = 8
    for line in lines:
        draw.text((12, y), line, fill=(255, 255, 255, 255), font=font)
        y += font_size + 4
    image.save(path)


def probe_scaled_height(video: Path, scale_width: int) -> int:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(video),
        ],
        text=True,
    ).strip()
    source_width, source_height = (int(value) for value in raw.split(","))
    height = round(scale_width * source_height / source_width)
    return height if height % 2 == 0 else height + 1


def make_separator_clip(out_path: Path, duration_s: float, width: int, height: int, color: str) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={width}x{height}:r=25:d={duration_s}",
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
        fieldnames = [
            "clip_index",
            "join_index",
            "side",
            "review_start_s",
            "review_stop_s",
            "caption",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    ranked_edges = args.ranked_edges.expanduser().resolve()
    out = args.out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if (args.order_csv is None) != (args.segments is None):
        raise ValueError("--order-csv and --segments must be provided together")
    if args.order_csv is not None:
        edges = read_order_edges(
            args.segments.expanduser().resolve(),
            args.order_csv.expanduser().resolve(),
            ranked_edges,
            args.limit,
        )
        review_mode = "exact order"
    else:
        edges = read_edges(
            ranked_edges,
            args.rank,
            20 if args.limit is None else args.limit,
        )
        review_mode = f"candidate rank {args.rank}"
    if not edges:
        raise RuntimeError(f"No joins found for {review_mode}.")
    if args.caption_height < 0:
        raise ValueError("--caption-height must be non-negative")
    if args.caption_font_size <= 0:
        raise ValueError("--caption-font-size must be positive")

    if args.caption_mode == "auto":
        caption_mode = "drawtext" if ffmpeg_has_filter("drawtext") else "pillow"
    else:
        caption_mode = args.caption_mode
    if caption_mode == "pillow":
        print("using Pillow-generated caption bars with ffmpeg overlay", flush=True)
    elif caption_mode == "none":
        print("caption overlay disabled; writing sidecar captions only", flush=True)

    caption_height = args.caption_height if caption_mode != "none" else 0
    review_height = probe_scaled_height(video, args.scale_width) + caption_height

    caption_rows = []
    with tempfile.TemporaryDirectory(prefix="join_review_") as tmpdir:
        tmp = Path(tmpdir)
        clips = []
        review_time = 0.0
        for join_index, edge in enumerate(edges, start=1):
            before_start = edge["from_end_frame_idx"] / args.fps - args.seconds_each_side
            after_start = edge["to_start_frame_idx"] / args.fps
            rank = edge.get("rank_for_from_segment")
            rank_text = str(rank) if rank is not None else "not-retained"
            difference = edge.get("mean_abs_diff")
            difference_text = f"{difference:.3f}" if difference is not None else "not-retained"
            shared = (
                f"join {join_index:03d} | rank {rank_text} | "
                f"S{edge['from_segment_id']} -> S{edge['to_segment_id']} | score {difference_text}"
            )
            before_caption = f"{shared} | before f{edge['from_end_frame_idx']}"
            after_caption = f"{shared} | after f{edge['to_start_frame_idx']}"
            before_clip = tmp / f"join_{join_index:03d}_before.mp4"
            separator_clip = tmp / f"join_{join_index:03d}_separator.mp4"
            after_clip = tmp / f"join_{join_index:03d}_after.mp4"
            before_caption_image = tmp / f"join_{join_index:03d}_before_caption.png"
            after_caption_image = tmp / f"join_{join_index:03d}_after_caption.png"
            print(f"rendering join {join_index}: {shared}", flush=True)
            if caption_mode == "pillow":
                make_caption_image(
                    before_caption_image,
                    before_caption,
                    args.scale_width,
                    caption_height,
                    args.caption_font_size,
                )
            make_clip(
                video,
                before_clip,
                before_start,
                args.seconds_each_side,
                before_caption,
                args.scale_width,
                caption_mode,
                caption_height,
                args.caption_font_size,
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
                review_height,
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
                make_caption_image(
                    after_caption_image,
                    after_caption,
                    args.scale_width,
                    caption_height,
                    args.caption_font_size,
                )
            make_clip(
                video,
                after_clip,
                after_start,
                args.seconds_each_side,
                after_caption,
                args.scale_width,
                caption_mode,
                caption_height,
                args.caption_font_size,
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
    print(f"review mode: {review_mode}")
    print(f"joins: {len(edges)}")
    print(f"wrote review video: {out}")
    print(f"wrote captions: {captions_path}")


if __name__ == "__main__":
    main()
