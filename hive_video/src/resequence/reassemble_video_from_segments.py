#!/usr/bin/env python3
"""Reassemble shuffled video segments into a review MP4 with frame/time captions."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2


INCOMPLETE_EXIT_CODE = 75


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reassemble video segments using ranked join edges. Writes a frame-accurate "
            "review MP4 with captions and a frame mapping CSV."
        )
    )
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--ranked-edges", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--order-csv",
        type=Path,
        default=None,
        help="Optional explicit order CSV with order and segment_id columns.",
    )
    parser.add_argument(
        "--require-complete-order",
        action="store_true",
        help="Require --order-csv to be a complete permutation of every segment.",
    )
    parser.add_argument(
        "--start-segment",
        type=int,
        default=0,
        help="Segment to start the reconstructed video with.",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=None,
        help="Optional cap for review/smoke runs.",
    )
    parser.add_argument(
        "--order-start",
        type=int,
        default=0,
        help="Start at this row of the inferred or explicit order.",
    )
    parser.add_argument(
        "--order-count",
        type=int,
        default=None,
        help="Number of ordered segments to render after --order-start.",
    )
    parser.add_argument(
        "--scale-width",
        type=int,
        default=824,
        help="Output width; height preserves source aspect and includes caption bar.",
    )
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument(
        "--caption-height",
        type=int,
        default=72,
        help="Top caption bar height in output pixels.",
    )
    parser.add_argument(
        "--caption-font-scale",
        type=float,
        default=0.56,
        help=(
            "OpenCV caption font scale. Default is about three quarters of the "
            "earlier caption size."
        ),
    )
    parser.add_argument(
        "--caption-thickness",
        type=int,
        default=1,
        help="OpenCV caption stroke thickness. Use 1 for less fuzzy text, 2 for heavier text.",
    )
    parser.add_argument(
        "--edge-rank-limit",
        type=int,
        default=10,
        help="Use ranked candidate edges up to this rank when selecting unused successors.",
    )
    parser.add_argument(
        "--segment-chunk-size",
        type=int,
        default=12,
        help=(
            "Number of ordered segments per restartable part file. Existing complete "
            "parts are skipped unless --overwrite is set."
        ),
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--safeword-file",
        type=Path,
        default=Path(".safeword"),
        help=(
            "Stop cleanly if this file contains 'sea cucumber' or 'seacucubmer' "
            "case-insensitively. Checked between segment chunks."
        ),
    )
    return parser.parse_args()


def seconds_to_mmss(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - 60 * minutes
    return f"{minutes:d}:{secs:06.3f}"


def read_segments(path: Path) -> dict[int, dict]:
    segments = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            segment_id = int(row["segment_id"])
            row["segment_id"] = segment_id
            row["start_frame_idx"] = int(row["start_frame_idx"])
            row["end_frame_idx"] = int(row["end_frame_idx"])
            row["duration_frames"] = int(row["duration_frames"])
            row["source_video"] = Path(row["source_video"])
            segments[segment_id] = row
    return segments


def read_edges(path: Path, rank_limit: int) -> dict[int, list[dict]]:
    by_from: dict[int, list[dict]] = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            rank = int(row["rank_for_from_segment"])
            if rank > rank_limit:
                continue
            edge = {
                "rank": rank,
                "from_segment_id": int(row["from_segment_id"]),
                "to_segment_id": int(row["to_segment_id"]),
                "mean_abs_diff": float(row["mean_abs_diff"]),
            }
            by_from.setdefault(edge["from_segment_id"], []).append(edge)
    for edges in by_from.values():
        edges.sort(key=lambda row: row["rank"])
    return by_from


def slice_order(
    rows: list[dict],
    order_start: int,
    order_count: int | None,
    max_segments: int | None,
) -> list[dict]:
    if order_start < 0:
        raise ValueError("--order-start must be non-negative")
    stop = None if order_count is None else order_start + order_count
    rows = rows[order_start:stop]
    if max_segments is not None:
        rows = rows[:max_segments]
    for idx, row in enumerate(rows):
        row.setdefault("source_order", row["order"])
        row.setdefault("source_previous_segment_id", row.get("previous_segment_id", ""))
        row["order"] = idx
        if idx == 0:
            row["previous_segment_id"] = ""
        else:
            row["previous_segment_id"] = rows[idx - 1]["segment_id"]
    return rows


def read_explicit_order(
    path: Path,
    segments: dict[int, dict],
    require_complete: bool,
    max_segments: int | None,
    order_start: int,
    order_count: int | None,
) -> list[dict]:
    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            rows.append(
                {
                    "order": int(row["order"]),
                    "source_order": int(row["order"]),
                    "segment_id": int(row["segment_id"]),
                    "previous_segment_id": "",
                    "join_rank": "",
                    "join_mean_abs_diff": row.get("join_cost_from_previous", ""),
                }
            )
    if not rows:
        raise ValueError(f"Explicit order is empty: {path}")
    order_values = [row["order"] for row in rows]
    if len(order_values) != len(set(order_values)):
        raise ValueError(f"Explicit order contains duplicate order values: {path}")
    rows.sort(key=lambda row: row["order"])
    sorted_order_values = [row["order"] for row in rows]
    expected_order_values = list(range(len(rows)))
    if sorted_order_values != expected_order_values:
        raise ValueError(
            f"Explicit order values must be contiguous {expected_order_values}; "
            f"got {sorted_order_values}"
        )
    segment_ids = [row["segment_id"] for row in rows]
    if len(segment_ids) != len(set(segment_ids)):
        raise ValueError(f"Explicit order contains duplicate segment IDs: {path}")
    unknown = sorted(set(segment_ids) - set(segments))
    if unknown:
        raise ValueError(f"Explicit order references unknown segment IDs {unknown}: {path}")
    if require_complete and set(segment_ids) != set(segments):
        missing = sorted(set(segments) - set(segment_ids))
        raise ValueError(
            f"Explicit order must contain every segment exactly once; missing {missing}: {path}"
        )
    for idx, row in enumerate(rows):
        row["source_previous_segment_id"] = "" if idx == 0 else rows[idx - 1]["segment_id"]
    return slice_order(rows, order_start, order_count, max_segments)


def infer_order(
    segments: dict[int, dict],
    edges_by_from: dict[int, list[dict]],
    start_segment: int,
    max_segments: int | None,
) -> list[dict]:
    used = {start_segment}
    order = [
        {
            "order": 0,
            "source_order": 0,
            "segment_id": start_segment,
            "previous_segment_id": "",
            "join_rank": "",
            "join_mean_abs_diff": "",
        }
    ]
    current = start_segment
    while len(used) < len(segments):
        if max_segments is not None and len(order) >= max_segments:
            break
        next_edge = None
        for edge in edges_by_from.get(current, []):
            if edge["to_segment_id"] not in used:
                next_edge = edge
                break
        if next_edge is None:
            # Start a new chain if the ranked edges only point to already-used segments.
            remaining = sorted(set(segments) - used)
            if not remaining:
                break
            next_segment = remaining[0]
            order.append(
                {
                    "order": len(order),
                    "source_order": len(order),
                    "segment_id": next_segment,
                    "previous_segment_id": "",
                    "join_rank": "",
                    "join_mean_abs_diff": "",
                }
            )
            used.add(next_segment)
            current = next_segment
            continue
        next_segment = next_edge["to_segment_id"]
        order.append(
            {
                "order": len(order),
                "source_order": len(order),
                "segment_id": next_segment,
                "previous_segment_id": current,
                "join_rank": next_edge["rank"],
                "join_mean_abs_diff": next_edge["mean_abs_diff"],
            }
        )
        used.add(next_segment)
        current = next_segment
    return order


def write_order(path: Path, rows: list[dict]) -> None:
    partial = path.with_suffix(f"{path.suffix}.partial")
    with partial.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "order",
                "source_order",
                "segment_id",
                "previous_segment_id",
                "source_previous_segment_id",
                "join_rank",
                "join_mean_abs_diff",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    partial.replace(path)


def safeword_triggered(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(errors="ignore").casefold()
    except OSError:
        return False
    return "sea cucumber" in text or "seacucubmer" in text


def chunk_order(rows: list[dict], chunk_size: int) -> list[list[dict]]:
    if chunk_size < 1:
        raise ValueError("--segment-chunk-size must be at least 1")
    return [rows[idx : idx + chunk_size] for idx in range(0, len(rows), chunk_size)]


def segment_output_frame_count(segment: dict) -> int:
    skip_frames = set(segment.get("skip_source_frame_indices", set()))
    return sum(
        1
        for source_frame_idx in range(segment["start_frame_idx"], segment["end_frame_idx"] + 1)
        if source_frame_idx not in skip_frames
    )


def write_parts_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(f"{path.suffix}.partial")
    with partial.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "part_index",
                "order_start",
                "order_end",
                "segment_count",
                "start_output_frame_idx",
                "output_frame_count",
                "part_video",
                "part_mapping_csv",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    partial.replace(path)


def draw_caption(frame, caption: str, caption_height: int, font_scale: float, thickness: int):
    height, width = frame.shape[:2]
    output = cv2.copyMakeBorder(
        frame,
        caption_height,
        0,
        0,
        0,
        cv2.BORDER_CONSTANT,
        value=(0, 0, 0),
    )
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = max(1, thickness)
    margin = 12
    scale = font_scale
    (text_width, text_height), baseline = cv2.getTextSize(caption, font, scale, thickness)
    max_width = max(1, width - 2 * margin)
    if text_width > max_width:
        scale *= max_width / text_width
        (text_width, text_height), baseline = cv2.getTextSize(caption, font, scale, thickness)
    x = max(margin, (width - text_width) // 2)
    y = max(text_height + margin, (caption_height + text_height) // 2 - baseline)
    cv2.putText(
        output,
        caption,
        (x, y),
        font,
        scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )
    return output


def write_frame_mapping_header(path: Path):
    f = path.open("w", newline="")
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "output_frame_idx",
            "output_time_s",
            "output_time_mmss",
            "segment_order",
            "source_order",
            "segment_id",
            "source_frame_idx",
            "source_time_s",
            "source_time_mmss",
        ],
    )
    writer.writeheader()
    return f, writer


def csv_data_row_count(path: Path) -> int:
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def video_frame_count(path: Path) -> int:
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return 0
        return int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        cap.release()


def artifacts_are_complete(video: Path, mapping: Path, expected_frames: int) -> bool:
    if not video.is_file() or not mapping.is_file():
        return False
    if video.stat().st_size <= 0 or mapping.stat().st_size <= 0:
        return False
    try:
        mapping_frames = csv_data_row_count(mapping)
    except (OSError, csv.Error):
        return False
    if mapping_frames != expected_frames:
        return False
    return video_frame_count(video) == expected_frames


def concat_part_videos(out: Path, part_rows: list[dict]) -> bool:
    ready = [Path(row["part_video"]) for row in part_rows if row["status"] == "done"]
    if len(ready) != len(part_rows):
        return False
    list_path = out.with_suffix(".concat_list.txt")
    with list_path.open("w") as f:
        for path in ready:
            escaped = str(path).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
    partial = out.with_name(f".{out.stem}.partial{out.suffix}")
    partial.unlink(missing_ok=True)
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
        str(list_path),
        "-c",
        "copy",
        str(partial),
    ]
    subprocess.run(cmd, check=True)
    partial.replace(out)
    return True


def combine_mapping_csvs(path: Path, part_rows: list[dict]) -> bool:
    done = [row for row in part_rows if row["status"] == "done"]
    if len(done) != len(part_rows):
        return False
    fieldnames = [
        "output_frame_idx",
        "output_time_s",
        "output_time_mmss",
        "segment_order",
        "source_order",
        "segment_id",
        "source_frame_idx",
        "source_time_s",
        "source_time_mmss",
    ]
    partial = path.with_suffix(f"{path.suffix}.partial")
    partial.unlink(missing_ok=True)
    with partial.open("w", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        writer.writeheader()
        for row in done:
            with Path(row["part_mapping_csv"]).open() as in_f:
                reader = csv.DictReader(in_f)
                for mapping_row in reader:
                    writer.writerow(mapping_row)
    partial.replace(path)
    return True


def write_metadata(
    path: Path,
    args: argparse.Namespace,
    source_video: Path,
    order_path: Path,
    mapping_path: Path,
    parts_manifest_path: Path,
    out: Path,
    safeword_file: Path,
    order: list[dict],
    part_rows: list[dict],
    stopped_by_safeword: bool,
    final_video_written: bool,
    final_mapping_written: bool,
    started_at: float,
) -> None:
    elapsed_s = time.monotonic() - started_at
    completed_parts = [row for row in part_rows if row["status"] == "done"]
    output_frame_count = sum(int(row["output_frame_count"]) for row in completed_parts)
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_video": str(source_video),
        "segments": str(args.segments.expanduser().resolve()),
        "ranked_edges": str(args.ranked_edges.expanduser().resolve()),
        "order_csv_input": (
            str(args.order_csv.expanduser().resolve())
            if args.order_csv is not None
            else None
        ),
        "out": str(out),
        "order_csv": str(order_path),
        "frame_mapping_csv": str(mapping_path),
        "parts_manifest_csv": str(parts_manifest_path),
        "start_segment": args.start_segment,
        "order_start": args.order_start,
        "order_count": args.order_count,
        "edge_rank_limit": args.edge_rank_limit,
        "segment_count": len(order),
        "part_count": len(part_rows),
        "completed_part_count": len(completed_parts),
        "output_frame_count": output_frame_count,
        "elapsed_wall_seconds": elapsed_s,
        "output_frames_per_wall_second": output_frame_count / elapsed_s if elapsed_s > 0 else None,
        "fps": args.fps,
        "scale_width": args.scale_width,
        "caption_height": args.caption_height,
        "caption_font_scale": args.caption_font_scale,
        "caption_thickness": args.caption_thickness,
        "segment_chunk_size": args.segment_chunk_size,
        "overwrite": args.overwrite,
        "safeword_file": str(safeword_file),
        "stopped_by_safeword": stopped_by_safeword,
        "final_video_written": final_video_written,
        "final_mapping_written": final_mapping_written,
    }
    partial = path.with_suffix(f"{path.suffix}.partial")
    partial.write_text(json.dumps(metadata, indent=2) + "\n")
    partial.replace(path)


def main() -> int:
    started_at = time.monotonic()
    args = parse_args()
    segments = read_segments(args.segments.expanduser().resolve())
    edges = read_edges(args.ranked_edges.expanduser().resolve(), args.edge_rank_limit)
    if args.order_csv is not None:
        order = read_explicit_order(
            args.order_csv.expanduser().resolve(),
            segments,
            args.require_complete_order,
            args.max_segments,
            args.order_start,
            args.order_count,
        )
    else:
        order = infer_order(segments, edges, args.start_segment, args.max_segments)
        order = slice_order(order, args.order_start, args.order_count, None)

    out = args.out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    order_path = out.with_suffix(".order.csv")
    mapping_path = out.with_suffix(".frame_mapping.csv")
    metadata_path = out.with_suffix(".metadata.json")
    parts_manifest_path = out.with_suffix(".parts_manifest.csv")
    parts_dir = out.with_suffix("")
    parts_dir = parts_dir.parent / f"{parts_dir.name}_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    write_order(order_path, order)
    safeword_file = args.safeword_file.expanduser()
    if not safeword_file.is_absolute():
        safeword_file = Path.cwd() / safeword_file

    source_video = next(iter(segments.values()))["source_video"]
    cap = cv2.VideoCapture(str(source_video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source video: {source_video}")
    source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    reported_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if reported_frame_count > 0:
        max_decodable_frame_idx = reported_frame_count - 2
        for segment in segments.values():
            if segment["end_frame_idx"] > max_decodable_frame_idx:
                skip_frames = set(segment.get("skip_source_frame_indices", set()))
                skip_frames.update(range(max_decodable_frame_idx + 1, segment["end_frame_idx"] + 1))
                segment["skip_source_frame_indices"] = skip_frames
                print(
                    f"warning: segment {segment['segment_id']} includes nominal terminal frames "
                    f"above decodable frame {max_decodable_frame_idx}; skipping "
                    f"{len(skip_frames)} frame(s)",
                    flush=True,
                )
    out_width = args.scale_width
    out_height = round(out_width * source_height / source_width)
    if out_height % 2:
        out_height += 1

    part_rows: list[dict] = []
    output_frame_idx = 0
    stopped_by_safeword = False
    part_chunks = chunk_order(order, args.segment_chunk_size)
    try:
        for part_index, part_order in enumerate(part_chunks):
            if safeword_triggered(safeword_file):
                print(f"safeword detected before part {part_index}; stopping cleanly", flush=True)
                stopped_by_safeword = True
                break

            part_frame_count = sum(
                segment_output_frame_count(segments[int(order_row["segment_id"])])
                for order_row in part_order
            )
            part_video = parts_dir / f"part_{part_index:04d}.mp4"
            part_mapping = parts_dir / f"part_{part_index:04d}.frame_mapping.csv"
            order_start = part_order[0]["order"]
            order_end = part_order[-1]["order"]
            status = "pending"

            if (
                not args.overwrite
                and artifacts_are_complete(part_video, part_mapping, part_frame_count)
            ):
                status = "done"
                print(
                    f"skipping validated part {part_index}: orders={order_start}-{order_end} "
                    f"frames={part_frame_count:,}",
                    flush=True,
                )
            else:
                if part_video.exists() or part_mapping.exists():
                    print(
                        f"existing part {part_index} is incomplete or unverified; rebuilding",
                        flush=True,
                    )
                print(
                    f"writing part {part_index}: orders={order_start}-{order_end} "
                    f"start_output_frame={output_frame_idx:,} frames={part_frame_count:,}",
                    flush=True,
                )
                partial_video = parts_dir / f".part_{part_index:04d}.partial.mp4"
                partial_mapping = (
                    parts_dir / f".part_{part_index:04d}.partial.frame_mapping.csv"
                )
                partial_video.unlink(missing_ok=True)
                partial_mapping.unlink(missing_ok=True)
                writer = cv2.VideoWriter(
                    str(partial_video),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    args.fps,
                    (out_width, out_height + args.caption_height),
                )
                if not writer.isOpened():
                    raise RuntimeError(
                        f"Could not open output video writer: {partial_video}"
                    )
                mapping_file, mapping_writer = write_frame_mapping_header(
                    partial_mapping
                )
                local_output_frame_idx = output_frame_idx
                try:
                    for order_row in part_order:
                        segment_order = order_row["order"]
                        source_order = order_row.get("source_order", segment_order)
                        segment_id = int(order_row["segment_id"])
                        segment = segments[segment_id]
                        print(
                            f"  segment order={segment_order} "
                            f"source_order={source_order} segment_id={segment_id} "
                            f"frames={segment['start_frame_idx']}-{segment['end_frame_idx']}",
                            flush=True,
                        )
                        source_frames = range(
                            segment["start_frame_idx"],
                            segment["end_frame_idx"] + 1,
                        )
                        for source_frame_idx in source_frames:
                            if source_frame_idx in segment.get("skip_source_frame_indices", set()):
                                print(
                                    f"    skipping unavailable source frame {source_frame_idx}",
                                    flush=True,
                                )
                                continue
                            if source_frame_idx == segment["start_frame_idx"]:
                                cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame_idx)
                            ok, frame = cap.read()
                            if not ok:
                                raise RuntimeError(
                                    f"Could not read source frame {source_frame_idx} "
                                    f"while writing part {part_index}"
                                )
                            frame = cv2.resize(
                                frame,
                                (out_width, out_height),
                                interpolation=cv2.INTER_AREA,
                            )
                            output_time_s = local_output_frame_idx / args.fps
                            source_time_s = source_frame_idx / args.fps
                            caption = (
                                f"current_frame={local_output_frame_idx} "
                                f"current={seconds_to_mmss(output_time_s)} "
                                f"source_frame={source_frame_idx} "
                                f"source={seconds_to_mmss(source_time_s)} "
                                f"segment={segment_id} order={segment_order} "
                                f"source_order={source_order}"
                            )
                            writer.write(
                                draw_caption(
                                    frame,
                                    caption,
                                    args.caption_height,
                                    args.caption_font_scale,
                                    args.caption_thickness,
                                )
                            )
                            mapping_writer.writerow(
                                {
                                    "output_frame_idx": local_output_frame_idx,
                                    "output_time_s": f"{output_time_s:.6f}",
                                    "output_time_mmss": seconds_to_mmss(output_time_s),
                                    "segment_order": segment_order,
                                    "source_order": source_order,
                                    "segment_id": segment_id,
                                    "source_frame_idx": source_frame_idx,
                                    "source_time_s": f"{source_time_s:.6f}",
                                    "source_time_mmss": seconds_to_mmss(source_time_s),
                                }
                            )
                            local_output_frame_idx += 1
                finally:
                    mapping_file.close()
                    writer.release()
                written_frames = local_output_frame_idx - output_frame_idx
                if written_frames != part_frame_count:
                    raise RuntimeError(
                        f"Part {part_index} wrote {written_frames} frames; "
                        f"expected {part_frame_count}"
                    )
                if not artifacts_are_complete(
                    partial_video, partial_mapping, part_frame_count
                ):
                    raise RuntimeError(
                        f"Part {part_index} failed post-write validation: "
                        f"{partial_video}, {partial_mapping}"
                    )
                partial_video.replace(part_video)
                partial_mapping.replace(part_mapping)
                status = "done"

            part_rows.append(
                {
                    "part_index": part_index,
                    "order_start": order_start,
                    "order_end": order_end,
                    "segment_count": len(part_order),
                    "start_output_frame_idx": output_frame_idx,
                    "output_frame_count": part_frame_count,
                    "part_video": str(part_video),
                    "part_mapping_csv": str(part_mapping),
                    "status": status,
                }
            )
            write_parts_manifest(parts_manifest_path, part_rows)
            output_frame_idx += part_frame_count

            if safeword_triggered(safeword_file):
                print(f"safeword detected after part {part_index}; stopping cleanly", flush=True)
                stopped_by_safeword = True
                break
    finally:
        cap.release()

    all_parts_done = len(part_rows) == len(part_chunks) and all(
        row["status"] == "done" for row in part_rows
    )
    final_video_written = False
    final_mapping_written = False
    if all_parts_done:
        expected_output_frames = sum(
            int(row["output_frame_count"]) for row in part_rows
        )
        if (
            not args.overwrite
            and artifacts_are_complete(out, mapping_path, expected_output_frames)
        ):
            final_video_written = True
            final_mapping_written = True
            print(f"skipping validated final artifacts: {out}", flush=True)
        else:
            if out.exists() or mapping_path.exists():
                print("existing final artifacts are incomplete or unverified; rebuilding")
            print(f"concatenating final video: {out}", flush=True)
            final_video_written = concat_part_videos(out, part_rows)
            final_mapping_written = combine_mapping_csvs(mapping_path, part_rows)
            if not artifacts_are_complete(
                out, mapping_path, expected_output_frames
            ):
                raise RuntimeError(
                    f"Final artifacts failed validation: {out}, {mapping_path}"
                )
    else:
        print("not all parts are complete; final concat deferred until restart", flush=True)

    write_metadata(
        metadata_path,
        args,
        source_video,
        order_path,
        mapping_path,
        parts_manifest_path,
        out,
        safeword_file,
        order,
        part_rows,
        stopped_by_safeword,
        final_video_written,
        final_mapping_written,
        started_at,
    )
    if final_video_written:
        print(f"wrote video: {out}")
    else:
        print(f"video not finalized yet: {out}")
    print(f"wrote order: {order_path}")
    print(f"wrote mapping: {mapping_path}")
    print(f"wrote parts manifest: {parts_manifest_path}")
    print(f"wrote metadata: {metadata_path}")
    elapsed_s = time.monotonic() - started_at
    print(f"elapsed wall time: {elapsed_s:.2f}s")
    if elapsed_s > 0:
        print(f"output frames per wall second: {output_frame_idx / elapsed_s:.2f}")
    if not (final_video_written and final_mapping_written):
        print(
            f"reassembly incomplete; exit code {INCOMPLETE_EXIT_CODE} prevents dependent upload",
            flush=True,
        )
        return INCOMPLETE_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
