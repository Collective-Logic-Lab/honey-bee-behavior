#!/usr/bin/env python3
"""Create or validate a review approval tied to one auto-QC report."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


REVIEW_ARTIFACT_NAMES = {
    "flagged_joins": "auto_qc.flagged_joins.csv",
    "review_video": "qc_roll_flagged_joins.mp4",
    "review_captions": "qc_roll_flagged_joins.captions.csv",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    with path.open() as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def review_artifact_paths(summary_path: Path) -> dict[str, Path]:
    return {
        name: summary_path.parent / filename
        for name, filename in REVIEW_ARTIFACT_NAMES.items()
    }


def artifact_fingerprint(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"Required manual-review artifact is missing or empty: {path}")
    return {
        "filename": path.name,
        "source_path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def create_approval(
    summary_path: Path,
    out_path: Path,
    reviewer: str,
    note: str,
) -> dict:
    summary_path = summary_path.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    summary = read_json(summary_path)
    decision = summary.get("decision")
    if decision != "manual_review_required":
        raise ValueError(
            "Manual approval is only valid for an auto-QC report whose decision is "
            f"'manual_review_required'; got {decision!r}."
        )
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("Reviewer must not be empty.")

    review_artifacts = {
        name: artifact_fingerprint(path)
        for name, path in review_artifact_paths(summary_path).items()
    }
    approval = {
        "schema_version": 2,
        "approved_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer": reviewer,
        "note": note.strip(),
        "summary_path": str(summary_path),
        "summary_sha256": file_sha256(summary_path),
        "decision_at_review": decision,
        "review_artifacts": review_artifacts,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    partial = out_path.with_name(f".{out_path.name}.partial")
    partial.write_text(json.dumps(approval, indent=2, allow_nan=False) + "\n")
    partial.replace(out_path)
    return approval


def validate_approval(summary_path: Path, approval_path: Path) -> tuple[bool, str]:
    summary_path = summary_path.expanduser().resolve()
    approval_path = approval_path.expanduser().resolve()
    try:
        summary = read_json(summary_path)
        approval = read_json(approval_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return False, str(error)

    if summary.get("decision") != "manual_review_required":
        return False, "The current report does not require manual review."
    if approval.get("decision_at_review") != "manual_review_required":
        return False, "The approval was not created for a manual-review decision."
    if approval.get("summary_sha256") != file_sha256(summary_path):
        return False, "The approval is stale: the current auto-QC report has changed."
    expected_artifacts = approval.get("review_artifacts")
    if not isinstance(expected_artifacts, dict):
        return False, "The approval does not bind the manual-review artifacts."
    for name, path in review_artifact_paths(summary_path).items():
        expected = expected_artifacts.get(name)
        if not isinstance(expected, dict):
            return False, f"The approval does not bind review artifact {name}."
        try:
            current = artifact_fingerprint(path)
        except (OSError, ValueError) as error:
            return False, str(error)
        if (
            current["filename"] != expected.get("filename")
            or current["size_bytes"] != expected.get("size_bytes")
            or current["sha256"] != expected.get("sha256")
        ):
            return False, f"The approval is stale: review artifact {name} has changed."
    reviewer = approval.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        return False, "The approval does not identify a reviewer."
    return True, f"Manual join review approved by {reviewer}."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or validate a manual approval for a flagged join-QC report."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a report-bound approval.")
    create.add_argument("--summary", type=Path, required=True)
    create.add_argument("--out", type=Path, required=True)
    create.add_argument("--reviewer", default=getpass.getuser())
    create.add_argument("--note", default="")

    check = subparsers.add_parser("check", help="Validate an existing approval.")
    check.add_argument("--summary", type=Path, required=True)
    check.add_argument("--approval", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "create":
        approval = create_approval(args.summary, args.out, args.reviewer, args.note)
        print(f"wrote manual join-QC approval: {args.out.expanduser().resolve()}")
        print(f"summary sha256: {approval['summary_sha256']}")
        return 0

    valid, message = validate_approval(args.summary, args.approval)
    print(message)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
