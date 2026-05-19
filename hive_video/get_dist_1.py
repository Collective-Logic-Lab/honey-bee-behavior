"""Download Distribution 1 data files into the local hive_video/data tree.

The repository already includes the small seed video in data/raw. Distribution 1
adds the larger resequenced video artifacts and selected experiment outputs used
by the notebooks.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_REMOTE = "hf://buckets/collective-logic-lab/honey-bee/distributions/distribution-1/v1"


def find_hf() -> list[str]:
    """Return a command prefix for the Hugging Face CLI."""
    hf = shutil.which("hf")
    if hf:
        return [hf]

    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "hf"]

    raise SystemExit(
        "Could not find `hf` or `uvx` on PATH. Run `uv sync` in hive_video or install the "
        "Hugging Face CLI before downloading Distribution 1."
    )


def run_sync(hf_cmd: list[str], remote: str, local: Path, dry_run: bool) -> None:
    local.mkdir(parents=True, exist_ok=True)
    command = [*hf_cmd, "sync", remote, str(local)]
    if dry_run:
        command.append("--dry-run")

    print(" ".join(command))
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Distribution 1 into the paths expected by hive_video notebooks."
    )
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help=f"Distribution root to sync from. Default: {DEFAULT_REMOTE}",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Local hive_video data directory. Default: data",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the sync plan without downloading files.",
    )
    args = parser.parse_args()

    data_dir = args.data_dir
    raw_sample = data_dir / "raw" / "start04_sample_5s.mp4"
    if not raw_sample.exists():
        print(
            f"warning: expected repository seed video is missing: {raw_sample}",
            file=sys.stderr,
        )

    hf_cmd = find_hf()
    remote_root = args.remote.rstrip("/")

    syncs = [
        (f"{remote_root}/data/artifacts", data_dir / "artifacts"),
        (f"{remote_root}/data/experiments", data_dir / "experiments"),
    ]
    for remote, local in syncs:
        run_sync(hf_cmd, remote, local, args.dry_run)

    print("Distribution 1 sync complete.")
    print(f"Data directory: {data_dir.resolve()}")


if __name__ == "__main__":
    main()
