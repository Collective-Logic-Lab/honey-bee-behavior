from __future__ import annotations

import argparse
import json
import ssl
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
    def test_default_ssl_context_keeps_verification_enabled(self) -> None:
        context, loaded = download_raw.build_ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertTrue(loaded)
        self.assertTrue(context.get_ca_certs())

    def test_ssl_context_adds_certifi_system_and_explicit_ca_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            certifi_bundle = root / "certifi.pem"
            system_bundle = root / "system.pem"
            explicit_bundle = root / "explicit.pem"
            for bundle in (certifi_bundle, system_bundle, explicit_bundle):
                bundle.write_text("test fixture")

            context = mock.Mock(spec=ssl.SSLContext)
            with (
                mock.patch.object(download_raw.ssl, "create_default_context", return_value=context),
                mock.patch.object(download_raw.certifi, "where", return_value=str(certifi_bundle)),
                mock.patch.object(
                    download_raw,
                    "SYSTEM_CA_BUNDLE_CANDIDATES",
                    (system_bundle,),
                ),
                mock.patch.dict("os.environ", {}, clear=True),
            ):
                result, loaded = download_raw.build_ssl_context(explicit_bundle)

        self.assertIs(result, context)
        self.assertEqual(
            loaded,
            (
                explicit_bundle.resolve(),
                certifi_bundle.resolve(),
                system_bundle.resolve(),
            ),
        )
        self.assertEqual(context.load_verify_locations.call_count, 3)

    def test_http_get_passes_verifying_context_to_opener(self) -> None:
        context = ssl.create_default_context()
        response = object()
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(
            download_raw.urllib.request,
            "build_opener",
            return_value=opener,
        ) as build_opener:
            result = download_raw._http_get(
                "https://example.invalid/video",
                4,
                {"Range": "bytes=0-0"},
                context,
            )
        self.assertIs(result, response)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Range"), "bytes=0-0")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 4)
        redirect_handler, https_handler = build_opener.call_args.args
        self.assertIsInstance(redirect_handler, download_raw.HTTPSOnlyRedirectHandler)
        self.assertIs(https_handler._context, context)

    def test_redirect_handler_rejects_non_https_before_following(self) -> None:
        handler = download_raw.HTTPSOnlyRedirectHandler()
        response = mock.Mock()
        request = download_raw.urllib.request.Request("https://example.invalid/access")
        with self.assertRaisesRegex(RuntimeError, "non-HTTPS redirect"):
            handler.redirect_request(
                request,
                response,
                303,
                "See Other",
                {},
                "http://storage.example.invalid/media",
            )
        response.close.assert_called_once_with()

    def test_http_get_rejects_non_https_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-HTTPS archive request"):
            download_raw._http_get(
                "http://example.invalid/access",
                2,
                None,
                ssl.create_default_context(),
            )

    def test_probe_download_reads_only_one_byte(self) -> None:
        remote = download_raw.RemoteFile(
            file_id=237822,
            filename="start47__20190731_184423_side1_top.mp4",
            size=33458364280,
            md5="b129f6027a0f095ab507ceb01add9326",
            start=47,
            date="20190731",
            time="184423",
            side=1,
            panel="top",
        )
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 206
        response.headers = {"Content-Range": "bytes 0-0/33458364280"}
        response.geturl.return_value = "https://storage.example.invalid/signed"
        response.read.return_value = b"x"
        context = ssl.create_default_context()
        with mock.patch.object(download_raw, "_http_get", return_value=response) as http_get:
            download_raw.probe_download(remote, "https://example.invalid", 5, context)
        http_get.assert_called_once_with(
            "https://example.invalid/api/access/datafile/237822",
            5,
            {"Range": "bytes=0-0"},
            context,
        )
        response.read.assert_called_once_with(1)

    def test_probe_download_rejects_wrong_range_size(self) -> None:
        remote = download_raw.RemoteFile(
            file_id=237822,
            filename="start47__20190731_184423_side1_top.mp4",
            size=33458364280,
            md5="b129f6027a0f095ab507ceb01add9326",
            start=47,
            date="20190731",
            time="184423",
            side=1,
            panel="top",
        )
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 206
        response.headers = {"Content-Range": "bytes 0-0/1"}
        response.geturl.return_value = "https://storage.example.invalid/signed"
        with mock.patch.object(download_raw, "_http_get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "size mismatch"):
                download_raw.probe_download(
                    remote,
                    "https://example.invalid",
                    5,
                    ssl.create_default_context(),
                )

    def test_certificate_verification_failure_is_not_retried(self) -> None:
        context = ssl.create_default_context()
        certificate_error = ssl.SSLCertVerificationError(
            1,
            "unable to get local issuer certificate",
        )
        with mock.patch.object(
            download_raw.urllib.request,
            "build_opener",
        ) as build_opener:
            build_opener.return_value.open.side_effect = download_raw.urllib.error.URLError(
                certificate_error
            )
            with self.assertRaisesRegex(RuntimeError, "TLS certificate verification failed"):
                download_raw._http_get(
                    "https://example.invalid/video",
                    4,
                    None,
                    context,
                )

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
