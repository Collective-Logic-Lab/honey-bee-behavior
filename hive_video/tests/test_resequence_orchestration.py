from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.resequence import build_segments_from_jumps
from src.resequence import compress_resequenced
from src.resequence import prepare_cut_review
from src.resequence import reassemble_video_from_segments
from src.resequence.diagnostics import make_join_review_video
from src.utils import verify_bucket_listing


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class CutReviewTests(unittest.TestCase):
    def test_single_jump_events_are_proposed_and_manual_edits_are_consumed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            events = root / "events.csv"
            write_csv(
                events,
                [
                    "rank",
                    "event_id",
                    "jump_count",
                    "duration_frames",
                    "peak_prev_frame_idx",
                    "avg_mean_abs_diff",
                    "max_mean_abs_diff",
                ],
                [
                    {
                        "rank": 1,
                        "event_id": 9,
                        "jump_count": 1,
                        "duration_frames": 2,
                        "peak_prev_frame_idx": 1800,
                        "avg_mean_abs_diff": 12.5,
                        "max_mean_abs_diff": 12.5,
                    },
                    {
                        "rank": 2,
                        "event_id": 10,
                        "jump_count": 3,
                        "duration_frames": 4,
                        "peak_prev_frame_idx": 3600,
                        "avg_mean_abs_diff": 9.0,
                        "max_mean_abs_diff": 11.0,
                    },
                ],
            )
            rows = prepare_cut_review.prepare_rows(events)
            self.assertEqual([row["keep"] for row in rows], ["1", "0"])

            rows[1]["keep"] = "1"
            rows.append({**rows[0], "prev_frame_idx": "5400", "event_id": "", "notes": "diagnosed"})
            verified = root / "cut_review.verified.csv"
            prepare_cut_review.write_rows(verified, rows)
            cuts = build_segments_from_jumps.read_jump_prev_frames(
                verified,
                top_n=1,
                input_kind="cut-review",
                single_jump_events_only=False,
                max_duration_frames=None,
            )
            self.assertEqual(cuts, [1800, 3600, 5400])


class CompressionTests(unittest.TestCase):
    def make_source(self, path: Path) -> None:
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            25.0,
            (32, 32),
        )
        self.assertTrue(writer.isOpened())
        for value in range(25):
            writer.write(np.full((32, 32, 3), value * 8, dtype=np.uint8))
        writer.release()

    def test_compression_writes_h264_and_validated_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "archival.mp4"
            output = root / "share.medium.mp4"
            metadata = root / "share.medium.compression.json"
            self.make_source(source)
            result = compress_resequenced.compress(
                source,
                output,
                quality="medium",
                preset="medium",
                start_seconds=0.0,
                duration_seconds=0.4,
                threads=1,
                heartbeat_seconds=60,
                metadata_path=metadata,
                overwrite=False,
            )
            self.assertFalse(result["skipped"])
            output_probe = compress_resequenced.probe_video(output)
            self.assertEqual(output_probe["codec_name"], "h264")
            self.assertEqual((output_probe["width"], output_probe["height"]), (32, 32))
            report = json.loads(metadata.read_text())
            self.assertEqual(report["settings"]["quality"], "medium")
            self.assertEqual(report["settings"]["crf"], 23)
            self.assertEqual(report["settings"]["threads"], 1)

            skipped = compress_resequenced.compress(
                source,
                output,
                quality="medium",
                preset="medium",
                start_seconds=0.0,
                duration_seconds=0.4,
                threads=1,
                heartbeat_seconds=60,
                metadata_path=metadata,
                overwrite=False,
            )
            self.assertTrue(skipped["skipped"])

    def test_compression_refuses_an_unexpected_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "archival.mp4"
            output = root / "unexpected.mp4"
            self.make_source(source)
            output.write_bytes(b"not an MP4")
            with self.assertRaises(FileExistsError):
                compress_resequenced.compress(
                    source,
                    output,
                    quality="low",
                    preset="medium",
                    start_seconds=0.0,
                    duration_seconds=0.4,
                    threads=1,
                    heartbeat_seconds=60,
                    metadata_path=root / "unexpected.compression.json",
                    overwrite=False,
                )


class ExactOrderReviewTests(unittest.TestCase):
    def test_review_uses_every_actual_order_join_including_rank_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            segments = root / "segments.csv"
            order = root / "order.csv"
            ranked = root / "ranked.csv"
            write_csv(
                segments,
                ["segment_id", "start_frame_idx", "end_frame_idx"],
                [
                    {"segment_id": 0, "start_frame_idx": 0, "end_frame_idx": 9},
                    {"segment_id": 1, "start_frame_idx": 10, "end_frame_idx": 19},
                    {"segment_id": 2, "start_frame_idx": 20, "end_frame_idx": 29},
                ],
            )
            write_csv(
                order,
                ["order", "segment_id"],
                [
                    {"order": 0, "segment_id": 0},
                    {"order": 1, "segment_id": 2},
                    {"order": 2, "segment_id": 1},
                ],
            )
            write_csv(
                ranked,
                [
                    "rank_for_from_segment",
                    "from_segment_id",
                    "to_segment_id",
                    "mean_abs_diff",
                ],
                [
                    {
                        "rank_for_from_segment": 2,
                        "from_segment_id": 0,
                        "to_segment_id": 2,
                        "mean_abs_diff": 3.0,
                    },
                    {
                        "rank_for_from_segment": 1,
                        "from_segment_id": 2,
                        "to_segment_id": 1,
                        "mean_abs_diff": 2.0,
                    },
                ],
            )
            edges = make_join_review_video.read_order_edges(
                segments, order, ranked, limit=None
            )
        self.assertEqual(
            [(edge["from_segment_id"], edge["to_segment_id"]) for edge in edges],
            [(0, 2), (2, 1)],
        )
        self.assertEqual(edges[0]["rank_for_from_segment"], 2)

    def test_review_rejects_an_order_that_omits_a_segment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            segments = root / "segments.csv"
            order = root / "order.csv"
            ranked = root / "ranked.csv"
            write_csv(
                segments,
                ["segment_id", "start_frame_idx", "end_frame_idx"],
                [
                    {"segment_id": 0, "start_frame_idx": 0, "end_frame_idx": 9},
                    {"segment_id": 1, "start_frame_idx": 10, "end_frame_idx": 19},
                    {"segment_id": 2, "start_frame_idx": 20, "end_frame_idx": 29},
                ],
            )
            write_csv(
                order,
                ["order", "segment_id"],
                [
                    {"order": 0, "segment_id": 0},
                    {"order": 1, "segment_id": 1},
                ],
            )
            write_csv(
                ranked,
                [
                    "rank_for_from_segment",
                    "from_segment_id",
                    "to_segment_id",
                    "mean_abs_diff",
                ],
                [],
            )
            with self.assertRaisesRegex(ValueError, "omits"):
                make_join_review_video.read_order_edges(
                    segments, order, ranked, limit=None
                )


class RestartValidationTests(unittest.TestCase):
    def make_reassembly_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        source = root / "source.mp4"
        writer = cv2.VideoWriter(
            str(source),
            cv2.VideoWriter_fourcc(*"mp4v"),
            25.0,
            (32, 32),
        )
        self.assertTrue(writer.isOpened())
        for value in range(6):
            writer.write(np.full((32, 32, 3), value * 20, dtype=np.uint8))
        writer.release()

        segments = root / "segments.csv"
        write_csv(
            segments,
            [
                "segment_id",
                "source_video",
                "start_frame_idx",
                "end_frame_idx",
                "duration_frames",
            ],
            [
                {
                    "segment_id": segment_id,
                    "source_video": source,
                    "start_frame_idx": segment_id * 2,
                    "end_frame_idx": segment_id * 2 + 1,
                    "duration_frames": 2,
                }
                for segment_id in range(3)
            ],
        )
        ranked = root / "ranked.csv"
        write_csv(
            ranked,
            [
                "rank_for_from_segment",
                "from_segment_id",
                "to_segment_id",
                "mean_abs_diff",
            ],
            [
                {
                    "rank_for_from_segment": 1,
                    "from_segment_id": 0,
                    "to_segment_id": 1,
                    "mean_abs_diff": 1.0,
                },
                {
                    "rank_for_from_segment": 1,
                    "from_segment_id": 1,
                    "to_segment_id": 2,
                    "mean_abs_diff": 1.0,
                },
            ],
        )
        order = root / "order.csv"
        write_csv(
            order,
            ["order", "segment_id"],
            [
                {"order": 0, "segment_id": 0},
                {"order": 1, "segment_id": 1},
                {"order": 2, "segment_id": 2},
            ],
        )
        return segments, ranked, order

    def test_complete_order_rejects_missing_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            order = Path(tmpdir) / "order.csv"
            write_csv(order, ["order", "segment_id"], [{"order": 0, "segment_id": 0}])
            with self.assertRaisesRegex(ValueError, "missing"):
                reassemble_video_from_segments.read_explicit_order(
                    order,
                    segments={0: {}, 1: {}},
                    require_complete=True,
                    max_segments=None,
                    order_start=0,
                    order_count=None,
                )

    def test_partial_mapping_is_not_accepted_as_a_complete_video_part(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            video = root / "part.mp4"
            mapping = root / "part.frame_mapping.csv"
            writer = cv2.VideoWriter(
                str(video),
                cv2.VideoWriter_fourcc(*"mp4v"),
                25.0,
                (32, 32),
            )
            self.assertTrue(writer.isOpened())
            for _ in range(3):
                writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
            writer.release()
            write_csv(mapping, ["output_frame_idx"], [{"output_frame_idx": 0}])
            self.assertFalse(
                reassemble_video_from_segments.artifacts_are_complete(
                    video, mapping, expected_frames=3
                )
            )
            write_csv(
                mapping,
                ["output_frame_idx"],
                [{"output_frame_idx": index} for index in range(3)],
            )
            self.assertTrue(
                reassemble_video_from_segments.artifacts_are_complete(
                    video, mapping, expected_frames=3
                )
            )

    def test_tiny_reassembly_finalizes_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            segments, ranked, order = self.make_reassembly_fixture(root)
            out = root / "output" / "reseq.mp4"
            command = [
                sys.executable,
                str(
                    Path(__file__).parents[1]
                    / "src/resequence/reassemble_video_from_segments.py"
                ),
                "--segments",
                str(segments),
                "--ranked-edges",
                str(ranked),
                "--order-csv",
                str(order),
                "--require-complete-order",
                "--out",
                str(out),
                "--scale-width",
                "32",
                "--caption-height",
                "8",
                "--segment-chunk-size",
                "1",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            mapping = out.with_suffix(".frame_mapping.csv")
            metadata = json.loads(out.with_suffix(".metadata.json").read_text())
            self.assertTrue(
                reassemble_video_from_segments.artifacts_are_complete(
                    out, mapping, expected_frames=5
                )
            )
            self.assertTrue(metadata["final_video_written"])
            self.assertFalse(list(root.rglob("*.partial*")))

    def test_safeword_returns_incomplete_status_and_does_not_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            segments, ranked, order = self.make_reassembly_fixture(root)
            out = root / "stopped" / "reseq.mp4"
            safeword = root / ".safeword"
            safeword.write_text("sea cucumber\n")
            command = [
                sys.executable,
                str(
                    Path(__file__).parents[1]
                    / "src/resequence/reassemble_video_from_segments.py"
                ),
                "--segments",
                str(segments),
                "--ranked-edges",
                str(ranked),
                "--order-csv",
                str(order),
                "--require-complete-order",
                "--out",
                str(out),
                "--safeword-file",
                str(safeword),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(
                result.returncode,
                reassemble_video_from_segments.INCOMPLETE_EXIT_CODE,
            )
            self.assertFalse(out.exists())


class BucketVerificationTests(unittest.TestCase):
    def test_remote_listing_must_match_staged_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            staging = root / "staging"
            staging.mkdir()
            (staging / "video.mp4").write_bytes(b"abc")
            listing = root / "listing.json"
            listing.write_text(
                json.dumps(
                    [
                        {
                            "type": "file",
                            "path": "resequenced/run/video.mp4",
                            "size": 3,
                        }
                    ]
                )
            )
            verified = verify_bucket_listing.verify_listing(
                staging, listing, "resequenced/run"
            )
            self.assertEqual(verified, ["resequenced/run/video.mp4"])


if __name__ == "__main__":
    unittest.main()
