from __future__ import annotations

import argparse
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from src.download import download_raw


def manifest_entry() -> dict:
    return {
        "dataFile": {
            "id": 237822,
            "filename": "start47__20190731_184423_side1_top.mp4",
            "filesize": 33458364280,
            "checksum": {
                "type": "MD5",
                "value": "b129f6027a0f095ab507ceb01add9326",
            },
        }
    }


class DownloadRawTests(unittest.TestCase):
    def test_start_locator_is_unambiguous(self) -> None:
        args = argparse.Namespace(
            locator="start47_side1_top",
            start=None,
            side=None,
            panel=None,
        )
        self.assertEqual(download_raw.resolve_selection(args), (47, 1, "top"))

    def test_old_day_locator_is_rejected(self) -> None:
        args = argparse.Namespace(
            locator="day47_side1_top",
            start=None,
            side=None,
            panel=None,
        )
        with self.assertRaises(SystemExit):
            download_raw.resolve_selection(args)

    def test_manifest_uses_checksum_fallback_and_start_locator(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Path(tmpdir) / "manifest.json"
            cache.write_text(json.dumps([manifest_entry()]))
            files = download_raw.load_manifest(
                "https://example.invalid",
                "doi:example",
                cache,
                refresh=False,
                timeout=1,
            )
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].locator, "start47_side1_top")
        self.assertEqual(files[0].panel, "top")
        self.assertEqual(files[0].md5, "b129f6027a0f095ab507ceb01add9326")

    def test_exact_archive_filename_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Path(tmpdir) / "manifest.json"
            cache.write_text(json.dumps([manifest_entry()]))
            files = download_raw.load_manifest(
                "https://example.invalid",
                "doi:example",
                cache,
                refresh=False,
                timeout=1,
            )
        selected = download_raw.select_file(
            files,
            filename="start47__20190731_184423_side1_top.mp4",
            start=None,
            side=None,
            panel=None,
        )
        self.assertEqual(selected.file_id, 237822)

    def test_concurrent_first_cache_writers_do_not_share_a_temp_path(self) -> None:
        raw = [manifest_entry()]

        def fetch(*_args):
            time.sleep(0.02)
            return raw

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Path(tmpdir) / "manifest.json"
            with mock.patch.object(download_raw, "fetch_manifest", side_effect=fetch):
                with ThreadPoolExecutor(max_workers=6) as pool:
                    results = list(
                        pool.map(
                            lambda _: download_raw.load_manifest(
                                "https://example.invalid",
                                "doi:example",
                                cache,
                                refresh=False,
                                timeout=1,
                            ),
                            range(6),
                        )
                    )
            self.assertEqual(json.loads(cache.read_text()), raw)
        self.assertTrue(all(result[0].locator == "start47_side1_top" for result in results))


if __name__ == "__main__":
    unittest.main()
