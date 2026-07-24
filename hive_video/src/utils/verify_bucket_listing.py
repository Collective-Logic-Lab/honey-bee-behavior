#!/usr/bin/env python3
"""Verify that every staged file appears remotely with the same byte size."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-dir", type=Path, required=True)
    parser.add_argument("--listing", type=Path, required=True)
    parser.add_argument("--remote-prefix", required=True)
    return parser.parse_args()


def verify_listing(
    local_dir: Path,
    listing_path: Path,
    remote_prefix: str,
) -> list[str]:
    listing = json.loads(listing_path.read_text())
    if not isinstance(listing, list):
        raise ValueError(f"Expected a JSON list in {listing_path}")
    remote_sizes = {
        str(item["path"]): int(item["size"])
        for item in listing
        if item.get("type") == "file"
    }
    prefix = remote_prefix.strip("/")
    verified: list[str] = []
    errors: list[str] = []
    for local_path in sorted(path for path in local_dir.rglob("*") if path.is_file()):
        relative = local_path.relative_to(local_dir).as_posix()
        remote_path = f"{prefix}/{relative}"
        remote_size = remote_sizes.get(remote_path)
        local_size = local_path.stat().st_size
        if remote_size is None:
            errors.append(f"missing remotely: {remote_path}")
        elif remote_size != local_size:
            errors.append(
                f"size mismatch for {remote_path}: local={local_size}, remote={remote_size}"
            )
        else:
            verified.append(remote_path)
    if errors:
        raise RuntimeError("Remote verification failed:\n  " + "\n  ".join(errors))
    if not verified:
        raise RuntimeError(f"No staged files found under {local_dir}")
    return verified


def main() -> None:
    args = parse_args()
    verified = verify_listing(
        args.local_dir.expanduser().resolve(),
        args.listing.expanduser().resolve(),
        args.remote_prefix,
    )
    print(f"verified {len(verified)} remote files")
    for path in verified:
        print(f"  {path}")


if __name__ == "__main__":
    main()
