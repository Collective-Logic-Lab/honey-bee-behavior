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
submissions with one manual check in the middle, all from `hive_video/`.

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

#### 3. Stage 1, up to the cut review

```bash
sbatch src/pipeline/slurm/resequence/resequence_stage1_array.sh
```

Runs detection and event summarisation, then writes
`qc/cut_review.proposed.csv`. Single-jump events default to `keep=1`, matching
the established Start03/Start04 procedure; multi-jump events remain visible
with `keep=0`. Successful steps receive completion markers, so a task killed
while writing output reruns that step.

#### 4. Check the cuts by hand

Inspect `qc/candidates/`, `qc/jump_events.csv`, and
`qc/cut_review.proposed.csv`. Boundary detection is never clean: change
`keep`, correct `prev_frame_idx`, and add diagnosed cuts when needed. Save the
reviewed table as:

```text
<work dir>/qc/cut_review.verified.csv
```

If all proposed cuts are correct, copy the proposed table unchanged. Stage 2
refuses to start without the verified file.

#### 5. Stage 2, reassemble and back up

```bash
sbatch src/pipeline/slurm/resequence/resequence_stage2_array.sh
```

Builds segments from the verified cuts, applies the established trajectory
signature with 10-frame windows, creates a green-flash review containing every
join in that exact greedy order, and renders it. A dependent job publishes the
validated MP4 and its audit artifacts to
`hf://buckets/collective-logic-lab/honey-bee/resequenced/reseq_<key>`. The
backup runs on its own wall clock so it is not competing with the reassembly.
Uploading needs write access to the bucket: run `hf auth login` on the cluster
once, or set `HF_TOKEN` in the job environment.

#### Where things land

Work for one video lives under
`${SCRATCH_ROOT}/artifacts/resequence/reseq_<key>/`, where `<key>` looks like
`start47_20190731_184423_side1_top`:

| Path | Contents |
| --- | --- |
| `qc/` | discontinuity candidates and jump events |
| `segments/` | segment definitions |
| `order/` | ranked joins and the trajectory-10 greedy order |
| `review/` | every join in the exact rendered order |
| `output/` | the reassembled MP4 and its frame map |
| `upload/` | exactly what gets published to HuggingFace |

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
