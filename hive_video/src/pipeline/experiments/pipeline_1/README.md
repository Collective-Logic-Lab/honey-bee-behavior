# Pipeline 1

Pipeline 1 is the cleaned-up version of the Experiment 9 sync-fix path. It
renders source-synchronous fixed-GMM motion-regime overlays from resequenced hive
videos.

The default profile is `0486`, the first profile that clearly isolated the
start03 festoon in a single dominant cluster:

- 500-frame lookback window
- 64x64 grid
- 13 GMM clusters
- `exp1` feature set
- `asinh` velocity scaling
- activity threshold 0.15
- angular feature weight 0.0
- neighbor feature weight 1.0
- vertical feature weight 2.0

The pipeline can run either a flat lookback window, a recency-decayed lookback
window, or both. It can also write side-by-side source/overlay diptych videos
and optional cluster statistics.

Pipeline 1 has two separate cadences:

- output cadence: every source frame is written to the output video
- analysis cadence: the expensive regime analysis can be computed every N frames
  with `--analysis-stride`, holding the most recent overlay between analyses

Use `--analysis-stride 1` for exact per-frame analysis. Full-video cluster runs
default to `ANALYSIS_STRIDE=10`, which keeps the output source-synchronous while
reducing the expensive feature extraction pass.

## Dry Run

From `hive_video`:

```sh
uv run python src/pipeline/pipeline_1/run.py \
  --video data/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4 \
  --out-root data/no-sync/pipeline_1_dry_run_start03 \
  --start-frame 230000 \
  --frame-count 250 \
  --mode both \
  --diptych \
  --dry-run
```

## Short Local Smoke Test

```sh
uv run python src/pipeline/pipeline_1/run.py \
  --video data/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4 \
  --out-root data/no-sync/pipeline_1_smoke_start03 \
  --start-frame 238847 \
  --frame-count 2 \
  --mode fixed \
  --fit-sample-stride 1 \
  --chunk-target-frames 2 \
  --analysis-stride 1 \
  --diptych \
  --stats summary
```

## Cluster Use

On the cluster, put resequenced videos under:

```text
/scratch/pdressla/honey-bee/artifacts/resequenced/
```

Then submit `src/pipeline/slurm/pipeline_1_day3_day4_array.sh`. The default
array has four jobs:

- start03 fixed
- start03 decay
- start04 fixed
- start04 decay

Use `DRY_RUN=1` for a plan-only test.

Useful Slurm environment overrides:

```sh
ANALYSIS_STRIDE=10 CHUNK_TARGET_FRAMES=1000 sbatch src/pipeline/slurm/pipeline_1_day3_day4_array.sh
```

`ANALYSIS_STRIDE=1` restores exact per-frame analysis. Larger values are faster
and produce held overlays between analyzed frames.
