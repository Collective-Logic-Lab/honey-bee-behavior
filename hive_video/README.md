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
sbatch src/resequence/slurm/download_raw_array.sh
```

Pulls the three Day 4 / Day 47 top videos from the Edmond archive
(doi:10.17617/3.LLWRWR) into `/scratch/pdressla/honey-bee/downloads/`. Transfers
resume and are MD5-checked, so re-running a failed task is safe. For other
files, pass locators of the form `day<N>_side<0|1>_<top|bottom>`, where `N` is
the capture start index (`day47` is `start47`).

Day numbers are capture identifiers, not elapsed calendar days. The two agree
early on but diverge from `start09`, because there are gaps in the recording
sequence: `start47` was recorded on 2019-07-31, which is the 56th day after
`start00`. The lab refers to captures by identifier, so `--day 47` always means
`start47`. Use `--list` if you need to check a date.

```bash
sbatch --array=0-1 --export=ALL,LOCATORS="day3_side0_top day3_side1_top" \
    src/resequence/slurm/download_raw_array.sh
```

To grab one file outside slurm:

```bash
uv run python src/download/download_raw.py --day 4 --side 1 --frame top \
    --target /scratch/pdressla/honey-bee/downloads
uv run python src/download/download_raw.py --list   # everything in the archive
```

#### 2. Measure before booking wall clock

```bash
sbatch src/resequence/slurm/resequence_smoke_test.sh
```

Times detection over 20,000 frames and projects the full-length cost. The wall
clocks in the stage scripts are placeholders until this has run.

#### 3. Stage 1, up to the join review

```bash
sbatch src/resequence/slurm/resequence_stage1_array.sh
```

Runs detection, event summarisation, segment building, ordering, and the join
review video. Each step is skipped if its output already exists, so a task that
hits the wall clock resumes on resubmission.

#### 4. Check the joins by hand

Stage 1 stops at `review/join_review_rank1.mp4`: short clips of each segment
ending followed by the proposed next segment start, separated by a green flash.
Boundary detection is never clean, so watch it, correct the ordering, and save
the result as:

```text
<work dir>/order/greedy_order.verified.csv
```

If the automatic ordering was already right, copy it across unchanged. Stage 2
refuses to start without this file, so the check cannot be skipped by accident.

#### 5. Stage 2, reassemble and back up

```bash
sbatch src/resequence/slurm/resequence_stage2_array.sh
```

Renders the verified ordering, and queues a dependent job that publishes the
finished MP4 plus the segment and ordering CSVs to
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
| `order/` | ranked joins, proposed and verified orderings |
| `review/` | the green-flash join review video |
| `output/` | the reassembled MP4 and its frame map |
| `upload/` | exactly what gets published to HuggingFace |

Shared setup lives in `src/resequence/slurm/common.sh`; override
`HIVE_VIDEO_ROOT`, `SCRATCH_ROOT`, or `DOWNLOAD_DIR` there or in the
environment. Detection parameters default to the tools' own defaults and can be
overridden per submission, for example
`--export=ALL,SAMPLE_WIDTH=256,TOP_N=400`.

See `src/resequence/README.md` for the underlying tools and for running the
steps by hand.

### Organization

The `src` folder has two major submodules and two helper folders. First, the hive videos that we are working with are archived in a disordered state: the sequence of frames cuts to a different part of the video every few minutes. The `resequence` module contains code that applies one algorithm to isolate the individual video segments, and a second algorithm to process those segments into the best identifiable working order. 

The `analyze` module contains code that attempts to classify and visually separate the bee behaviors in the video.
