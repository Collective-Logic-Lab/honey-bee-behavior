#!/usr/bin/env python3
"""Automatically triage reconstructed segment joins using detector-scale frames.

This diagnostic scores the exact one-frame boundary emitted by the reassembler.
It deliberately calls the result a deterministic QC decision, not a probability
or confidence estimate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2

try:
    from src.resequence import detect_video_discontinuities as detector
except ModuleNotFoundError:  # Support direct execution by file path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from src.resequence import detect_video_discontinuities as detector


METHOD_NAME = "detector_gray_one_frame_segment_join_qc"
METHOD_VERSION = "1.0"
JOIN_SCORES_NAME = "auto_qc.join_scores.csv"
FLAGGED_JOINS_NAME = "auto_qc.flagged_joins.csv"
SUMMARY_NAME = "auto_qc.summary.json"
MAD_NORMAL_SCALE = 1.4826

JOIN_SCORE_FIELDS = [
    "join_index",
    "join_order",
    "from_segment_id",
    "to_segment_id",
    "from_nominal_end_frame_idx",
    "from_actual_end_frame_idx",
    "to_start_frame_idx",
    "reported_source_frame_count",
    "possible_successor_count",
    "scored_successor_count",
    "selected_mean_abs_diff",
    "selected_rank",
    "runner_up_segment_id",
    "runner_up_mean_abs_diff",
    "margin_ratio",
    "margin_ratio_unbounded",
    "robust_z",
    "scoreable",
    "decision",
    "reasons",
]


@dataclass(frozen=True)
class Segment:
    """One inclusive source-frame segment."""

    segment_id: int
    source_video: Path | None
    start_frame_idx: int
    end_frame_idx: int
    duration_frames: int


@dataclass(frozen=True)
class DetectorMetadata:
    comparison_width: int
    comparison_height: int
    distance_median: float
    distance_mad: float


@dataclass(frozen=True)
class JoinScore:
    join_order: int
    from_segment_id: int
    to_segment_id: int
    from_nominal_end_frame_idx: int
    from_actual_end_frame_idx: int
    to_start_frame_idx: int
    reported_source_frame_count: int
    possible_successor_count: int
    scored_successor_count: int
    selected_mean_abs_diff: float | None
    selected_rank: int | None
    runner_up_segment_id: int | None
    runner_up_mean_abs_diff: float | None
    margin_ratio: float | None
    margin_ratio_unbounded: bool
    robust_z: float | None
    scoreable: bool
    decision: str
    reasons: tuple[str, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score each selected segment join at the discontinuity detector's grayscale "
            "resolution and flag joins that need manual review."
        )
    )
    parser.add_argument("video", type=Path, help="Source video used to build the segments.")
    parser.add_argument("--segments", type=Path, required=True, help="Inclusive segments CSV.")
    parser.add_argument(
        "--order-csv",
        type=Path,
        required=True,
        help="Complete explicit order CSV with contiguous order and segment_id columns.",
    )
    parser.add_argument(
        "--detector-metadata",
        type=Path,
        required=True,
        help="metadata.json written by detect_video_discontinuities.py.",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--max-robust-z",
        type=float,
        default=15.0,
        help=(
            "Maximum join distance in detector MAD units: "
            "(distance - median) / (1.4826 * MAD)."
        ),
    )
    parser.add_argument(
        "--min-margin-ratio",
        type=float,
        default=2.0,
        help=(
            "Minimum runner-up distance divided by selected distance. "
            "Larger values indicate a more distinct selected successor."
        ),
    )
    parser.add_argument(
        "--require-rank1",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require the selected successor to be the closest one-frame candidate.",
    )
    parser.add_argument(
        "--progress-every-frames",
        type=int,
        default=5_000,
        help="Print decode progress after this many frames; use 0 to disable.",
    )
    parser.add_argument(
        "--progress-every-seconds",
        type=float,
        default=10.0,
        help="Print decode progress after this many wall-clock seconds; use 0 to disable.",
    )
    return parser.parse_args(argv)


def require_input_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file: {resolved}")
    if resolved.stat().st_size <= 0:
        raise ValueError(f"{label} is empty: {resolved}")
    return resolved


def _required_csv_columns(
    reader: csv.DictReader, required: set[str], path: Path, label: str
) -> None:
    columns = set(reader.fieldnames or [])
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"{label} is missing required columns {missing}: {path}")


def _strict_int(value: Any, field: str, path: Path, row_number: int) -> int:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"Missing {field} in row {row_number} of {path}")
    try:
        parsed = int(text)
    except ValueError as exc:
        raise ValueError(
            f"Invalid integer {field}={text!r} in row {row_number} of {path}"
        ) from exc
    return parsed


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except (FileNotFoundError, OSError):
        return left.resolve() == right.resolve()


def load_segments(path: Path, source_video: Path) -> dict[int, Segment]:
    """Read and validate a contiguous partition of inclusive source-frame ranges."""

    segments: dict[int, Segment] = {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        _required_csv_columns(
            reader,
            {"segment_id", "start_frame_idx", "end_frame_idx"},
            path,
            "Segments CSV",
        )
        has_source_video = "source_video" in (reader.fieldnames or [])
        has_duration_frames = "duration_frames" in (reader.fieldnames or [])
        for row_number, row in enumerate(reader, start=2):
            segment_id = _strict_int(row.get("segment_id"), "segment_id", path, row_number)
            start = _strict_int(
                row.get("start_frame_idx"), "start_frame_idx", path, row_number
            )
            end = _strict_int(row.get("end_frame_idx"), "end_frame_idx", path, row_number)
            if segment_id in segments:
                raise ValueError(f"Duplicate segment_id {segment_id} in {path}")
            if start < 0:
                raise ValueError(
                    f"Segment {segment_id} has negative start_frame_idx {start}: {path}"
                )
            if end < start:
                raise ValueError(
                    f"Segment {segment_id} has end_frame_idx {end} before start {start}: {path}"
                )
            duration = end - start + 1
            if has_duration_frames:
                declared_duration = _strict_int(
                    row.get("duration_frames"), "duration_frames", path, row_number
                )
                if declared_duration != duration:
                    raise ValueError(
                        f"Segment {segment_id} duration_frames={declared_duration}, "
                        f"but inclusive range {start}-{end} contains {duration} frames: {path}"
                    )
            row_source: Path | None = None
            if has_source_video:
                source_text = str(row.get("source_video") or "").strip()
                if not source_text:
                    raise ValueError(f"Missing source_video in row {row_number} of {path}")
                row_source = Path(source_text).expanduser().resolve()
                if not _same_path(row_source, source_video):
                    raise ValueError(
                        f"Segment {segment_id} source_video {row_source} does not match "
                        f"CLI source video {source_video}"
                    )
            segments[segment_id] = Segment(
                segment_id=segment_id,
                source_video=row_source,
                start_frame_idx=start,
                end_frame_idx=end,
                duration_frames=duration,
            )

    if not segments:
        raise ValueError(f"Segments CSV has no data rows: {path}")

    by_start = sorted(segments.values(), key=lambda segment: segment.start_frame_idx)
    if by_start[0].start_frame_idx != 0:
        raise ValueError(
            f"Inclusive segments must begin at source frame 0; first start is "
            f"{by_start[0].start_frame_idx}: {path}"
        )
    for previous, current in zip(by_start, by_start[1:], strict=False):
        expected_start = previous.end_frame_idx + 1
        if current.start_frame_idx != expected_start:
            relationship = "overlap" if current.start_frame_idx < expected_start else "gap"
            raise ValueError(
                f"Inclusive segments have a {relationship}: segment {previous.segment_id} "
                f"ends at {previous.end_frame_idx}, but segment {current.segment_id} starts "
                f"at {current.start_frame_idx}: {path}"
            )
    return segments


def load_complete_order(path: Path, segments: Mapping[int, Segment]) -> list[int]:
    """Read a complete permutation whose explicit order values are 0..N-1."""

    parsed: list[tuple[int, int]] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        _required_csv_columns(reader, {"order", "segment_id"}, path, "Order CSV")
        for row_number, row in enumerate(reader, start=2):
            parsed.append(
                (
                    _strict_int(row.get("order"), "order", path, row_number),
                    _strict_int(row.get("segment_id"), "segment_id", path, row_number),
                )
            )
    if not parsed:
        raise ValueError(f"Order CSV has no data rows: {path}")

    order_values = [order_value for order_value, _ in parsed]
    if len(order_values) != len(set(order_values)):
        raise ValueError(f"Order CSV contains duplicate order values: {path}")
    parsed.sort()
    expected_values = list(range(len(parsed)))
    actual_values = [order_value for order_value, _ in parsed]
    if actual_values != expected_values:
        raise ValueError(
            f"Order values must be contiguous {expected_values}; got {actual_values}: {path}"
        )

    segment_ids = [segment_id for _, segment_id in parsed]
    if len(segment_ids) != len(set(segment_ids)):
        raise ValueError(f"Order CSV contains duplicate segment IDs: {path}")
    expected_segments = set(segments)
    actual_segments = set(segment_ids)
    if actual_segments != expected_segments:
        missing = sorted(expected_segments - actual_segments)
        unknown = sorted(actual_segments - expected_segments)
        raise ValueError(
            f"Order CSV must contain every segment exactly once; missing={missing}, "
            f"unknown={unknown}: {path}"
        )
    return segment_ids


def _finite_number(value: Any, field: str, path: Path) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Detector metadata {field} must be numeric, not boolean: {path}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Detector metadata {field} is not numeric: {path}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"Detector metadata {field} must be finite: {path}")
    return parsed


def _positive_int_metadata(value: Any, field: str, path: Path) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Detector metadata {field} must be an integer: {path}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Detector metadata {field} must be an integer: {path}") from exc
    if parsed <= 0 or float(value) != parsed:
        raise ValueError(f"Detector metadata {field} must be a positive integer: {path}")
    return parsed


def load_detector_metadata(path: Path) -> DetectorMetadata:
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Detector metadata is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Detector metadata must be a JSON object: {path}")
    required = {
        "comparison_width",
        "comparison_height",
        "distance_median",
        "distance_mad",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError(f"Detector metadata is missing fields {missing}: {path}")

    width = _positive_int_metadata(raw["comparison_width"], "comparison_width", path)
    height = _positive_int_metadata(raw["comparison_height"], "comparison_height", path)
    median = _finite_number(raw["distance_median"], "distance_median", path)
    mad = _finite_number(raw["distance_mad"], "distance_mad", path)
    if not 0.0 <= median <= 255.0:
        raise ValueError(f"Detector distance_median must be between 0 and 255: {path}")
    if not 0.0 <= mad <= 255.0:
        raise ValueError(
            f"Detector distance_mad must be between zero and 255; got {mad}: {path}"
        )
    return DetectorMetadata(
        comparison_width=width,
        comparison_height=height,
        distance_median=median,
        distance_mad=mad,
    )


def opencv_reported_frame_count(video: Path) -> int:
    cap = cv2.VideoCapture(str(video))
    try:
        if not cap.isOpened():
            raise RuntimeError(f"OpenCV could not open source video: {video}")
        return int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        cap.release()


def actual_segment_end(segment: Segment, reported_frame_count: int) -> int:
    """Mirror the reassembler's omission of the nominal terminal OpenCV frame."""

    if reported_frame_count > 0:
        return min(segment.end_frame_idx, reported_frame_count - 2)
    return segment.end_frame_idx


def required_frame_indices(
    segments: Mapping[int, Segment],
    order: Sequence[int],
    reported_frame_count: int,
) -> set[int]:
    needed = {segment.start_frame_idx for segment in segments.values()}
    for segment_id in order[:-1]:
        endpoint = actual_segment_end(segments[segment_id], reported_frame_count)
        if endpoint >= 0:
            needed.add(endpoint)
    return needed


def retain_detector_frames(
    video: Path,
    width: int,
    height: int,
    needed_indices: set[int],
    info: detector.VideoInfo,
    progress_every_frames: int,
    progress_every_seconds: float,
) -> dict[int, bytes]:
    """Decode sequentially and retain only segment starts and selected-source ends."""

    if not needed_indices:
        return {}
    if min(needed_indices) < 0:
        raise ValueError(f"Required source frame indices must be non-negative: {needed_indices}")

    retained: dict[int, bytes] = {}
    maximum = max(needed_indices)
    started_at = time.monotonic()
    last_progress_frame = 0
    last_progress_at = started_at
    last_idx: int | None = None
    for idx, frame in enumerate(
        detector.stream_gray_frames(video, width, height, max_frames=maximum + 1)
    ):
        last_idx = idx
        if idx in needed_indices:
            retained[idx] = frame
        now = time.monotonic()
        frame_due = progress_every_frames > 0 and idx - last_progress_frame >= progress_every_frames
        time_due = (
            progress_every_seconds > 0 and now - last_progress_at >= progress_every_seconds
        )
        if idx and (frame_due or time_due):
            detector.print_progress(idx, info, started_at)
            last_progress_frame = idx
            last_progress_at = now

    if last_idx is not None:
        estimated_frames = (
            round(info.duration_s * info.fps)
            if info.duration_s is not None and info.fps > 0
            else None
        )
        decoded_source_end = (
            estimated_frames is not None and last_idx + 1 >= estimated_frames
        )
        detector.print_progress(
            last_idx,
            info,
            started_at,
            finished=decoded_source_end,
        )
        if not decoded_source_end:
            print(
                f"endpoint decode complete at highest required frame {maximum:,}",
                flush=True,
            )
    missing = sorted(needed_indices - set(retained))
    if missing:
        print(
            f"warning: decoder did not yield {len(missing)} required frame(s); "
            f"first missing indices: {missing[:10]}",
            flush=True,
        )
    print(
        f"retained {len(retained)}/{len(needed_indices)} detector-scale endpoint frame(s)",
        flush=True,
    )
    return retained


def robust_z(distance: float, metadata: DetectorMetadata) -> float | None:
    if metadata.distance_mad <= 0.0:
        return None
    return (distance - metadata.distance_median) / (MAD_NORMAL_SCALE * metadata.distance_mad)


def _margin_ratio(selected: float, runner_up: float | None) -> tuple[float, bool]:
    if runner_up is None:
        return math.inf, True
    if selected == 0.0:
        if runner_up > 0.0:
            return math.inf, True
        return 1.0, False
    return runner_up / selected, False


def score_joins(
    segments: Mapping[int, Segment],
    order: Sequence[int],
    retained_frames: Mapping[int, bytes],
    metadata: DetectorMetadata,
    reported_frame_count: int,
    max_robust_z: float,
    min_margin_ratio: float,
    require_rank1: bool,
) -> list[JoinScore]:
    """Score each selected successor against the segment starts still available."""

    scores: list[JoinScore] = []
    for join_order, (from_id, selected_id) in enumerate(
        zip(order, order[1:], strict=False)
    ):
        from_segment = segments[from_id]
        selected_segment = segments[selected_id]
        endpoint_idx = actual_segment_end(from_segment, reported_frame_count)
        from_segment_emits_frames = endpoint_idx >= from_segment.start_frame_idx
        endpoint_frame = (
            retained_frames.get(endpoint_idx) if from_segment_emits_frames else None
        )

        candidates: list[tuple[float, int]] = []
        used_segment_ids = set(order[: join_order + 1])
        available_successors = [
            segments[segment_id]
            for segment_id in order
            if segment_id not in used_segment_ids
        ]
        if endpoint_frame is not None:
            for candidate in available_successors:
                candidate_end = actual_segment_end(candidate, reported_frame_count)
                if candidate.start_frame_idx > candidate_end:
                    continue
                start_frame = retained_frames.get(candidate.start_frame_idx)
                if start_frame is not None:
                    candidates.append(
                        (
                            detector.mean_abs_diff(endpoint_frame, start_frame),
                            candidate.segment_id,
                        )
                    )

        possible_successors = len(available_successors)
        complete_candidates = len(candidates) == possible_successors
        by_id = {segment_id: distance for distance, segment_id in candidates}
        selected_distance = by_id.get(selected_id)
        selected_rank: int | None = None
        runner_up_id: int | None = None
        runner_up_distance: float | None = None
        margin_ratio: float | None = None
        margin_unbounded = False
        join_robust_z: float | None = None
        reasons: list[str] = []

        if not from_segment_emits_frames:
            reasons.append("from_segment_emits_no_frames")
        elif endpoint_frame is None:
            reasons.append("missing_from_actual_end_frame")
        selected_actual_end = actual_segment_end(selected_segment, reported_frame_count)
        if selected_segment.start_frame_idx > selected_actual_end:
            reasons.append("selected_segment_emits_no_frames")
        elif retained_frames.get(selected_segment.start_frame_idx) is None:
            reasons.append("missing_selected_start_frame")
        if not complete_candidates:
            reasons.append("incomplete_successor_candidate_scores")

        scoreable = (
            endpoint_frame is not None
            and selected_distance is not None
            and complete_candidates
        )
        if scoreable:
            ranked = sorted(candidates, key=lambda item: (item[0], item[1]))
            selected_rank = next(
                rank
                for rank, (_, candidate_id) in enumerate(ranked, start=1)
                if candidate_id == selected_id
            )
            runner_ups = [item for item in ranked if item[1] != selected_id]
            if runner_ups:
                runner_up_distance, runner_up_id = runner_ups[0]
            margin_ratio, margin_unbounded = _margin_ratio(
                selected_distance, runner_up_distance
            )
            join_robust_z = robust_z(selected_distance, metadata)

            if require_rank1 and selected_rank != 1:
                reasons.append("selected_successor_not_rank1")
            if join_robust_z is None:
                reasons.append("detector_mad_not_positive")
            elif join_robust_z > max_robust_z:
                reasons.append("robust_z_above_max")
            if margin_ratio < min_margin_ratio:
                reasons.append("margin_ratio_below_min")

        decision = "auto_pass" if not reasons else "manual_review_required"
        scores.append(
            JoinScore(
                join_order=join_order,
                from_segment_id=from_id,
                to_segment_id=selected_id,
                from_nominal_end_frame_idx=from_segment.end_frame_idx,
                from_actual_end_frame_idx=endpoint_idx,
                to_start_frame_idx=selected_segment.start_frame_idx,
                reported_source_frame_count=reported_frame_count,
                possible_successor_count=possible_successors,
                scored_successor_count=len(candidates),
                selected_mean_abs_diff=selected_distance,
                selected_rank=selected_rank,
                runner_up_segment_id=runner_up_id,
                runner_up_mean_abs_diff=runner_up_distance,
                margin_ratio=margin_ratio,
                margin_ratio_unbounded=margin_unbounded,
                robust_z=join_robust_z,
                scoreable=scoreable,
                decision=decision,
                reasons=tuple(reasons),
            )
        )
    return scores


def _format_float(value: float | None) -> str:
    if value is None:
        return ""
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.6f}"


def join_score_csv_row(score: JoinScore) -> dict[str, Any]:
    return {
        "join_index": score.join_order + 1,
        "join_order": score.join_order,
        "from_segment_id": score.from_segment_id,
        "to_segment_id": score.to_segment_id,
        "from_nominal_end_frame_idx": score.from_nominal_end_frame_idx,
        "from_actual_end_frame_idx": score.from_actual_end_frame_idx,
        "to_start_frame_idx": score.to_start_frame_idx,
        "reported_source_frame_count": score.reported_source_frame_count,
        "possible_successor_count": score.possible_successor_count,
        "scored_successor_count": score.scored_successor_count,
        "selected_mean_abs_diff": _format_float(score.selected_mean_abs_diff),
        "selected_rank": "" if score.selected_rank is None else score.selected_rank,
        "runner_up_segment_id": (
            "" if score.runner_up_segment_id is None else score.runner_up_segment_id
        ),
        "runner_up_mean_abs_diff": _format_float(score.runner_up_mean_abs_diff),
        "margin_ratio": _format_float(score.margin_ratio),
        "margin_ratio_unbounded": str(score.margin_ratio_unbounded).lower(),
        "robust_z": _format_float(score.robust_z),
        "scoreable": str(score.scoreable).lower(),
        "decision": score.decision,
        "reasons": ";".join(score.reasons),
    }


def write_csv_atomically(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".partial"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=JOIN_SCORE_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def input_fingerprint(path: Path, *, hash_contents: bool = True) -> dict[str, Any]:
    stat = path.stat()
    fingerprint = {
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "identity": "sha256_size_mtime" if hash_contents else "size_mtime",
    }
    if hash_contents:
        fingerprint["sha256"] = sha256_file(path)
    return fingerprint


def validate_summary_inputs(
    summary_path: Path,
    video: Path,
    segments_path: Path,
    order_path: Path,
    detector_metadata_path: Path,
) -> tuple[bool, str]:
    """Confirm that a saved decision covers the exact current pipeline inputs."""

    try:
        summary_path = require_input_file(summary_path, "Auto-QC summary")
        resolved = {
            "video": require_input_file(video, "Source video"),
            "segments": require_input_file(segments_path, "Segments CSV"),
            "order_csv": require_input_file(order_path, "Order CSV"),
            "detector_metadata": require_input_file(
                detector_metadata_path,
                "Detector metadata",
            ),
        }
        summary = json.loads(summary_path.read_text())
        expected_inputs = summary["inputs"]
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
        return False, f"Could not validate auto-QC inputs: {error}"
    if not isinstance(expected_inputs, dict):
        return False, "Could not validate auto-QC inputs: inputs is not a JSON object"

    failures: list[str] = []
    for name, path in resolved.items():
        expected = expected_inputs.get(name)
        if not isinstance(expected, dict):
            failures.append(f"{name}: missing fingerprint")
            continue
        if expected.get("path") != str(path):
            failures.append(f"{name}: path changed")
            continue
        try:
            current = input_fingerprint(path, hash_contents=name != "video")
        except OSError as error:
            failures.append(f"{name}: could not fingerprint current file ({error})")
            continue
        if current["size_bytes"] != expected.get("size_bytes"):
            failures.append(f"{name}: size changed")
            continue
        if name == "video":
            if current["mtime_ns"] != expected.get("mtime_ns"):
                failures.append("video: modification time changed")
        elif current.get("sha256") != expected.get("sha256"):
            failures.append(f"{name}: content hash changed")

    if failures:
        return False, "Auto-QC report does not cover current inputs: " + "; ".join(failures)
    return True, "Auto-QC report input fingerprints match the current pipeline inputs."


def _finite_or_none(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return value


def join_score_summary(score: JoinScore) -> dict[str, Any]:
    return {
        "join_index": score.join_order + 1,
        "join_order": score.join_order,
        "from_segment_id": score.from_segment_id,
        "to_segment_id": score.to_segment_id,
        "from_nominal_end_frame_idx": score.from_nominal_end_frame_idx,
        "from_actual_end_frame_idx": score.from_actual_end_frame_idx,
        "to_start_frame_idx": score.to_start_frame_idx,
        "selected_mean_abs_diff": _finite_or_none(score.selected_mean_abs_diff),
        "selected_rank": score.selected_rank,
        "runner_up_segment_id": score.runner_up_segment_id,
        "runner_up_mean_abs_diff": _finite_or_none(score.runner_up_mean_abs_diff),
        "margin_ratio": _finite_or_none(score.margin_ratio),
        "margin_ratio_unbounded": score.margin_ratio_unbounded,
        "robust_z": _finite_or_none(score.robust_z),
        "scoreable": score.scoreable,
        "decision": score.decision,
        "reasons": list(score.reasons),
    }


def choose_worst_join(scores: Sequence[JoinScore]) -> JoinScore | None:
    if not scores:
        return None
    flagged = [score for score in scores if score.decision != "auto_pass"]
    if not flagged:
        return max(
            scores,
            key=lambda score: (
                score.robust_z if score.robust_z is not None else -math.inf,
                score.selected_rank if score.selected_rank is not None else 0,
                score.join_order,
            ),
        )

    def flagged_severity(score: JoinScore) -> tuple[float, ...]:
        robust_value = score.robust_z if score.robust_z is not None else math.inf
        rank_value = float(score.selected_rank) if score.selected_rank is not None else math.inf
        if score.margin_ratio is None:
            inverse_margin = math.inf
        elif math.isinf(score.margin_ratio):
            inverse_margin = 0.0
        else:
            inverse_margin = -score.margin_ratio
        return (
            float(not score.scoreable),
            float(len(score.reasons)),
            robust_value,
            rank_value,
            inverse_margin,
            float(score.join_order),
        )

    return max(flagged, key=flagged_severity)


def build_summary(
    *,
    video: Path,
    segments_path: Path,
    order_path: Path,
    detector_metadata_path: Path,
    fingerprints: Mapping[str, Mapping[str, Any]],
    segments: Mapping[int, Segment],
    scores: Sequence[JoinScore],
    metadata: DetectorMetadata,
    reported_frame_count: int,
    max_robust_z: float,
    min_margin_ratio: float,
    require_rank1: bool,
) -> dict[str, Any]:
    flagged = [score for score in scores if score.decision != "auto_pass"]
    reason_counts = Counter(reason for score in flagged for reason in score.reasons)
    decision = "auto_pass" if not flagged and len(scores) == len(segments) - 1 else (
        "manual_review_required"
    )
    worst = choose_worst_join(scores)
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": METHOD_NAME,
        "method_version": METHOD_VERSION,
        "method_description": (
            "Sequential ffmpeg decode at the discontinuity detector's grayscale dimensions; "
            "each emitted source-segment endpoint is compared directly with every still-unused "
            "segment start available at that ordering step. The selected successor is gated by "
            "robust detector distance, successor rank, and runner-up margin."
        ),
        "settings": {
            "max_robust_z": max_robust_z,
            "min_margin_ratio": min_margin_ratio,
            "require_rank1": require_rank1,
            "mad_normal_scale": MAD_NORMAL_SCALE,
            "comparison_width": metadata.comparison_width,
            "comparison_height": metadata.comparison_height,
            "detector_distance_median": metadata.distance_median,
            "detector_distance_mad": metadata.distance_mad,
            "opencv_reported_frame_count": reported_frame_count,
            "terminal_frame_rule": (
                "when OpenCV frame count is positive, actual segment end is "
                "min(nominal end, reported frame count - 2)"
            ),
        },
        "inputs": {
            "video": fingerprints["video"],
            "segments": fingerprints["segments"],
            "order_csv": fingerprints["order_csv"],
            "detector_metadata": fingerprints["detector_metadata"],
        },
        "paths": {
            "video": str(video),
            "segments": str(segments_path),
            "order_csv": str(order_path),
            "detector_metadata": str(detector_metadata_path),
        },
        "counts": {
            "segments": len(segments),
            "joins_expected": max(0, len(segments) - 1),
            "joins_scored": sum(score.scoreable for score in scores),
            "joins_flagged": len(flagged),
            "joins_auto_passed": sum(score.decision == "auto_pass" for score in scores),
        },
        "worst_join": join_score_summary(worst) if worst is not None else None,
        "decision": decision,
        "reasons": sorted(reason_counts),
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def write_json_atomically(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".partial"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_settings(args: argparse.Namespace) -> None:
    if not math.isfinite(args.max_robust_z):
        raise ValueError("--max-robust-z must be finite")
    if not math.isfinite(args.min_margin_ratio) or args.min_margin_ratio <= 0:
        raise ValueError("--min-margin-ratio must be finite and greater than zero")
    if args.progress_every_frames < 0:
        raise ValueError("--progress-every-frames must be non-negative")
    if not math.isfinite(args.progress_every_seconds) or args.progress_every_seconds < 0:
        raise ValueError("--progress-every-seconds must be finite and non-negative")


def run(args: argparse.Namespace) -> dict[str, Any]:
    validate_settings(args)
    video = require_input_file(args.video, "Source video")
    segments_path = require_input_file(args.segments, "Segments CSV")
    order_path = require_input_file(args.order_csv, "Order CSV")
    metadata_path = require_input_file(args.detector_metadata, "Detector metadata")
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata = load_detector_metadata(metadata_path)
    segments = load_segments(segments_path, video)
    order = load_complete_order(order_path, segments)
    info = detector.probe_video(video)
    expected_width, expected_height = detector.comparison_size(
        info, metadata.comparison_width
    )
    if (metadata.comparison_width, metadata.comparison_height) != (
        expected_width,
        expected_height,
    ):
        raise ValueError(
            "Detector comparison dimensions do not match the source aspect ratio: "
            f"metadata={metadata.comparison_width}x{metadata.comparison_height}, "
            f"expected={expected_width}x{expected_height}"
        )

    reported_frame_count = opencv_reported_frame_count(video)
    needed = required_frame_indices(segments, order, reported_frame_count)
    frames: dict[int, bytes]
    if len(order) == 1:
        frames = {}
        print("one-segment order: no joins to decode or score", flush=True)
    else:
        print(
            f"decoding detector-scale frames at "
            f"{metadata.comparison_width}x{metadata.comparison_height}",
            flush=True,
        )
        frames = retain_detector_frames(
            video,
            metadata.comparison_width,
            metadata.comparison_height,
            needed,
            info,
            args.progress_every_frames,
            args.progress_every_seconds,
        )

    scores = score_joins(
        segments,
        order,
        frames,
        metadata,
        reported_frame_count,
        args.max_robust_z,
        args.min_margin_ratio,
        args.require_rank1,
    )
    score_rows = [join_score_csv_row(score) for score in scores]
    flagged_rows = [
        join_score_csv_row(score) for score in scores if score.decision != "auto_pass"
    ]
    write_csv_atomically(out_dir / JOIN_SCORES_NAME, score_rows)
    write_csv_atomically(out_dir / FLAGGED_JOINS_NAME, flagged_rows)

    # The raw videos are tens of gigabytes and have already been checksum
    # verified by the downloader. Avoid a second full-file read after decoding;
    # bind the report to raw-file size/mtime and hash the small analysis inputs.
    print("recording input fingerprints", flush=True)
    fingerprints = {
        "video": input_fingerprint(video, hash_contents=False),
        "segments": input_fingerprint(segments_path),
        "order_csv": input_fingerprint(order_path),
        "detector_metadata": input_fingerprint(metadata_path),
    }
    summary = build_summary(
        video=video,
        segments_path=segments_path,
        order_path=order_path,
        detector_metadata_path=metadata_path,
        fingerprints=fingerprints,
        segments=segments,
        scores=scores,
        metadata=metadata,
        reported_frame_count=reported_frame_count,
        max_robust_z=args.max_robust_z,
        min_margin_ratio=args.min_margin_ratio,
        require_rank1=args.require_rank1,
    )
    write_json_atomically(out_dir / SUMMARY_NAME, summary)

    counts = summary["counts"]
    print(
        f"auto-QC decision: {summary['decision']} "
        f"(scored {counts['joins_scored']}/{counts['joins_expected']} joins; "
        f"flagged {counts['joins_flagged']})",
        flush=True,
    )
    print(f"join scores: {out_dir / JOIN_SCORES_NAME}", flush=True)
    print(f"flagged joins: {out_dir / FLAGGED_JOINS_NAME}", flush=True)
    print(f"summary: {out_dir / SUMMARY_NAME}", flush=True)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
