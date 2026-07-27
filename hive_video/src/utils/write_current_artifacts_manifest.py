#!/usr/bin/env python3
"""Atomically describe the current files in a staged resequencing upload."""

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

MANIFEST_NAME = "CURRENT_ARTIFACTS.json"
DEFAULT_HASH_THRESHOLD_BYTES = 1024**3
ALLOWED_DECISIONS = {"auto_pass", "manual_review_required"}
SUPERSESSION_NOTICE = (
    "Upload sync is non-deleting; except for CURRENT_ARTIFACTS.json itself, "
    "any remote object not listed in files is superseded and is not part of "
    "the current artifact set."
)
KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--auto-qc-summary", type=Path, required=True)
    parser.add_argument("--reassembly-completion", type=Path, required=True)
    parser.add_argument(
        "--hash-threshold-bytes", type=int, default=DEFAULT_HASH_THRESHOLD_BYTES
    )
    return parser.parse_args()


def strict_json(text: str, source: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON constant in {source}: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key in {source}: {key!r}")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )


def regular_file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symbolic link: {path}")
    path = path.expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"{label} is not a regular file: {path}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    staging_dir: Path,
    key: str,
    auto_qc_summary: Path,
    reassembly_completion: Path,
    hash_threshold_bytes: int,
) -> dict[str, Any]:
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError(f"Invalid artifact key: {key!r}")
    if type(hash_threshold_bytes) is not int or hash_threshold_bytes < 0:
        raise ValueError("hash_threshold_bytes must be a nonnegative integer")
    staging_dir = staging_dir.expanduser().resolve(strict=True)
    if not staging_dir.is_dir():
        raise ValueError(f"Staging path is not a directory: {staging_dir}")

    summary = regular_file(auto_qc_summary, "Auto-QC summary")
    try:
        summary_relative = summary.relative_to(staging_dir).as_posix()
    except ValueError as error:
        raise ValueError("Auto-QC summary must be inside staging") from error
    summary_json = strict_json(summary.read_text(encoding="utf-8"), summary)
    decision = summary_json.get("decision") if isinstance(summary_json, dict) else None
    if not isinstance(decision, str) or decision not in ALLOWED_DECISIONS:
        raise ValueError(f"Invalid Auto-QC decision: {decision!r}")
    completion = regular_file(reassembly_completion, "Reassembly completion marker")
    if completion.stat().st_size == 0:
        raise ValueError(f"Reassembly completion marker is empty: {completion}")

    files: list[dict[str, Any]] = []
    output = staging_dir / MANIFEST_NAME
    for path in sorted(staging_dir.rglob("*")):
        if path == output:
            continue
        if path.is_symlink():
            raise ValueError(f"Staging contains a symbolic link: {path}")
        if not path.is_file():
            continue
        size = path.stat().st_size
        hashed = size <= hash_threshold_bytes
        files.append(
            {
                "path": path.relative_to(staging_dir).as_posix(),
                "size_bytes": size,
                "hash_status": "sha256" if hashed else "unhashed",
                "sha256": sha256_file(path) if hashed else None,
            }
        )
    if summary_relative not in {entry["path"] for entry in files}:
        raise ValueError("Staging inventory does not contain the Auto-QC summary")
    return {
        "schema_version": 1,
        "key": key,
        "supersession_notice": SUPERSESSION_NOTICE,
        "auto_qc_decision": decision,
        "auto_qc_summary_sha256": sha256_file(summary),
        "reassembly_completion_sha256": sha256_file(completion),
        "hash_threshold_bytes": hash_threshold_bytes,
        "files": files,
    }


def write_manifest_atomically(
    staging_dir: Path,
    *,
    key: str,
    auto_qc_summary: Path,
    reassembly_completion: Path,
    hash_threshold_bytes: int = DEFAULT_HASH_THRESHOLD_BYTES,
) -> Path:
    staging_dir = staging_dir.expanduser().resolve(strict=True)
    manifest = build_manifest(
        staging_dir,
        key,
        auto_qc_summary,
        reassembly_completion,
        hash_threshold_bytes,
    )
    serialized = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    descriptor, name = tempfile.mkstemp(
        dir=staging_dir, prefix=f".{MANIFEST_NAME}.", suffix=".partial"
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, staging_dir / MANIFEST_NAME)
    finally:
        temporary.unlink(missing_ok=True)
    return staging_dir / MANIFEST_NAME


def main() -> None:
    args = parse_args()
    output = write_manifest_atomically(
        args.staging_dir,
        key=args.key,
        auto_qc_summary=args.auto_qc_summary,
        reassembly_completion=args.reassembly_completion,
        hash_threshold_bytes=args.hash_threshold_bytes,
    )
    manifest = strict_json(output.read_text(encoding="utf-8"), output)
    print(f"wrote {output}: {len(manifest['files'])} staged files")


if __name__ == "__main__":
    main()
