#!/usr/bin/env python3
"""Create a smaller, share-oriented H.264 copy of a resequenced MP4.

The original resequenced MP4 remains the archival artifact. This tool makes a
separate derivative for collaborators who need a substantially smaller download.
It writes the MP4 and its provenance sidecar atomically and refuses to replace
an unexpected existing output unless ``--overwrite`` is explicit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILE_CRF = {
    "high": 18,
    "medium": 23,
    "low": 28,
}
METADATA_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Completed resequenced MP4.")
    parser.add_argument("--out", type=Path, required=True, help="Compressed MP4 path.")
    parser.add_argument(
        "--quality",
        choices=tuple(PROFILE_CRF),
        required=True,
        help="Share-quality profile: high (CRF 18), medium (23), or low (28).",
    )
    parser.add_argument(
        "--preset",
        default="medium",
        help="ffmpeg libx264 speed/compression preset; recorded in metadata.",
    )
    parser.add_argument(
        "--start-seconds",
        type=float,
        default=0.0,
        help="Start time for a bounded smoke sample. Default: start of the video.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Optional duration for a bounded smoke sample.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Optional ffmpeg encoder-thread cap.",
    )
    parser.add_argument(
        "--progress-every-seconds",
        type=float,
        default=60.0,
        help="Heartbeat interval for long transcodes.",
    )
    parser.add_argument(
        "--metadata-out",
        type=Path,
        default=None,
        help="Sidecar JSON path. Defaults beside --out.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def run_json(command: list[str]) -> dict[str, Any]:
    return json.loads(subprocess.check_output(command, text=True))


def fps_as_float(value: str) -> float:
    numerator, denominator = value.split("/", 1)
    if float(denominator) == 0:
        raise ValueError(f"Invalid frame rate {value!r}")
    return float(numerator) / float(denominator)


def probe_video(path: Path) -> dict[str, Any]:
    payload = run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames,duration,bit_rate",
            "-show_entries",
            "format=duration,size,bit_rate",
            "-of",
            "json",
            str(path),
        ]
    )
    streams = payload.get("streams", [])
    if len(streams) != 1:
        raise RuntimeError(f"Expected one video stream in {path}, found {len(streams)}")
    stream = streams[0]
    format_data = payload.get("format", {})
    duration_value = stream.get("duration") or format_data.get("duration")
    if duration_value is None:
        raise RuntimeError(f"ffprobe did not report a duration for {path}")
    frame_rate = stream.get("avg_frame_rate")
    if not frame_rate:
        raise RuntimeError(f"ffprobe did not report a frame rate for {path}")
    return {
        "codec_name": stream.get("codec_name"),
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "pix_fmt": stream.get("pix_fmt"),
        "fps": fps_as_float(frame_rate),
        "frame_rate": frame_rate,
        "nb_frames": int(stream["nb_frames"]) if stream.get("nb_frames") else None,
        "duration_seconds": float(duration_value),
        "size_bytes": int(format_data.get("size", path.stat().st_size)),
        "bit_rate": int(format_data["bit_rate"]) if format_data.get("bit_rate") else None,
    }


def input_descriptor(path: Path, probe: dict[str, Any]) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "probe": probe,
    }


def expected_duration(
    source_duration: float,
    start_seconds: float,
    duration_seconds: float | None,
) -> float:
    if start_seconds < 0:
        raise ValueError("--start-seconds must be non-negative")
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("--duration-seconds must be positive")
    if start_seconds >= source_duration:
        raise ValueError(
            f"--start-seconds={start_seconds} is outside the {source_duration:.3f}s input"
        )
    available = source_duration - start_seconds
    return available if duration_seconds is None else min(duration_seconds, available)


def validate_output(
    source_probe: dict[str, Any],
    output: Path,
    start_seconds: float,
    duration_seconds: float | None,
) -> dict[str, Any]:
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Compressed output is missing or empty: {output}")
    output_probe = probe_video(output)
    if output_probe["codec_name"] != "h264":
        raise RuntimeError(f"Expected H.264 output, got {output_probe['codec_name']!r}")
    if output_probe["pix_fmt"] != "yuv420p":
        raise RuntimeError(f"Expected yuv420p output, got {output_probe['pix_fmt']!r}")
    for field in ("width", "height"):
        if output_probe[field] != source_probe[field]:
            raise RuntimeError(
                f"Output {field} changed: {source_probe[field]} -> {output_probe[field]}"
            )
    fps_tolerance = 0.001
    if abs(output_probe["fps"] - source_probe["fps"]) > fps_tolerance:
        raise RuntimeError(
            f"Output FPS changed: {source_probe['fps']} -> {output_probe['fps']}"
        )
    expected = expected_duration(
        source_probe["duration_seconds"], start_seconds, duration_seconds
    )
    duration_tolerance = max(0.15, 2.0 / source_probe["fps"])
    if abs(output_probe["duration_seconds"] - expected) > duration_tolerance:
        raise RuntimeError(
            "Output duration is inconsistent with the requested input window: "
            f"expected {expected:.3f}s, got {output_probe['duration_seconds']:.3f}s"
        )
    if (
        start_seconds == 0
        and duration_seconds is None
        and source_probe["nb_frames"] is not None
        and output_probe["nb_frames"] is not None
        and output_probe["nb_frames"] != source_probe["nb_frames"]
    ):
        raise RuntimeError(
            "Full-output frame count changed: "
            f"{source_probe['nb_frames']} -> {output_probe['nb_frames']}"
        )
    return output_probe


def metadata_matches(
    metadata_path: Path,
    descriptor: dict[str, Any],
    quality: str,
    preset: str,
    start_seconds: float,
    duration_seconds: float | None,
    threads: int | None,
) -> bool:
    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (
        metadata.get("schema_version") == METADATA_SCHEMA_VERSION
        and metadata.get("input") == descriptor
        and metadata.get("settings")
        == {
            "quality": quality,
            "crf": PROFILE_CRF[quality],
            "preset": preset,
            "start_seconds": start_seconds,
            "duration_seconds": duration_seconds,
            "threads": threads,
        }
    )


def build_ffmpeg_command(
    source: Path,
    partial_output: Path,
    quality: str,
    preset: str,
    start_seconds: float,
    duration_seconds: float | None,
    threads: int | None,
) -> list[str]:
    command = ["ffmpeg", "-hide_banner", "-y", "-v", "error", "-i", str(source)]
    if start_seconds:
        command.extend(["-ss", f"{start_seconds:.6f}"])
    if duration_seconds is not None:
        command.extend(["-t", f"{duration_seconds:.6f}"])
    command.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-map_metadata",
            "0",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(PROFILE_CRF[quality]),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
        ]
    )
    if threads is not None:
        if threads < 1:
            raise ValueError("--threads must be at least 1")
        command.extend(["-threads", str(threads)])
    command.extend(["-progress", "pipe:1", "-nostats", str(partial_output)])
    return command


def run_ffmpeg(command: list[str], total_seconds: float, heartbeat_seconds: float) -> None:
    if heartbeat_seconds <= 0:
        raise ValueError("--progress-every-seconds must be positive")
    started = time.monotonic()
    last_heartbeat = started
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    with process.stdout:
        for line in process.stdout:
            line = line.rstrip()
            if "=" not in line:
                if line:
                    print(line, flush=True)
                continue
            key, value = line.split("=", 1)
            now = time.monotonic()
            if key == "out_time_us" and now - last_heartbeat >= heartbeat_seconds:
                rendered_seconds = int(value) / 1_000_000
                elapsed = now - started
                rate = rendered_seconds / elapsed if elapsed else 0.0
                percent = 100 * rendered_seconds / total_seconds if total_seconds else 0.0
                print(
                    f"progress: {rendered_seconds:.1f}/{total_seconds:.1f}s "
                    f"({percent:.1f}%), {rate:.2f}x realtime",
                    flush=True,
                )
                last_heartbeat = now
    return_code = process.wait()
    if return_code:
        raise RuntimeError(f"ffmpeg failed with exit code {return_code}")


def write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    partial = path.with_suffix(f"{path.suffix}.partial")
    partial.write_text(json.dumps(payload, indent=2) + "\n")
    partial.replace(path)


def human_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def compress(
    source: Path,
    output: Path,
    quality: str,
    preset: str,
    start_seconds: float,
    duration_seconds: float | None,
    threads: int | None,
    heartbeat_seconds: float,
    metadata_path: Path,
    overwrite: bool,
) -> dict[str, Any]:
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    metadata_path = metadata_path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Resequenced input is missing: {source}")
    if output.suffix.lower() != ".mp4":
        raise ValueError(f"Compressed output must be an .mp4 file: {output}")
    source_probe = probe_video(source)
    descriptor = input_descriptor(source, source_probe)
    window_duration = expected_duration(
        source_probe["duration_seconds"], start_seconds, duration_seconds
    )

    if output.exists() and not overwrite:
        if metadata_matches(
            metadata_path,
            descriptor,
            quality,
            preset,
            start_seconds,
            duration_seconds,
            threads,
        ):
            output_probe = validate_output(
                source_probe, output, start_seconds, duration_seconds
            )
            print(f"validated existing compressed output: {output}")
            return {"skipped": True, "output": output_probe}
        raise FileExistsError(
            f"Refusing to replace unexpected output {output}; use --overwrite after review."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    partial_output = output.with_name(f".{output.stem}.partial{output.suffix}")
    partial_output.unlink(missing_ok=True)
    command = build_ffmpeg_command(
        source,
        partial_output,
        quality,
        preset,
        start_seconds,
        duration_seconds,
        threads,
    )
    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    print(
        f"compressing {source.name} -> {output.name}: "
        f"quality={quality}, CRF={PROFILE_CRF[quality]}, preset={preset}",
        flush=True,
    )
    run_ffmpeg(command, window_duration, heartbeat_seconds)
    elapsed_seconds = time.monotonic() - started
    output_probe = validate_output(
        source_probe, partial_output, start_seconds, duration_seconds
    )
    partial_output.replace(output)
    metadata = {
        "schema_version": METADATA_SCHEMA_VERSION,
        "created_at_utc": started_at.isoformat(),
        "input": descriptor,
        "output": {
            "path": str(output),
            "probe": output_probe,
        },
        "settings": {
            "quality": quality,
            "crf": PROFILE_CRF[quality],
            "preset": preset,
            "start_seconds": start_seconds,
            "duration_seconds": duration_seconds,
            "threads": threads,
        },
        "elapsed_wall_seconds": elapsed_seconds,
        "encoding_realtime_factor": window_duration / elapsed_seconds,
        "ffmpeg_command": command,
    }
    write_json_atomically(metadata_path, metadata)
    print(f"wrote compressed video: {output}")
    print(f"output size: {human_size(output.stat().st_size)}")
    print(f"metadata: {metadata_path}")
    return {"skipped": False, "output": output_probe, "metadata": metadata}


def main() -> int:
    args = parse_args()
    out = args.out.expanduser()
    metadata_out = args.metadata_out or out.with_suffix(".compression.json")
    compress(
        args.input,
        out,
        args.quality,
        args.preset,
        args.start_seconds,
        args.duration_seconds,
        args.threads,
        args.progress_every_seconds,
        metadata_out,
        args.overwrite,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
