# Resequencing

These scripts repair shuffled hive videos by detecting visual discontinuities,
turning those discontinuities into source segments, ordering the segments, and
rendering a captioned review video. They are written as command-line tools and
are intended to be run from the `hive_video/` directory with `uv run python`.

## Quickstart

Run the cluster commands from the `hive_video/` checkout on Sol. The default
arrays process the established Start 04 side 1 and Start 47 sides 0 and 1
videos. Each `sbatch` below is a separate job: wait for it to succeed before
submitting the next stage.

```bash
cd ~/workspace/honey-bee-behavior/hive_video

sbatch src/pipeline/slurm/resequence/download_raw_array.sh
squeue -u pdressla --iterate=120

# After the downloads succeed:
sbatch src/pipeline/slurm/resequence/resequence_stage1_array.sh

# Inspect qc/candidates.csv, qc/jump_events.csv, and
# qc/cut_review.proposed.csv. Create qc/cut_review.verified.csv only if
# you change the proposed cuts. Then:
sbatch src/pipeline/slurm/resequence/resequence_stage1a_review_array.sh

# Read review/auto_qc.summary.json. If it says manual_review_required,
# inspect review/qc_roll_flagged_joins.mp4 and record approval first.
# When it says auto_pass, or the flagged roll has been approved:
sbatch src/pipeline/slurm/resequence/resequence_stage2_array.sh
```

Stage 2 renders the full-fidelity MP4 and queues its dependent upload. From a
clean checkout published at `origin/main`, use the fixed zero-argument launcher
only to reproduce the recorded Start 01 / Start 02 integration pilot; it owns
that pilot's dependencies, configuration, scratch prefix, and upload prefix:

```bash
bash src/pipeline/slurm/resequence/submit_start01_start02_side0_top_e2e_v2.sh
```

## Where things live

- `src/resequence/` contains reusable Python implementation and diagnostic
  modules. These should remain runnable outside Slurm.
- `src/pipeline/slurm/resequence/` contains all cluster orchestration for this
  workflow: job arrays, smoke tests, upload and compression jobs, and versioned
  parent launchers. Put additional resequencing Slurm scripts here.
- `data/qc/resequence/reseq_<key>/` contains selectively copied local review
  artifacts, organized into `qc/`, `segments/`, `order/`, and `review/`.

## Workflow details

On the cluster, the wrappers in `src/pipeline/slurm/resequence/` run the whole
sequence and resolve every path from a single locator. Source cuts are inspected
once; segment joins are sent to a human only when automatic QC flags them.

Stage 1 covers steps 1 and 2 below and prepares an editable cut table without
writing hundreds of JPEGs. Stage 1a uses the inspected proposal directly, or
`cut_review.verified.csv` when cuts were edited; it then covers steps 3 and 4
with the established trajectory-10 ordering. The automatic join diagnostic
scores every chosen boundary. Clean videos pass without a second human loop;
flagged videos receive a green-flash roll containing only the joins requiring
review, and Stage 2 requires a report-bound approval. Stage 2 then performs the
final render and upload. Completed steps and validated video parts resume safely
after a wall-clock kill. Each remote video folder carries
`CURRENT_ARTIFACTS.json`; the upload preserves older bucket objects for audit,
but publishes the manifest only after payload verification, and only its listed
files belong to the current validated run.

The fixed Start 01 / Start 02 pilot is intentionally different: it marks the
unchanged source-cut proposals as `unreviewed_pilot`, files every Stage 1a
outcome under a separate pilot prefix, and only lets auto-cleared videos
continue. The v2 launcher also proves the manifest and actual media TLS paths
with one-byte ranged GETs before submission; v1 remains the failed-attempt
record. Its outputs are integration evidence rather than validated inventory.

Compression is intentionally separate from resequencing: it creates a smaller
H.264 sharing derivative while retaining the full-fidelity resequenced MP4.
The smoke wrapper renders `high`, `medium`, and `low` samples before the array
creates and uploads only the chosen full-length profile.

Optional smoke tests, compression passes, and the one-time five-video backfill
are launched from the same directory:

```bash
sbatch src/pipeline/slurm/resequence/resequence_smoke_test.sh
sbatch src/pipeline/slurm/resequence/compress_qc_roll_smoke.sh
sbatch src/pipeline/slurm/resequence/compress_resequenced_smoke_test.sh
sbatch src/pipeline/slurm/resequence/compress_resequenced_array.sh
sbatch src/pipeline/slurm/resequence/compress_existing_low_backfill_array.sh
```

`src/pipeline/slurm/resequence/common.sh` holds the shared environment, the uv
scratch-venv locking, and `hv_resolve`, which turns a locator such as
`start47_side1_top` into the raw video path, the canonical key, and every work
directory. The full walkthrough, including how to select other files, is in the
[project README](../../README.md).

The rest of this document describes the underlying tools, which is what you
want when diagnosing a bad join or running a step by hand.

## Underlying tools

The current pipeline is:

1. `detect_video_discontinuities.py`
   Compute frame-to-frame visual distances from a raw MP4. This produces ranked
   candidate cuts and, optionally, all frame-to-frame distances or candidate
   JPEGs (`--write-candidate-frames`).

2. `summarize_jump_events.py`
   Group adjacent high-distance frame pairs into discontinuity events. This
   separates single-frame cuts from short bursts of activity around a cut.

3. `build_segments_from_jumps.py`
   Build a segment CSV from selected discontinuity events. Diagnosed exceptions
   can be made reproducible with `--extra-cut-prev-frame`.

4. `order_video_segments.py`
   Compare segment endings to segment beginnings and write candidate joins plus
   a greedy segment order. The trajectory signature is the default choice for
   the 2019 Smith archive work.

5. `reassemble_video_from_segments.py`
   Render the ordered segments into a captioned MP4. This step is restartable:
   it writes part videos, skips completed parts, and checks `.safeword` between
   parts.

6. `compress_resequenced.py`
   Make a separately named H.264 sharing copy at one of three recorded CRF
   profiles. It validates resolution, frame rate, duration, and codec before
   atomically publishing the local derivative.

## Diagnostics

The `diagnostics/` directory contains tools used to validate or review the
pipeline rather than produce the final video directly.

- `diagnostics/diagnose_segment_discontinuities.py`
  Scores frame-to-frame distances inside specified source segments or source
  frame ranges. Use this to justify any forced cuts added to segment production.

- `diagnostics/make_join_review_video.py`
  Builds short before/after clips for candidate joins or filters an exact order
  to the joins listed by automatic QC.

- `diagnostics/auto_qc_segment_joins.py`
  Scores the exact chosen boundaries with the detector feature, ranks every
  possible successor, and emits a conservative video-level `auto_pass` or
  `manual_review_required` decision.

- `diagnostics/approve_manual_join_qc.py`
  Records a manual approval whose checksums are bound to one exact flagged
  auto-QC report, flagged table, review MP4, and caption manifest, and rejects
  stale approvals after any of them change.

## Safeword

Long-running, restartable scripts use `.safeword` in the current working
directory. If the file contains `sea cucumber` or `seacucubmer`, processing
stops cleanly between restartable units.

```bash
printf 'sea cucumber\n' > .safeword
```

Remove `.safeword` and rerun the same command to resume.

## Outputs

Production runs use one work root per source video on Sol:

```text
/scratch/pdressla/honey-bee/artifacts/resequence/reseq_<key>/
|-- qc/        detector results and cut-review tables
|-- segments/  source segment table and metadata
|-- order/     ranked edges and selected segment order
|-- review/    automatic join-QC reports and any flagged-join roll
`-- output/    full-fidelity render, mappings, metadata, and derivatives
```

The cleaned local review copies in `data/qc/resequence/` mirror the first four
directories. A `qc/candidates/` JPEG directory may still appear in older runs;
current Stage 1 creates those images only when `--write-candidate-frames` is
explicitly enabled.

Large videos, compressed derivatives, and generated part files should stay out
of git.
