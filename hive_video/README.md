## Hive Video

Honey bee hives are busy, layered, and difficult to read frame by frame. This folder contains tools for turning long hive videos into research-friendly artifacts: resequenced videos, motion-regime overlays, experiment outputs, and notebooks for reviewing collective behavior in the hive.

The current work focuses on comb-building and festoon-related behavior in the "Videos for honey bee lifetime tracking data 2019" dataset published by Smith et al. (2019), with related context from Neubauer et al. (2023), "Honey Bee Drones Are Synchronously Hyperactive inside the Nest." DOIs: [10.17617/3.LLWRWR](https://doi.org/10.17617/3.LLWRWR) for the dataset and [10.1016/j.anbehav.2023.05.018](https://doi.org/10.1016/j.anbehav.2023.05.018) for the paper.

The videos are here: [https://edmond.mpg.de/dataset.xhtml?persistentId=doi:10.17617/3.LLWRWR](https://edmond.mpg.de/dataset.xhtml?persistentId=doi:10.17617/3.LLWRWR).

Edmonds runs Dataverse. There is a schematic image for download at [https://doi.org/10.17617/3.LLWRWR](this location).

### TLDR

Run this from the repository root to set up the video tools:

```bash
cd hive_video
uv venv
source .venv/bin/activate
uv sync
uv run python get_dist_1.py
```

Then open `docs/experiments.ipynb`. The repository already includes a small five second sample video, and `get_dist_1.py` downloads the larger resequenced video artifact plus selected experiment outputs used by the notebook.

### Getting started

To get started, clone the overall repository and work from `./hive_video`. We recommend a virtual environment, and this documentation assumes `uv` for dependency management.

An example path might be:

```bash
git clone https://github.com/collab-bees/honey-bee-behavior.git
cd honey-bee-behavior/hive_video
# so, `pwd` would return `[your-workspace]/honey-bee-behavior/hive_video`

uv venv
source .venv/bin/activate
uv sync
```

The packages and data acquisition scripts should now be ready to use.

The project ships with a small amount of seed data in the `hive_video/data/` directory. A five second sample video is included in `data/raw/start04_sample_5s.mp4`, and `data/experiments/experiment_example_5s/` contains the output of a sample pipeline run on that video. Larger artifacts are distributed separately.

### Getting Data

This repository works with large video files. For most of the work to be done, you'll need to sync be able to access and sync with the public Collective Logic Lab HuggingFace data bucket, `collective-logic-lab/honey-bee`. The repository packaging includes the HuggingFace CLI, `hf`, and it is referenced in our pre-packaged scripts. You can also run `hf` as separately installed on your system or in your Python environment; for example, `uvx hf sync ...`. Since the bucket is public, a login is not required to download the data.

We package larger video data as named distributions for download. The first curated distribution contains the resequenced video artifact and representative experiment outputs used by `docs/experiments.ipynb`. It does not include `data/raw/start04_sample_5s.mp4` or `data/experiments/experiment_example_5s/`, because those are tracked directly in Git.

To download Distribution 1 into the paths expected by the notebooks:

```bash
uv run python get_dist_1.py
```

This syncs distribution files into `data/artifacts/` and `data/experiments/`. Distribution 1 includes only selected outputs from the larger Experiment 3 overnight parameter sweep: runs 09, 11, and 16, plus the summary figure and metric tables. The full overnight sweep can remain available in the data bucket as an archive without being part of the default download.

### Resequencing

The archived hive videos cut to a different part of the recording every few
minutes. Resequencing puts them back in order. End to end that is four `sbatch`
submissions from `hive_video/`, with source-cut inspection and manual join
review only when the automatic join diagnostic flags a video.

#### Bounded unattended Start 03 / Start 38 pilot

The current four-video integration batch fixes both top-panel sides of Start 03
and Start 38, then runs the dependency-linked download, Stage 1, Stage 1a,
outcome filing, Stage 2, and maximum-compression paths:

```bash
bash src/pipeline/slurm/resequence/submit_start03_start38_both_sides_top_e2e_v1.sh
```

The archive resolves those starts to `20190608_181426` and `20190722_200917`.
The launcher takes no arguments, verifies the four exact files and their real
media TLS paths, and records the complete submission before releasing its held
download array. Scratch work lives under
`artifacts/resequence_pilots/start03_start38_both_sides_top_v1/`, and remote
artifacts live under
`resequenced/pilots/start03_start38_both_sides_top_v1/`. Source-cut proposals
are explicitly marked `unreviewed_pilot`; flagged videos stop after filing the
compact review bundle, while Auto-QC-cleared videos continue to an archival MP4
and a `low` (CRF 28, maximum-compression) sharing derivative. These artifacts
do not replace validated inventory.

#### Recorded Start 01 / Start 02 pilot

The tracked two-video integration pilot fixes the inputs to Start 01 and Start
02, side 0, top panel, then submits the dependency-linked download, Stage 1,
Stage 1a, outcome filing, Stage 2, and maximum-compression paths:

```bash
bash src/pipeline/slurm/resequence/submit_start01_start02_side0_top_e2e_v2.sh
```

It takes no arguments and refuses a dirty or unpublished checkout, inherited
`SBATCH_*` overrides, an existing submission record, or a nonempty remote
prefix. Before submission it refreshes the Edmond manifest and verifies both
actual media redirect paths with one-byte ranged GETs using Sol's tracked CA
bundle. Source-cut proposals are explicitly marked `unreviewed_pilot`.
Every Stage 1a result is filed under
`resequenced/pilots/start01_start02_side0_top_v2/`; flagged videos stop there
cleanly, while automatically cleared videos continue to an archival MP4 and a
`low` (CRF 28) sharing derivative. Pilot artifacts do not replace the validated
inventory. Scratch work also uses the disjoint
`artifacts/resequence_pilots/start01_start02_side0_top_v2/` root, whose marker
prevents later generic compression/upload commands from losing that
provenance. v1 is retained as the failed TLS-at-download attempt rather than
being overwritten or requeued with changed settings. The launcher verifies the
retained v1 record and incrementally files v2's submission/job-ID record under
the private pilot prefix.

#### 1. Download the raw video

```bash
sbatch src/pipeline/slurm/resequence/download_raw_array.sh
```

Run the Slurm commands in this section from the `hive_video/` checkout root.
The jobs use Slurm's recorded submission directory to locate their shared
scripts after Slurm copies the submitted script into its spool directory.

Pulls the three Start 04 / Start 47 top-panel videos from the Edmond archive
(doi:10.17617/3.LLWRWR) into `/scratch/pdressla/honey-bee/downloads/`. Transfers
resume and are MD5-checked, so re-running a failed task is safe. For other
files, pass locators of the form `start<N>_side<0|1>_<top|bottom>`.

`start<N>` is the archive's sequential capture identifier, not an elapsed
calendar day. The timestamp embedded in the resolved filename is authoritative;
use `--list` to inspect the complete mapping.

```bash
sbatch --array=0-1 --export=ALL,LOCATORS="start3_side0_top start3_side1_top" \
    src/pipeline/slurm/resequence/download_raw_array.sh
```

To grab one file outside slurm:

```bash
uv run python src/download/download_raw.py --start 4 --side 1 --panel top \
    --target /scratch/pdressla/honey-bee/downloads
uv run python src/download/download_raw.py --list   # everything in the archive
```

#### 2. Measure before booking wall clock

```bash
sbatch src/pipeline/slurm/resequence/resequence_smoke_test.sh
```

Runs the full path over 20,000 frames and reports separate detection, ordering,
review-video, and reassembly timings. The wall clocks in the stage scripts are
placeholders until this has run.

#### 3. Stage 1, detect cuts and prepare the cut table

```bash
sbatch src/pipeline/slurm/resequence/resequence_stage1_array.sh
```

Runs detection and event summarisation, then writes
`qc/cut_review.proposed.csv`. Single-jump events default to `keep=1`, matching
the established Start03/Start04 procedure; multi-jump events remain visible
with `keep=0`. Successful steps receive completion markers, so a task killed
while writing output reruns that step. It intentionally writes CSV artifacts,
not hundreds of before/after JPEGs.

#### 4. Check the cuts by hand

Inspect `qc/candidates.csv`, `qc/jump_events.csv`, and
`qc/cut_review.proposed.csv`. Boundary detection is never clean: change `keep`,
correct `prev_frame_idx`, and add diagnosed cuts when needed. Save the reviewed
table as:

```text
<work dir>/qc/cut_review.verified.csv
```

If all proposed cuts are correct, do nothing further: Stage 1a uses that
inspected proposal directly. Only save `cut_review.verified.csv` when you
actually change a cut. To extract still frames for a specific investigation,
run `detect_video_discontinuities.py` directly with
`--write-candidate-frames`; it is not part of the normal array output.

#### 5. Stage 1a, order segments and check every join

```bash
sbatch src/pipeline/slurm/resequence/resequence_stage1a_review_array.sh
```

Builds segments from the inspected proposal (or an edited verified table),
applies the established trajectory signature with 10-frame windows, and then
checks every selected join using the direct one-frame discontinuity feature.
The diagnostic requires the selected successor to rank first among the
still-unused segments, retain a two-fold margin over the runner-up, and remain
below the recorded robust-score threshold. Its auditable outputs are:

```text
review/auto_qc.join_scores.csv
review/auto_qc.flagged_joins.csv
review/auto_qc.summary.json
```

An `auto_pass` result needs no manual join review. If any join is ambiguous,
discontinuous, or unscorable, the video receives
`manual_review_required` and Stage 1a creates
`review/qc_roll_flagged_joins.mp4` containing only those joins. After inspecting
that compact roll, bind the approval to the exact report, flagged table, roll,
and captions with the command printed in the Stage 1a log:

```bash
uv run --no-sync python src/resequence/diagnostics/approve_manual_join_qc.py create \
  --summary <work-dir>/review/auto_qc.summary.json \
  --out <work-dir>/review/auto_qc.manual_approval.json
```

Changing the order, inputs, thresholds, or report invalidates the approval.
The method, calibration evidence, and limitations are recorded in
`METHODS.md` under `HV-R001`.

#### 6. Stage 2, reassemble and back up

```bash
sbatch src/pipeline/slurm/resequence/resequence_stage2_array.sh
```

Consumes an automatically cleared order, or a flagged order with a current
manual approval, then renders the archival MP4. A dependent job publishes the
validated MP4 and its audit artifacts to
`hf://buckets/collective-logic-lab/honey-bee/resequenced/reseq_<key>`. The
backup runs on its own wall clock so it is not competing with the reassembly.
Uploading needs write access to the bucket: run `hf auth login` on the cluster
once, or set `HF_TOKEN` in the job environment. Bucket sync is deliberately
non-deleting; `CURRENT_ARTIFACTS.json` is the machine-readable authority for
the current file set, is published only after payload verification, and marks
any older unlisted review objects as superseded.

#### 7. Compare sharing profiles on a QC roll

The full Stage 1a QC roll is a compact, realistic source for choosing the
sharing profile before committing to a full archival-video transcode:

```bash
sbatch src/pipeline/slurm/resequence/compress_qc_roll_smoke.sh
```

This job encodes the complete Start 04 side 1 QC roll at high (CRF 18), medium
(23), and low (28). Its dependent upload job sends only those three comparison
MP4s, their metadata, and a README to:

```text
hf://buckets/collective-logic-lab/honey-bee/resequenced/qc_compression_smoke/reseq_<key>/
```

It does not alter the QC roll or any final resequenced video.

#### 8. Make a smaller sharing copy (after stage 2)

The archival resequenced MP4 remains unchanged. First render and inspect the
same short clip at all three H.264 quality profiles:

```bash
sbatch src/pipeline/slurm/resequence/compress_resequenced_smoke_test.sh
```

The smoke job writes `high` (CRF 18), `medium` (23), and `low` (28) samples
under `<work dir>/compression_smoke/`; it does not upload them. After choosing
one, create that one full-length sharing derivative. `medium` is the default:

```bash
sbatch --export=ALL,QUALITY=medium \
    src/pipeline/slurm/resequence/compress_resequenced_array.sh
```

Each successful array task queues its own verified upload to
`hf://buckets/collective-logic-lab/honey-bee/resequenced/compressed/reseq_<key>/<quality>/`.
Only the chosen sharing copy is added there; the full-fidelity resequenced
video remains at its existing archival path.

#### 9. One-time maximum-compression backfill for the five existing videos

```bash
sbatch src/pipeline/slurm/resequence/compress_existing_low_backfill_array.sh
```

This reviewed five-item array covers the three current Stage 2 outputs plus the
Start 04 side 0 and Start 03 side 0 archival MP4s in `prior_batch/`. It runs at
most two 8-CPU transcodes at once and uploads each maximum-compression low
(CRF 28) derivative to its canonical `compressed/reseq_<key>/low/` folder after
byte-size verification.

#### Where things land

Work for one video lives under
`${SCRATCH_ROOT}/artifacts/resequence/reseq_<key>/`, where `<key>` looks like
`start47_20190731_184423_side1_top`:

| Path | Contents |
| --- | --- |
| `qc/` | compact discontinuity candidates, jump events, and cut-review CSVs |
| `segments/` | segment definitions |
| `order/` | ranked joins and the trajectory-10 greedy order |
| `review/` | automatic join scores and, only when flagged, a compact QC roll and approval |
| `output/` | the reassembled MP4 and its frame map |
| `upload/` | exactly what gets published to HuggingFace |
| `compression_smoke/` | high, medium, and low short comparison clips |
| `qc_compression_smoke/` | high, medium, and low full-QC-roll comparison files |
| `compressed/` | one selected full-length H.264 sharing derivative |

Shared setup lives in `src/pipeline/slurm/resequence/common.sh`; override
`HIVE_VIDEO_ROOT`, `SCRATCH_ROOT`, or `DOWNLOAD_DIR` there or in the
environment. Detection parameters default to the tools' own defaults and can be
overridden per submission, for example
`--export=ALL,SAMPLE_WIDTH=256,TOP_N=400`.

See `src/resequence/README.md` for the underlying tools and for running the
steps by hand.

### Organization

The `src` folder has two major submodules and two helper folders. First, the hive videos that we are working with are archived in a disordered state: the sequence of frames cuts to a different part of the video every few minutes. The `resequence` module contains code that applies one algorithm to isolate the individual video segments, and a second algorithm to process those segments into the best identifiable working order. 

The `analyze` module contains code that attempts to classify and visually separate the bee behaviors in the video.
