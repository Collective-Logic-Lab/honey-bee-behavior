from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

from src.resequence import build_segments_from_jumps
from src.resequence import compress_resequenced
from src.resequence import detect_video_discontinuities
from src.resequence import prepare_cut_review
from src.resequence import reassemble_video_from_segments
from src.resequence.diagnostics import approve_manual_join_qc
from src.resequence.diagnostics import auto_qc_segment_joins
from src.resequence.diagnostics import make_join_review_video
from src.utils import verify_bucket_listing
from src.utils import write_current_artifacts_manifest


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class DetectionArtifactTests(unittest.TestCase):
    def test_candidate_jpegs_are_explicitly_opt_in(self) -> None:
        with mock.patch.object(
            sys,
            "argv",
            ["detect_video_discontinuities.py", "input.mp4", "--out", "qc"],
        ):
            default_args = detect_video_discontinuities.parse_args()
        self.assertFalse(default_args.write_candidate_frames)

        with mock.patch.object(
            sys,
            "argv",
            [
                "detect_video_discontinuities.py",
                "input.mp4",
                "--out",
                "qc",
                "--write-candidate-frames",
            ],
        ):
            explicit_args = detect_video_discontinuities.parse_args()
        self.assertTrue(explicit_args.write_candidate_frames)


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
    def test_small_green_flash_render_writes_video_and_captions(self) -> None:
        source = Path(__file__).parents[1] / "data/raw/start04_sample_5s.mp4"
        self.assertTrue(source.is_file())
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            segments = root / "segments.csv"
            order = root / "order.csv"
            ranked = root / "ranked.csv"
            out = root / "review.mp4"
            write_csv(
                segments,
                ["segment_id", "start_frame_idx", "end_frame_idx"],
                [
                    {"segment_id": 0, "start_frame_idx": 0, "end_frame_idx": 39},
                    {"segment_id": 1, "start_frame_idx": 40, "end_frame_idx": 79},
                    {"segment_id": 2, "start_frame_idx": 80, "end_frame_idx": 119},
                ],
            )
            write_csv(
                order,
                ["order", "segment_id"],
                [
                    {"order": 0, "segment_id": 0},
                    {"order": 1, "segment_id": 1},
                    {"order": 2, "segment_id": 2},
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
            command = [
                sys.executable,
                str(
                    Path(__file__).parents[1]
                    / "src/resequence/diagnostics/make_join_review_video.py"
                ),
                str(source),
                "--ranked-edges",
                str(ranked),
                "--segments",
                str(segments),
                "--order-csv",
                str(order),
                "--out",
                str(out),
                "--seconds-each-side",
                "0.08",
                "--scale-width",
                "64",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)
            dimensions = subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "csv=p=0",
                    str(out),
                ],
                text=True,
            ).strip()
            self.assertEqual(
                dimensions,
                f"64,{make_join_review_video.probe_scaled_height(source, 64) + 40}",
            )
            captions = out.with_suffix(".captions.csv")
            self.assertTrue(captions.is_file())
            with captions.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 6)
            self.assertIn("before f39", rows[0]["caption"])
            self.assertNotIn("before end frame", rows[0]["caption"])

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

    def test_review_filter_preserves_original_join_indices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            segments = root / "segments.csv"
            order = root / "order.csv"
            ranked = root / "ranked.csv"
            flagged = root / "flagged.csv"
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
                    {"order": 2, "segment_id": 2},
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
            write_csv(flagged, ["join_index"], [{"join_index": 2}])
            join_indices = make_join_review_video.read_join_indices(flagged)
            edges = make_join_review_video.read_order_edges(
                segments,
                order,
                ranked,
                limit=None,
                join_indices=join_indices,
            )
        self.assertEqual(
            [
                (
                    edge["join_index"],
                    edge["from_segment_id"],
                    edge["to_segment_id"],
                )
                for edge in edges
            ],
            [(2, 1, 2)],
        )

    def test_flagged_only_review_renders_just_the_requested_join(self) -> None:
        source = Path(__file__).parents[1] / "data/raw/start04_sample_5s.mp4"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            segments = root / "segments.csv"
            order = root / "order.csv"
            ranked = root / "ranked.csv"
            flagged = root / "auto_qc.flagged_joins.csv"
            out = root / "flagged.mp4"
            write_csv(
                segments,
                ["segment_id", "start_frame_idx", "end_frame_idx"],
                [
                    {"segment_id": 0, "start_frame_idx": 0, "end_frame_idx": 39},
                    {"segment_id": 1, "start_frame_idx": 40, "end_frame_idx": 79},
                    {"segment_id": 2, "start_frame_idx": 80, "end_frame_idx": 119},
                ],
            )
            write_csv(
                order,
                ["order", "segment_id"],
                [
                    {"order": 0, "segment_id": 0},
                    {"order": 1, "segment_id": 1},
                    {"order": 2, "segment_id": 2},
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
            write_csv(
                flagged,
                [
                    "join_index",
                    "from_actual_end_frame_idx",
                    "to_start_frame_idx",
                    "selected_mean_abs_diff",
                    "selected_rank",
                    "margin_ratio",
                    "robust_z",
                    "decision",
                    "reasons",
                ],
                [
                    {
                        "join_index": 2,
                        "from_actual_end_frame_idx": 78,
                        "to_start_frame_idx": 80,
                        "selected_mean_abs_diff": "8.500000",
                        "selected_rank": 1,
                        "margin_ratio": "1.500000",
                        "robust_z": "9.000000",
                        "decision": "manual_review_required",
                        "reasons": "margin_ratio_below_min",
                    }
                ],
            )
            subprocess.run(
                [
                    sys.executable,
                    str(
                        Path(__file__).parents[1]
                        / "src/resequence/diagnostics/make_join_review_video.py"
                    ),
                    str(source),
                    "--ranked-edges",
                    str(ranked),
                    "--segments",
                    str(segments),
                    "--order-csv",
                    str(order),
                    "--join-filter-csv",
                    str(flagged),
                    "--out",
                    str(out),
                    "--seconds-each-side",
                    "0.08",
                    "--scale-width",
                    "64",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            with out.with_suffix(".captions.csv").open(newline="") as handle:
                captions = list(csv.DictReader(handle))
            self.assertEqual(len(captions), 3)
            self.assertEqual({row["join_index"] for row in captions}, {"2"})
            self.assertTrue(all("join 002" in row["caption"] for row in captions))
            self.assertIn("before f78", captions[0]["caption"])
            self.assertIn("AUTO-QC", captions[0]["caption"])
            self.assertIn("margin<min", captions[0]["caption"])


class ManualJoinQCApprovalTests(unittest.TestCase):
    def test_approval_is_bound_to_the_exact_manual_review_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "auto_qc.summary.json"
            approval = root / "auto_qc.manual_approval.json"
            summary.write_text(json.dumps({"decision": "manual_review_required"}) + "\n")
            (root / "auto_qc.flagged_joins.csv").write_text("join_index\n2\n")
            review_video = root / "qc_roll_flagged_joins.mp4"
            review_video.write_bytes(b"review-video")
            (root / "qc_roll_flagged_joins.captions.csv").write_text(
                "join_index,caption\n2,flagged\n"
            )

            approve_manual_join_qc.create_approval(
                summary,
                approval,
                reviewer="test-reviewer",
                note="join 2 inspected",
            )
            valid, message = approve_manual_join_qc.validate_approval(summary, approval)
            self.assertTrue(valid, message)

            review_video.write_bytes(b"changed-review-video")
            valid, message = approve_manual_join_qc.validate_approval(summary, approval)
            self.assertFalse(valid)
            self.assertIn("review artifact review_video has changed", message)

            summary.write_text(
                json.dumps(
                    {
                        "decision": "manual_review_required",
                        "changed": True,
                    }
                )
                + "\n"
            )
            valid, message = approve_manual_join_qc.validate_approval(summary, approval)
            self.assertFalse(valid)
            self.assertIn("stale", message)

    def test_auto_pass_report_cannot_receive_manual_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "auto_qc.summary.json"
            summary.write_text(json.dumps({"decision": "auto_pass"}) + "\n")
            with self.assertRaisesRegex(ValueError, "only valid"):
                approve_manual_join_qc.create_approval(
                    summary,
                    root / "approval.json",
                    reviewer="test-reviewer",
                    note="",
                )


class AutomaticJoinQCTests(unittest.TestCase):
    def make_segments(self) -> dict[int, auto_qc_segment_joins.Segment]:
        return {
            segment_id: auto_qc_segment_joins.Segment(
                segment_id=segment_id,
                source_video=None,
                start_frame_idx=segment_id * 10,
                end_frame_idx=segment_id * 10 + 9,
                duration_frames=10,
            )
            for segment_id in range(3)
        }

    def make_frames(self) -> dict[int, bytes]:
        return {
            0: bytes([0]),
            9: bytes([9]),
            10: bytes([10]),
            19: bytes([19]),
            20: bytes([20]),
            29: bytes([29]),
        }

    def test_smooth_unambiguous_joins_auto_pass(self) -> None:
        scores = auto_qc_segment_joins.score_joins(
            self.make_segments(),
            [0, 1, 2],
            self.make_frames(),
            auto_qc_segment_joins.DetectorMetadata(
                comparison_width=1,
                comparison_height=1,
                distance_median=1.0,
                distance_mad=1.0,
            ),
            reported_frame_count=0,
            max_robust_z=15.0,
            min_margin_ratio=2.0,
            require_rank1=True,
        )
        self.assertEqual(len(scores), 2)
        self.assertTrue(all(score.decision == "auto_pass" for score in scores))
        self.assertTrue(all(score.selected_rank == 1 for score in scores))

    def test_wrong_order_and_missing_frames_fail_conservatively(self) -> None:
        scores = auto_qc_segment_joins.score_joins(
            self.make_segments(),
            [0, 2, 1],
            self.make_frames(),
            auto_qc_segment_joins.DetectorMetadata(
                comparison_width=1,
                comparison_height=1,
                distance_median=1.0,
                distance_mad=1.0,
            ),
            reported_frame_count=0,
            max_robust_z=15.0,
            min_margin_ratio=2.0,
            require_rank1=True,
        )
        self.assertEqual(scores[0].decision, "manual_review_required")
        self.assertIn("selected_successor_not_rank1", scores[0].reasons)

        missing = dict(self.make_frames())
        del missing[20]
        scores = auto_qc_segment_joins.score_joins(
            self.make_segments(),
            [0, 1, 2],
            missing,
            auto_qc_segment_joins.DetectorMetadata(
                comparison_width=1,
                comparison_height=1,
                distance_median=1.0,
                distance_mad=1.0,
            ),
            reported_frame_count=0,
            max_robust_z=15.0,
            min_margin_ratio=2.0,
            require_rank1=True,
        )
        self.assertTrue(
            all(score.decision == "manual_review_required" for score in scores)
        )
        self.assertTrue(
            all("incomplete_successor_candidate_scores" in score.reasons for score in scores)
        )

    def test_successor_rank_uses_only_segments_still_available_at_that_step(self) -> None:
        frames = self.make_frames()
        frames[19] = bytes([1])
        scores = auto_qc_segment_joins.score_joins(
            self.make_segments(),
            [0, 1, 2],
            frames,
            auto_qc_segment_joins.DetectorMetadata(
                comparison_width=1,
                comparison_height=1,
                distance_median=9.0,
                distance_mad=1.0,
            ),
            reported_frame_count=0,
            max_robust_z=15.0,
            min_margin_ratio=2.0,
            require_rank1=True,
        )
        self.assertEqual(scores[1].possible_successor_count, 1)
        self.assertEqual(scores[1].selected_rank, 1)
        self.assertEqual(scores[1].decision, "auto_pass")

    def test_nominal_terminal_frame_matches_reassembler_skip(self) -> None:
        segment = self.make_segments()[2]
        self.assertEqual(
            auto_qc_segment_joins.actual_segment_end(
                segment,
                reported_frame_count=30,
            ),
            28,
        )

    def test_zero_detector_mad_routes_joins_to_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata = Path(tmpdir) / "metadata.json"
            metadata.write_text(
                json.dumps(
                    {
                        "comparison_width": 128,
                        "comparison_height": 117,
                        "distance_median": 2.0,
                        "distance_mad": 0.0,
                    }
                )
            )
            loaded = auto_qc_segment_joins.load_detector_metadata(metadata)
            scores = auto_qc_segment_joins.score_joins(
                self.make_segments(),
                [0, 1, 2],
                self.make_frames(),
                loaded,
                reported_frame_count=0,
                max_robust_z=15.0,
                min_margin_ratio=2.0,
                require_rank1=True,
            )
            self.assertTrue(
                all(score.decision == "manual_review_required" for score in scores)
            )
            self.assertTrue(
                all("detector_mad_not_positive" in score.reasons for score in scores)
            )

    def test_cli_run_writes_both_csvs_and_summary(self) -> None:
        source = Path(__file__).parents[1] / "data/raw/start04_sample_5s.mp4"
        info = detect_video_discontinuities.probe_video(source)
        width, height = detect_video_discontinuities.comparison_size(info, 64)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            segments = root / "segments.csv"
            order = root / "order.csv"
            metadata = root / "metadata.json"
            out = root / "review"
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
                        "segment_id": 0,
                        "source_video": source,
                        "start_frame_idx": 0,
                        "end_frame_idx": 39,
                        "duration_frames": 40,
                    },
                    {
                        "segment_id": 1,
                        "source_video": source,
                        "start_frame_idx": 40,
                        "end_frame_idx": 79,
                        "duration_frames": 40,
                    },
                    {
                        "segment_id": 2,
                        "source_video": source,
                        "start_frame_idx": 80,
                        "end_frame_idx": 119,
                        "duration_frames": 40,
                    },
                ],
            )
            write_csv(
                order,
                ["order", "segment_id"],
                [
                    {"order": 0, "segment_id": 0},
                    {"order": 1, "segment_id": 1},
                    {"order": 2, "segment_id": 2},
                ],
            )
            metadata.write_text(
                json.dumps(
                    {
                        "comparison_width": width,
                        "comparison_height": height,
                        "distance_median": 2.0,
                        "distance_mad": 1.0,
                    }
                )
            )
            args = auto_qc_segment_joins.parse_args(
                [
                    str(source),
                    "--segments",
                    str(segments),
                    "--order-csv",
                    str(order),
                    "--detector-metadata",
                    str(metadata),
                    "--out-dir",
                    str(out),
                    "--progress-every-frames",
                    "0",
                    "--progress-every-seconds",
                    "0",
                ]
            )
            summary = auto_qc_segment_joins.run(args)

            self.assertEqual(summary["counts"]["joins_expected"], 2)
            self.assertTrue((out / "auto_qc.join_scores.csv").is_file())
            self.assertTrue((out / "auto_qc.flagged_joins.csv").is_file())
            self.assertTrue((out / "auto_qc.summary.json").is_file())
            self.assertFalse(list(root.rglob("*.partial")))

            valid, message = auto_qc_segment_joins.validate_summary_inputs(
                out / "auto_qc.summary.json",
                source,
                segments,
                order,
                metadata,
            )
            self.assertTrue(valid, message)
            write_csv(
                order,
                ["order", "segment_id"],
                [
                    {"order": 0, "segment_id": 0},
                    {"order": 1, "segment_id": 2},
                    {"order": 2, "segment_id": 1},
                ],
            )
            valid, message = auto_qc_segment_joins.validate_summary_inputs(
                out / "auto_qc.summary.json",
                source,
                segments,
                order,
                metadata,
            )
            self.assertFalse(valid)
            self.assertIn("order_csv: content hash changed", message)


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


class CurrentArtifactsManifestTests(unittest.TestCase):
    def test_manifest_lists_all_other_files_and_marks_large_files_unhashed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            staging = root / "staging"
            staging.mkdir()
            summary = staging / "auto_qc.summary.json"
            summary.write_text(json.dumps({"decision": "auto_pass"}) + "\n")
            (staging / "small.bin").write_bytes(b"s" * 64)
            (staging / "large.mp4").write_bytes(b"v" * 65)
            nested = staging / "metadata"
            nested.mkdir()
            (nested / "run.json").write_text("{}\n")
            completion = root / ".reassemble.complete"
            completion.write_text("v3|outputs=complete\n")
            (staging / write_current_artifacts_manifest.MANIFEST_NAME).write_text(
                '{"stale": true}\n'
            )

            output = write_current_artifacts_manifest.write_manifest_atomically(
                staging,
                key="start47_20190731_184423_side1_top",
                auto_qc_summary=summary,
                reassembly_completion=completion,
                hash_threshold_bytes=64,
            )
            manifest = json.loads(output.read_text())
            entries = {entry["path"]: entry for entry in manifest["files"]}

            self.assertEqual(
                set(entries),
                {
                    "auto_qc.summary.json",
                    "large.mp4",
                    "metadata/run.json",
                    "small.bin",
                },
            )
            self.assertEqual(entries["small.bin"]["hash_status"], "sha256")
            self.assertEqual(
                entries["large.mp4"]["hash_status"],
                "unhashed",
            )
            self.assertIsNone(entries["large.mp4"]["sha256"])
            self.assertEqual(manifest["auto_qc_decision"], "auto_pass")
            self.assertEqual(
                manifest["auto_qc_summary_sha256"],
                write_current_artifacts_manifest.sha256_file(summary),
            )
            self.assertEqual(
                manifest["reassembly_completion_sha256"],
                write_current_artifacts_manifest.sha256_file(completion),
            )
            self.assertIn("non-deleting", manifest["supersession_notice"])
            self.assertIn(
                "except for CURRENT_ARTIFACTS.json itself",
                manifest["supersession_notice"],
            )
            self.assertIn("not listed in files", manifest["supersession_notice"])
            self.assertIn("superseded", manifest["supersession_notice"])
            self.assertFalse(list(staging.glob("*.partial")))

    def test_invalid_summary_json_does_not_replace_existing_manifest(self) -> None:
        invalid_summaries = {
            "duplicate": (
                '{"decision":"auto_pass",'
                '"decision":"manual_review_required"}\n'
            ),
            "nonfinite": '{"decision":"auto_pass","score":NaN}\n',
        }
        for label, summary_text in invalid_summaries.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                staging = root / "staging"
                staging.mkdir()
                summary = staging / "auto_qc.summary.json"
                summary.write_text(summary_text)
                completion = root / ".reassemble.complete"
                completion.write_text("v3|outputs=complete\n")
                output = (
                    staging / write_current_artifacts_manifest.MANIFEST_NAME
                )
                output.write_text("existing manifest\n")

                with self.assertRaisesRegex(
                    ValueError,
                    "Duplicate JSON key|Non-finite JSON constant",
                ):
                    write_current_artifacts_manifest.write_manifest_atomically(
                        staging,
                        key="start47_side1_top",
                        auto_qc_summary=summary,
                        reassembly_completion=completion,
                    )
                self.assertEqual(output.read_text(), "existing manifest\n")
                self.assertFalse(list(staging.glob("*.partial")))


class CompletionMarkerTests(unittest.TestCase):
    def test_unreviewed_pilot_root_requires_bound_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temporary = Path(tmpdir)
            scratch = temporary / "scratch"
            pilot_id = "start01_start02_side0_top_v1"
            pilot_root = scratch / "artifacts/resequence_pilots" / pilot_id
            pilot_root.mkdir(parents=True)
            revision = "0123456789abcdef0123456789abcdef01234567"
            bucket = "hf://buckets/test/honey-bee"
            reseq_prefix = f"{bucket}/resequenced"
            pilot_prefix = f"{reseq_prefix}/pilots/{pilot_id}"
            (pilot_root / ".unreviewed_pilot_root").write_text(
                f"v1|pilot_id={pilot_id}|git_revision={revision}|"
                f"hf_prefix={pilot_prefix}\n"
            )
            repository = Path(__file__).parents[1]
            script = r"""
set -eu
export HIVE_VIDEO_ROOT="$1"
export SCRATCH_ROOT="$2"
export RESEQ_ROOT="$3"
export HF_BUCKET="$4"
export HF_RESEQ_PREFIX="$5"
export HF_PILOT_PREFIX="$6"
export E2E_PILOT_ID="$7"
export E2E_EXPECTED_GIT_REVISION="$8"
source "${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence/common.sh"
hv_require_pilot_context_if_set
hv_require_pilot_root_for_path "${RESEQ_ROOT}"
"""
            command = [
                "bash",
                "-c",
                script,
                "bash",
                str(repository),
                str(scratch),
                str(pilot_root),
                bucket,
                reseq_prefix,
                pilot_prefix,
                pilot_id,
                revision,
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)

            misrouted_release = command.copy()
            misrouted_release[8] = pilot_prefix
            result = subprocess.run(
                misrouted_release, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("canonical resequenced prefix", result.stderr)

            wrong_evidence = command.copy()
            wrong_evidence[9] = f"{reseq_prefix}/pilots/wrong"
            result = subprocess.run(wrong_evidence, capture_output=True, text=True)
            self.assertEqual(result.returncode, 4)
            self.assertIn("tracked evidence prefix", result.stderr)

            unbound_script = script.replace(
                'export E2E_PILOT_ID="$7"',
                "unset E2E_PILOT_ID",
            )
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    unbound_script,
                    *command[3:],
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("require their tracked pilot context", result.stderr)

    def test_v2_unreviewed_pilot_root_is_allowed_but_untracked_id_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temporary = Path(tmpdir)
            scratch = temporary / "scratch"
            pilot_id = "start01_start02_side0_top_v2"
            pilot_root = scratch / "artifacts/resequence_pilots" / pilot_id
            pilot_root.mkdir(parents=True)
            revision = "0123456789abcdef0123456789abcdef01234567"
            bucket = "hf://buckets/test/honey-bee"
            reseq_prefix = f"{bucket}/resequenced"
            pilot_prefix = f"{reseq_prefix}/pilots/{pilot_id}"
            (pilot_root / ".unreviewed_pilot_root").write_text(
                f"v1|pilot_id={pilot_id}|git_revision={revision}|"
                f"hf_prefix={pilot_prefix}\n"
            )
            repository = Path(__file__).parents[1]
            script = r"""
set -eu
export HIVE_VIDEO_ROOT="$1"
export SCRATCH_ROOT="$2"
export RESEQ_ROOT="$3"
export HF_BUCKET="$4"
export HF_RESEQ_PREFIX="$5"
export HF_PILOT_PREFIX="$6"
export E2E_PILOT_ID="$7"
export E2E_EXPECTED_GIT_REVISION="$8"
source "${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence/common.sh"
hv_require_pilot_context_if_set
hv_require_pilot_root_for_path "${RESEQ_ROOT}"
"""
            command = [
                "bash",
                "-c",
                script,
                "bash",
                str(repository),
                str(scratch),
                str(pilot_root),
                bucket,
                reseq_prefix,
                pilot_prefix,
                pilot_id,
                revision,
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)

            command[-2] = "start01_start02_side0_top_v3"
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 4)
            self.assertIn("Unexpected E2E_PILOT_ID", result.stderr)

    def test_stage1a_cut_review_status_is_bound_to_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repository = Path(__file__).parents[1]
            script = r"""
set -eu
export HIVE_VIDEO_ROOT="$1"
source "${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence/common.sh"
hv_stage1a_cut_review_status "$2"
"""
            for expected in (
                "edited_verified",
                "inspected",
                "unreviewed_pilot",
            ):
                marker = root / f"{expected}.complete"
                marker.write_text(
                    f"v3|cuts_file=cuts.csv|cuts=1:2|"
                    f"cut_review_status={expected}|segments=fixture\n"
                )
                result = subprocess.run(
                    [
                        "bash",
                        "-c",
                        script,
                        "bash",
                        str(repository),
                        str(marker),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.stdout.strip(), expected)

            invalid = root / "invalid.complete"
            invalid.write_text("v2|cuts_file=cuts.csv|cuts=1:2\n")
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    script,
                    "bash",
                    str(repository),
                    str(invalid),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("no recognized cut-review status", result.stderr)

    def test_generated_output_mutation_invalidates_completion_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scores = root / "auto_qc.join_scores.csv"
            flagged = root / "auto_qc.flagged_joins.csv"
            summary = root / "auto_qc.summary.json"
            marker = root / ".auto_qc.complete"
            scores.write_text("join_index,decision\n1,auto_pass\n")
            flagged.write_text("join_index,decision\n")
            summary.write_text('{"decision":"auto_pass"}\n')
            script = r"""
set -eu
export HIVE_VIDEO_ROOT="$1"
source "${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence/common.sh"
marker="$2"
scores="$3"
flagged="$4"
summary="$5"
original="inputs|outputs=$(hv_file_bundle_fingerprint \
  "${scores}" "${flagged}" "${summary}")"
hv_mark_complete "${marker}" "${original}"
if hv_step_needed "${marker}" "${original}" "${scores}" "${flagged}" "${summary}"; then
  echo "unchanged output bundle was not reusable" >&2
  exit 10
fi
printf 'tampered\n' >>"${summary}"
mutated="inputs|outputs=$(hv_file_bundle_fingerprint \
  "${scores}" "${flagged}" "${summary}")"
if ! hv_step_needed "${marker}" "${mutated}" "${scores}" "${flagged}" "${summary}"; then
  echo "mutated output bundle was incorrectly reusable" >&2
  exit 11
fi
"""
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    script,
                    "bash",
                    str(Path(__file__).parents[1]),
                    str(marker),
                    str(scores),
                    str(flagged),
                    str(summary),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("inputs changed; rerunning step", result.stdout)


class EndToEndPilotLauncherTests(unittest.TestCase):
    def test_pipeline_sample_is_fail_closed_and_records_resources(self) -> None:
        repository = Path(__file__).parents[1]
        script_dir = repository / "src/pipeline/slurm/resequence"
        sample = script_dir / "resequence_pipeline_sample.sh"
        text = sample.read_text()
        self.assertTrue(os.access(sample, os.X_OK))

        result = subprocess.run(
            ["bash", str(sample)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("fail-closed", result.stderr)

        for resource in (
            'DOWNLOAD_MEM="4GB"',
            'STAGE1_MEM="32GB"',
            'STAGE1A_MEM="32GB"',
            'STAGE2_MEM="192GB"',
            'ARCHIVAL_UPLOAD_MEM="16GB"',
            'COMPRESSION_MEM="8GB"',
            'COMPRESSED_UPLOAD_MEM="4GB"',
        ):
            self.assertIn(resource, text)
        self.assertIn('--dependency="aftercorr:${DOWNLOAD_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${STAGE1_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${STAGE1A_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${STAGE2_JOB}"', text)
        self.assertIn('--array="${ARRAY_RANGE}%1"', text)
        self.assertIn('scontrol release "${DOWNLOAD_JOB}"', text)
        for readme in (
            repository / "README.md",
            repository / "src/resequence/README.md",
        ):
            self.assertIn("resequence_pipeline_sample.sh", readme.read_text())

    def test_launcher_fixes_inputs_dependencies_and_pilot_destination(self) -> None:
        repository = Path(__file__).parents[1]
        launcher = (
            repository
            / "src/pipeline/slurm/resequence/"
            "submit_start01_start02_side0_top_e2e.sh"
        )
        text = launcher.read_text()
        self.assertIn('LOCATORS="start1_side0_top start2_side0_top"', text)
        self.assertIn('CUT_REVIEW_STATUS="unreviewed_pilot"', text)
        self.assertIn('E2E_PILOT_QUALITY="low"', text)
        self.assertIn('PILOT_ID="start01_start02_side0_top_v1"', text)
        self.assertIn(
            'RESEQ_ROOT="${SCRATCH_ROOT}/artifacts/resequence_pilots/'
            '${TRACKED_PILOT_ID}"',
            text,
        )
        self.assertIn('HF_RESEQ_PREFIX="${HF_BUCKET}/resequenced"', text)
        self.assertIn(
            'HF_PILOT_PREFIX="${HF_RESEQ_PREFIX}/pilots/${PILOT_ID}"', text
        )
        self.assertIn(
            'COMMON_EXPORT="${COMMON_EXPORT},HF_PILOT_PREFIX=${HF_PILOT_PREFIX}"',
            text,
        )
        self.assertIn('--dependency="aftercorr:${DOWNLOAD_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${STAGE1_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${STAGE1A_JOB}"', text)
        self.assertIn('--array="${ARRAY_RANGE}%1"', text)
        self.assertIn("resequence_e2e_stage2_gate_array.sh", text)

    def test_v2_launcher_binds_tls_probe_and_failed_v1_provenance(self) -> None:
        repository = Path(__file__).parents[1]
        launcher = (
            repository / "src/pipeline/slurm/resequence/submit_start01_start02_side0_top_e2e_v2.sh"
        )
        text = launcher.read_text()
        self.assertIn('TRACKED_PILOT_ID="start01_start02_side0_top_v2"', text)
        self.assertIn('PRIOR_PILOT_ID="start01_start02_side0_top_v1"', text)
        self.assertIn('PRIOR_DOWNLOAD_JOB="59712692"', text)
        self.assertIn(
            'PRIOR_GIT_REVISION="86cad78be24f81590ed47cd639c71ed76551a0f0"',
            text,
        )
        self.assertIn('SOL_CA_BUNDLE="/etc/pki/tls/certs/ca-bundle.crt"', text)
        self.assertIn("--probe-only", text)
        self.assertIn("--refresh-manifest", text)
        self.assertIn("verified_tls_chain_fix", text)
        self.assertIn("PRIOR_SUBMISSION_SHA256", text)
        self.assertIn("prior_submission_sha256", text)
        self.assertIn("prior_v1_root_marker.txt", text)
        self.assertIn("prior_v1_submission.tsv", text)
        self.assertIn("squeue -h -u pdressla -o '%A'", text)
        self.assertIn("submission.step00.tsv", text)
        self.assertIn("submission.step04.tsv", text)
        self.assertIn('publish_submission_record "${PLAN_DIR}/submission.tsv"', text)
        self.assertIn("src/utils/verify_bucket_listing.py", text)
        self.assertIn("--hold", text)
        self.assertIn('scontrol release "${DOWNLOAD_JOB}"', text)
        self.assertIn('LOCATORS="start1_side0_top start2_side0_top"', text)
        self.assertIn('CUT_REVIEW_STATUS="unreviewed_pilot"', text)
        self.assertIn('E2E_PILOT_QUALITY="low"', text)
        self.assertIn('HF_RESEQ_PREFIX="${HF_BUCKET}/resequenced"', text)
        self.assertIn(
            'HF_PILOT_PREFIX="${HF_RESEQ_PREFIX}/pilots/${PILOT_ID}"', text
        )
        self.assertIn(
            'COMMON_EXPORT="${COMMON_EXPORT},HF_PILOT_PREFIX=${HF_PILOT_PREFIX}"',
            text,
        )
        self.assertIn('--dependency="aftercorr:${DOWNLOAD_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${STAGE1_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${STAGE1A_JOB}"', text)
        self.assertLess(
            text.index(
                'publish_submission_record "${SUBMISSION_PARTIAL}" '
                '"submission.step00.tsv"'
            ),
            text.index('DOWNLOAD_JOB="$(sbatch --parsable'),
        )
        self.assertLess(
            text.index('publish_submission_record "${PLAN_DIR}/submission.tsv"'),
            text.index('scontrol release "${DOWNLOAD_JOB}"'),
        )

    def test_start03_start38_launcher_fixes_four_video_pilot(self) -> None:
        repository = Path(__file__).parents[1]
        script_dir = repository / "src/pipeline/slurm/resequence"
        launcher = (
            script_dir / "submit_start03_start38_both_sides_top_e2e_v1.sh"
        )
        text = launcher.read_text()
        self.assertIn(
            'TRACKED_PILOT_ID="start03_start38_both_sides_top_v1"', text
        )
        self.assertIn(
            'LOCATORS="start3_side0_top start3_side1_top '
            'start38_side0_top start38_side1_top"',
            text,
        )
        for key in (
            "start03_20190608_181426_side0_top",
            "start03_20190608_181426_side1_top",
            "start38_20190722_200917_side0_top",
            "start38_20190722_200917_side1_top",
        ):
            self.assertIn(key, text)
        self.assertIn('ARRAY_RANGE="0-3"', text)
        self.assertIn('CUT_REVIEW_STATUS="unreviewed_pilot"', text)
        self.assertIn('E2E_PILOT_QUALITY="low"', text)
        self.assertIn('SOL_CA_BUNDLE="/etc/pki/tls/certs/ca-bundle.crt"', text)
        self.assertIn("--probe-only", text)
        self.assertIn("--refresh-manifest", text)
        self.assertIn(
            'RESEQ_ROOT="${SCRATCH_ROOT}/artifacts/resequence_pilots/'
            '${TRACKED_PILOT_ID}"',
            text,
        )
        self.assertIn('HF_RESEQ_PREFIX="${HF_BUCKET}/resequenced"', text)
        self.assertIn(
            'HF_PILOT_PREFIX="${HF_RESEQ_PREFIX}/pilots/${PILOT_ID}"', text
        )
        self.assertIn("hf_pilot_prefix", text)
        self.assertIn("hf_reseq_prefix", text)
        self.assertIn(
            'COMMON_EXPORT="${COMMON_EXPORT},HF_PILOT_PREFIX=${HF_PILOT_PREFIX}"',
            text,
        )
        self.assertIn("submission.step00.tsv", text)
        self.assertIn("submission.step04.tsv", text)
        self.assertIn("src/utils/verify_bucket_listing.py", text)
        self.assertIn("--hold", text)
        self.assertIn('scontrol release "${DOWNLOAD_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${DOWNLOAD_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${STAGE1_JOB}"', text)
        self.assertIn('--dependency="aftercorr:${STAGE1A_JOB}"', text)
        self.assertIn('--array="${ARRAY_RANGE}%1"', text)
        self.assertNotIn("PRIOR_PILOT_ID", text)

        common_text = (script_dir / "common.sh").read_text()
        gate_text = (script_dir / "resequence_e2e_stage2_gate_array.sh").read_text()
        self.assertIn("start03_start38_both_sides_top_v1", common_text)
        self.assertIn("start03_start38_both_sides_top_v1", gate_text)
        self.assertIn(
            'EXPECTED_LOCATORS="start3_side0_top start3_side1_top '
            'start38_side0_top start38_side1_top"',
            gate_text,
        )
        self.assertIn(
            'REMOTE="${HF_PILOT_PREFIX}/stage1a/reseq_${RESEQ_KEY}"',
            gate_text,
        )

        upload_text = (script_dir / "resequence_upload.sh").read_text()
        compression_text = (
            script_dir / "compress_resequenced_upload.sh"
        ).read_text()
        self.assertIn("#SBATCH --mem=16GB", upload_text)
        self.assertIn('REMOTE="${HF_RESEQ_PREFIX}/reseq_${KEY}"', upload_text)
        self.assertIn(
            'REMOTE="${HF_RESEQ_PREFIX}/compressed/reseq_${KEY}/${QUALITY}"',
            compression_text,
        )

    def test_launcher_rejects_arguments_and_environment_overrides(self) -> None:
        repository = Path(__file__).parents[1]
        for name in (
            "submit_start01_start02_side0_top_e2e.sh",
            "submit_start01_start02_side0_top_e2e_v2.sh",
            "submit_start03_start38_both_sides_top_e2e_v1.sh",
        ):
            launcher = repository / "src/pipeline/slurm/resequence" / name
            with self.subTest(launcher=name):
                with_argument = subprocess.run(
                    ["bash", str(launcher), "start3"],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(with_argument.returncode, 2)
                self.assertIn("zero-argument tracked launcher", with_argument.stderr)

                inherited = subprocess.run(
                    ["bash", str(launcher)],
                    env={"PATH": "/usr/bin:/bin", "FORCE": "1"},
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(inherited.returncode, 2)
                self.assertIn("inherited pipeline override: FORCE", inherited.stderr)


class EndToEndStage2GateTests(unittest.TestCase):
    def run_gate(
        self,
        root: Path,
        decision: str,
        *,
        pilot_id: str = "start01_start02_side0_top_v1",
        locators: str = "start1_side0_top start2_side0_top",
    ) -> tuple[subprocess.CompletedProcess[str], list[str], Path]:
        repository = Path(__file__).parents[1]
        script_dir = root / "src/pipeline/slurm/resequence"
        script_dir.mkdir(parents=True)
        gate = script_dir / "resequence_e2e_stage2_gate_array.sh"
        gate.write_text(
            (
                repository
                / "src/pipeline/slurm/resequence/"
                "resequence_e2e_stage2_gate_array.sh"
            ).read_text()
        )

        work = root / "work"
        qc = work / "qc"
        segments = work / "segments"
        order = work / "order"
        review = work / "review"
        for directory in (qc, segments, order, review):
            directory.mkdir(parents=True)
        for path in (
            work / "raw.mp4",
            qc / "cut_review.proposed.csv",
            qc / "metadata.json",
            qc / "candidates.csv",
            qc / "jump_events.csv",
            segments / "segments.csv",
            order / "ranked_edges.csv",
            order / "greedy_order.csv",
            review / "auto_qc.join_scores.csv",
            review / "auto_qc.flagged_joins.csv",
        ):
            path.write_text("fixture\n")
        (review / "auto_qc.summary.json").write_text(
            json.dumps({"decision": decision}) + "\n"
        )
        (review / ".auto_qc.complete").write_text("inputs|outputs=bundle\n")
        (review / ".stage1a.complete").write_text(
            "v3|cuts_file=cut_review.proposed.csv|cuts=fp|"
            "cut_review_status=unreviewed_pilot|"
            "git_revision=0123456789abcdef0123456789abcdef01234567|"
            "auto_qc_report=fp|auto_qc_bundle=fp|review=fixture\n"
        )
        if decision == "manual_review_required":
            (review / "qc_roll_flagged_joins.mp4").write_text("video\n")
            (review / "qc_roll_flagged_joins.captions.csv").write_text(
                "caption\n"
            )

        common = script_dir / "common.sh"
        common.write_text(
            r"""
set -eu
HF_BUCKET="${HF_BUCKET}"
HF_RESEQ_PREFIX="${HF_RESEQ_PREFIX}"
HF_PILOT_PREFIX="${HF_PILOT_PREFIX}"
hv_sync_env() { :; }
hv_locator_for_task() { printf '%s\n' "${1%% *}"; }
hv_resolve() {
  RESEQ_KEY="start01_20190606_190340_side0_top"
  RESEQ_PATH="${PILOT_FIXTURE_WORK}/raw.mp4"
  HV_WORK_DIR="${PILOT_FIXTURE_WORK}"
  HV_QC_DIR="${HV_WORK_DIR}/qc"
  HV_SEG_DIR="${HV_WORK_DIR}/segments"
  HV_ORDER_DIR="${HV_WORK_DIR}/order"
  HV_REVIEW_DIR="${HV_WORK_DIR}/review"
  HV_OUT_DIR="${HV_WORK_DIR}/output"
}
hv_require_file() {
  if [ ! -f "$1" ]; then
    echo "missing: $1" >&2
    exit 4
  fi
}
hv_stage1a_cut_review_status() {
  case "$(cat "$1")" in
    *"|cut_review_status=unreviewed_pilot|"*) printf '%s\n' unreviewed_pilot ;;
    *"|cut_review_status=inspected|"*) printf '%s\n' inspected ;;
    *) exit 4 ;;
  esac
}
hv_file_bundle_fingerprint() { printf '%s\n' bundle; }
hv_file_fingerprint() { printf '%s\n' fp; }
"""
        )
        (script_dir / "resequence_stage2_array.sh").write_text(
            '#!/bin/bash\nprintf "stage2\\n" >>"${PILOT_EVENT_LOG}"\n'
        )
        (script_dir / "compress_resequenced_array.sh").write_text(
            "#!/bin/bash\nexit 0\n"
        )

        bin_dir = root / "bin"
        bin_dir.mkdir()
        event_log = root / "events.log"
        fake_uv = bin_dir / "uv"
        fake_uv.write_text(
            f"""#!{sys.executable}
import json
import os
import pathlib
import sys

args = sys.argv[1:]
with open(os.environ["PILOT_EVENT_LOG"], "a") as handle:
    handle.write("uv " + json.dumps(args) + "\\n")
if len(args) >= 5 and args[0:3] == ["run", "--no-sync", "python"]:
    code = args[4] if args[3] == "-c" else ""
    if "json.load" in code and "decision" in code:
        summary = pathlib.Path(args[-1])
        print(json.loads(summary.read_text())["decision"])
elif "hf" in args and "buckets" in args and "list" in args:
    print("[]")
elif "hf" in args and "auth" in args and "whoami" in args:
    print("{{}}")
"""
        )
        fake_uv.chmod(0o755)
        fake_git = bin_dir / "git"
        fake_git.write_text(
            f"""#!{sys.executable}
import sys
if sys.argv[1:3] == ["rev-parse", "HEAD"]:
    print("0123456789abcdef0123456789abcdef01234567")
else:
    raise SystemExit(2)
"""
        )
        fake_git.chmod(0o755)
        fake_sbatch = bin_dir / "sbatch"
        fake_sbatch.write_text(
            f"""#!{sys.executable}
import json
import os
import sys
with open(os.environ["PILOT_EVENT_LOG"], "a") as handle:
    handle.write("sbatch " + json.dumps(sys.argv[1:]) + "\\n")
print("92001;sol")
"""
        )
        fake_sbatch.chmod(0o755)

        environment = dict(os.environ)
        environment.update(
            {
                "PATH": f"{bin_dir}:{environment['PATH']}",
                "HIVE_VIDEO_ROOT": str(root),
                "SLURM_SUBMIT_DIR": str(root),
                "PILOT_FIXTURE_WORK": str(work),
                "PILOT_EVENT_LOG": str(event_log),
                "LOCATORS": locators,
                "E2E_PILOT_ID": pilot_id,
                "E2E_PILOT_QUALITY": "low",
                "E2E_EXPECTED_GIT_REVISION": (
                    "0123456789abcdef0123456789abcdef01234567"
                ),
                "HF_BUCKET": "hf://buckets/test/honey-bee",
                "HF_RESEQ_PREFIX": (
                    "hf://buckets/test/honey-bee/resequenced"
                ),
                "HF_PILOT_PREFIX": (
                    "hf://buckets/test/honey-bee/resequenced/pilots/"
                    f"{pilot_id}"
                ),
                "HF_TOKEN": "test-only",
                "SLURM_ARRAY_JOB_ID": "900",
                "SLURM_ARRAY_TASK_ID": "0",
                "SLURM_JOB_ID": "901",
            }
        )
        result = subprocess.run(
            ["bash", str(gate)],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
        )
        events = event_log.read_text().splitlines()
        return result, events, work

    def test_start03_start38_pilot_mapping_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result, events, _work = self.run_gate(
                Path(tmpdir),
                "manual_review_required",
                pilot_id="start03_start38_both_sides_top_v1",
                locators=(
                    "start3_side0_top start3_side1_top "
                    "start38_side0_top start38_side1_top"
                ),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(any(event == "stage2" for event in events))

    def test_manual_review_is_filed_and_stops_without_stage2(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result, events, work = self.run_gate(
                Path(tmpdir),
                "manual_review_required",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(any(event == "stage2" for event in events))
            self.assertFalse(any(event.startswith("sbatch ") for event in events))
            sync_index = next(
                index
                for index, event in enumerate(events)
                if event.startswith("uv ") and '"sync"' in event
            )
            commit_index = next(
                index
                for index, event in enumerate(events)
                if event.startswith("uv ")
                and '"cp"' in event
                and "CURRENT_STAGE1A.json" in event
            )
            self.assertLess(sync_index, commit_index)
            self.assertIn(
                "hf://buckets/test/honey-bee/resequenced/pilots/"
                "start01_start02_side0_top_v1/stage1a/",
                events[sync_index],
            )
            staging = work / "e2e_pilot_stage1a_upload"
            self.assertTrue((staging / "qc_roll_flagged_joins.mp4").is_file())
            self.assertTrue(
                (staging / "qc_roll_flagged_joins.captions.csv").is_file()
            )
            self.assertIn("No Stage 2 render", result.stdout)

    def test_auto_pass_is_filed_before_stage2_and_compression(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result, events, work = self.run_gate(Path(tmpdir), "auto_pass")
            self.assertEqual(result.returncode, 0, result.stderr)
            stage2_index = events.index("stage2")
            commit_index = next(
                index
                for index, event in enumerate(events)
                if event.startswith("uv ")
                and '"cp"' in event
                and "CURRENT_STAGE1A.json" in event
            )
            sbatch_index = next(
                index
                for index, event in enumerate(events)
                if event.startswith("sbatch ")
            )
            self.assertLess(commit_index, stage2_index)
            self.assertLess(stage2_index, sbatch_index)
            submission = events[sbatch_index]
            self.assertIn('"--array=0-0"', submission)
            self.assertIn('"--dependency=afterok:901"', submission)
            self.assertIn("LOCATORS=start1_side0_top,QUALITY=low", submission)
            staging = work / "e2e_pilot_stage1a_upload"
            self.assertFalse((staging / "qc_roll_flagged_joins.mp4").exists())


if __name__ == "__main__":
    unittest.main()
