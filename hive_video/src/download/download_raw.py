"""Download raw 2019 hive videos from the Edmond (Dataverse) archive.

The source dataset is "Videos for honey bee lifetime tracking data 2019",
published at doi:10.17617/3.LLWRWR. Every file in it is public, so no API
token is required.

Files are named on the archive like::

    start47__20190731_184423_side1_top.mp4

This module addresses them either by the archive filename or by the
``day`` / ``side`` / ``frame`` triple, where ``day`` is the literal start
index (``--day 47`` selects ``start47``). It also exposes a canonical *key*
used everywhere downstream::

    start47_20190731_184423_side1_top

That key is the naming pattern the resequencing outputs follow
(``reseq_<key>``), so slurm scripts can resolve a locator once and derive
every later path from it.

Examples::

    # Download one file into the current directory.
    uv run python src/download/download_raw.py --day 4 --side 1 --frame top

    # Download by archive filename into an explicit target.
    uv run python src/download/download_raw.py \\
        --filename start47__20190731_184423_side1_top.mp4 \\
        --target /scratch/pdressla/honey-bee/downloads

    # Resolve a slurm locator to its key and local path without downloading.
    uv run python src/download/download_raw.py --locator day47_side1_top --resolve-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SERVER = "https://edmond.mpg.de"
DEFAULT_DOI = "doi:10.17617/3.LLWRWR"

# start47__20190731_184423_side1_top.mp4
FILENAME_RE = re.compile(
    r"^start(?P<day>\d+)__(?P<date>\d{8})_(?P<time>\d{6})_side(?P<side>\d)_(?P<frame>[a-z]+)\.mp4$"
)
# day47_side1_top
LOCATOR_RE = re.compile(r"^day(?P<day>\d+)_side(?P<side>\d)_(?P<frame>[a-z]+)$")

CHUNK_BYTES = 8 * 1024 * 1024
USER_AGENT = "hive-video-download-raw/1.0"


@dataclass(frozen=True)
class RemoteFile:
    """One file in the Edmond dataset."""

    file_id: int
    filename: str
    size: int
    md5: str
    day: int
    date: str
    time: str
    side: int
    frame: str

    @property
    def key(self) -> str:
        """Canonical key, e.g. ``start47_20190731_184423_side1_top``."""
        return f"start{self.day:02d}_{self.date}_{self.time}_side{self.side}_{self.frame}"

    @property
    def locator(self) -> str:
        """Compact slurm-friendly locator, e.g. ``day47_side1_top``."""
        return f"day{self.day}_side{self.side}_{self.frame}"

    @property
    def reseq_dirname(self) -> str:
        """Output folder name used by the resequencing pipeline."""
        return f"reseq_{self.key}"


def default_cache_path(doi: str) -> Path:
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "hive_video"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", doi).strip("_")
    return root / f"edmond_manifest_{slug}.json"


def _http_get(url: str, timeout: float, headers: dict[str, str] | None = None):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_manifest(server: str, doi: str, timeout: float) -> list[dict]:
    """Fetch the dataset file listing from the Dataverse native API."""
    url = (
        f"{server}/api/datasets/:persistentId/versions/:latest/files"
        f"?persistentId={urllib.parse.quote(doi, safe=':.')}"
    )
    with _http_get(url, timeout) as response:
        payload = json.load(response)
    if payload.get("status") != "OK":
        raise RuntimeError(f"Dataverse API returned status {payload.get('status')!r} for {doi}")
    return payload["data"]


def load_manifest(
    server: str, doi: str, cache_path: Path, refresh: bool, timeout: float
) -> list[RemoteFile]:
    """Load the file listing, using a local cache unless ``refresh`` is set.

    The published dataset is immutable, so caching avoids one API round trip
    per array task.
    """
    raw: list[dict] | None = None
    if cache_path.exists() and not refresh:
        try:
            raw = json.loads(cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            raw = None
    if raw is None:
        raw = fetch_manifest(server, doi, timeout)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(raw))
        tmp.replace(cache_path)

    files: list[RemoteFile] = []
    for entry in raw:
        data_file = entry["dataFile"]
        name = data_file["filename"]
        match = FILENAME_RE.match(name)
        if match is None:
            continue  # non-video assets, e.g. the camera diagram PNG
        files.append(
            RemoteFile(
                file_id=int(data_file["id"]),
                filename=name,
                size=int(data_file.get("filesize", 0)),
                md5=str(data_file.get("md5", "")),
                day=int(match.group("day")),
                date=match.group("date"),
                time=match.group("time"),
                side=int(match.group("side")),
                frame=match.group("frame"),
            )
        )
    return files


def select_file(
    files: list[RemoteFile],
    filename: str | None,
    day: int | None,
    side: int | None,
    frame: str | None,
) -> RemoteFile:
    """Resolve a single archive file, failing loudly when the request is ambiguous."""
    if filename is not None:
        for candidate in files:
            if candidate.filename == filename:
                return candidate
        raise SystemExit(f"No archive file named {filename!r} in this dataset.")

    matches = [f for f in files if f.day == day and f.side == side and f.frame == frame]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        for_day = [f for f in files if f.day == day]
        if not for_day:
            days = sorted({f.day for f in files})
            raise SystemExit(
                f"No start{day:02d} in this dataset. Available start indices: "
                f"{days[0]}-{days[-1]} ({len(days)} captures)."
            )
        sides = sorted({f.side for f in for_day})
        frames = sorted({f.frame for f in for_day})
        raise SystemExit(
            f"No start{day:02d} side{side} {frame!r}. For start{day:02d} the archive has "
            f"sides {sides} and frames {frames}."
        )
    names = ", ".join(f.filename for f in matches)
    raise SystemExit(f"Ambiguous selection, matched several files: {names}")


def md5sum(path: Path, chunk_bytes: int = CHUNK_BYTES) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_bytes), b""):
            digest.update(block)
    return digest.hexdigest()


def _format_bytes(count: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(count) < 1024.0:
            return f"{count:.1f}{unit}"
        count /= 1024.0
    return f"{count:.1f}PB"


def download(
    remote: RemoteFile,
    destination: Path,
    server: str,
    timeout: float,
    retries: int,
    progress_seconds: float,
) -> None:
    """Download ``remote`` to ``destination``, resuming a partial ``.part`` file.

    Edmond redirects large files to presigned S3 URLs that honour HTTP range
    requests, so an interrupted transfer resumes rather than restarting.
    """
    part = destination.with_suffix(destination.suffix + ".part")
    url = f"{server}/api/access/datafile/{remote.file_id}"

    for attempt in range(1, retries + 1):
        have = part.stat().st_size if part.exists() else 0
        if remote.size and have > remote.size:
            print(f"  partial file is larger than expected ({have} > {remote.size}); restarting")
            part.unlink()
            have = 0
        if remote.size and have == remote.size:
            break

        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with _http_get(url, timeout, headers) as response:
                if have and response.status != 206:
                    # Server ignored the range request; start over rather than corrupt.
                    print(f"  server returned {response.status} for a range request; restarting")
                    part.unlink(missing_ok=True)
                    have = 0
                mode = "ab" if have else "wb"
                started = time.monotonic()
                last_report = started
                written = have
                with part.open(mode) as handle:
                    while True:
                        block = response.read(CHUNK_BYTES)
                        if not block:
                            break
                        handle.write(block)
                        written += len(block)
                        now = time.monotonic()
                        if now - last_report >= progress_seconds:
                            rate = (written - have) / max(now - started, 1e-6)
                            pct = f"{100.0 * written / remote.size:5.1f}%" if remote.size else "?"
                            print(
                                f"  {pct} {_format_bytes(written)}"
                                f"/{_format_bytes(remote.size)} at {_format_bytes(rate)}/s",
                                flush=True,
                            )
                            last_report = now
            if not remote.size or part.stat().st_size == remote.size:
                break
            print(f"  short read ({part.stat().st_size}/{remote.size}); retrying")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            if attempt == retries:
                raise
            backoff = min(60.0, 2.0**attempt)
            print(f"  attempt {attempt}/{retries} failed ({error}); retrying in {backoff:.0f}s")
            time.sleep(backoff)
    else:
        raise SystemExit(f"Giving up on {remote.filename} after {retries} attempts.")

    part.replace(destination)


def resolve_selection(args: argparse.Namespace) -> tuple[int | None, int | None, str | None]:
    """Normalise --locator into the day/side/frame triple."""
    if args.locator is not None:
        match = LOCATOR_RE.match(args.locator)
        if match is None:
            raise SystemExit(
                f"Could not parse locator {args.locator!r}. Expected e.g. 'day47_side1_top'."
            )
        return int(match.group("day")), int(match.group("side")), match.group("frame")
    return args.day, args.side, args.frame


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download a raw 2019 hive video from the Edmond archive by day/side/frame "
            "or by archive filename."
        )
    )
    selector = parser.add_argument_group("file selection")
    selector.add_argument(
        "--day",
        type=int,
        help="Literal capture start index: --day 47 selects start47.",
    )
    selector.add_argument("--side", type=int, choices=(0, 1), help="Hive side.")
    selector.add_argument(
        "--frame",
        help="Camera frame position. The 2019 archive provides 'top' and 'bottom'.",
    )
    selector.add_argument("--filename", help="Exact archive filename, overrides day/side/frame.")
    selector.add_argument(
        "--locator",
        help="Compact locator used by the slurm arrays, e.g. 'day47_side1_top'.",
    )

    parser.add_argument(
        "--target",
        type=Path,
        default=Path.cwd(),
        help="Directory to download into. Defaults to the current directory.",
    )
    parser.add_argument(
        "--resolve-only",
        action="store_true",
        help="Print the resolved key, filename and local path, then exit without downloading.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "sh"),
        default="json",
        help=(
            "Output shape for --resolve-only. 'sh' emits RESEQ_* shell assignments "
            "suitable for eval in a slurm script."
        ),
    )
    parser.add_argument("--list", action="store_true", help="List archive files and exit.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when a verified local copy already exists.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip the MD5 check. Faster, but a truncated file will go unnoticed.",
    )

    source = parser.add_argument_group("archive source")
    source.add_argument("--server", default=DEFAULT_SERVER)
    source.add_argument("--doi", default=DEFAULT_DOI)
    source.add_argument("--manifest-cache", type=Path, default=None)
    source.add_argument("--refresh-manifest", action="store_true")
    source.add_argument("--timeout", type=float, default=120.0)
    source.add_argument("--retries", type=int, default=8)
    source.add_argument("--progress-every-seconds", type=float, default=60.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cache_path = args.manifest_cache or default_cache_path(args.doi)
    files = load_manifest(args.server, args.doi, cache_path, args.refresh_manifest, args.timeout)

    if args.list:
        for entry in sorted(files, key=lambda f: (f.day, f.side, f.frame)):
            print(f"{entry.key}\t{entry.locator}\t{entry.size / 1e9:.1f}GB\t{entry.filename}")
        return 0

    day, side, frame = resolve_selection(args)
    if args.filename is None and (day is None or side is None or frame is None):
        raise SystemExit("Specify --filename, or --locator, or all of --day, --side and --frame.")

    remote = select_file(files, args.filename, day, side, frame)
    destination = args.target.expanduser() / remote.filename

    if args.resolve_only:
        resolved = {
            "key": remote.key,
            "locator": remote.locator,
            "filename": remote.filename,
            "path": str(destination),
            "reseq_dirname": remote.reseq_dirname,
            "file_id": remote.file_id,
            "size": remote.size,
            "md5": remote.md5,
        }
        if args.format == "sh":
            for name, value in resolved.items():
                # Avoid RESEQ_RESEQ_DIRNAME; the prefix already carries that meaning.
                suffix = name.removeprefix("reseq_").upper()
                print(f"RESEQ_{suffix}={shlex.quote(str(value))}")
        else:
            print(json.dumps(resolved, indent=2))
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"resolved {remote.locator} -> {remote.filename} ({remote.size / 1e9:.1f} GB)")
    print(f"target   {destination}")

    if destination.exists() and not args.force:
        if args.no_verify:
            print("already present, skipping (MD5 not checked)")
            return 0
        if destination.stat().st_size == remote.size and md5sum(destination) == remote.md5:
            print("already present and MD5 matches, skipping")
            return 0
        print("existing file does not match the archive checksum; re-downloading")

    download(
        remote,
        destination,
        args.server,
        args.timeout,
        args.retries,
        args.progress_every_seconds,
    )

    if not args.no_verify:
        print("verifying MD5")
        digest = md5sum(destination)
        if digest != remote.md5:
            raise SystemExit(f"MD5 mismatch: got {digest}, archive says {remote.md5}")
        print("MD5 OK")

    print(f"done: {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
