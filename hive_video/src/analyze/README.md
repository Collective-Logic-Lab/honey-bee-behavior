## Analyze

This directory contains instrumentation scripts for exploratory motion-regime
analysis. The scripts here are deliberately close to the raw measurements:
optical flow, local grid-cell summaries, clustering inputs, labels, and overlay
videos. The higher-level scientific framing for experiments lives in
`../../docs/experiments.ipynb`.

The current analysis tools are:

1. `run_analysis.py`
   Run named presets for examples, teaching runs, and long exploratory runs.
   This is the recommended entry point for experiments that should be
   reproducible from a preset name.

2. `annotate_motion_regimes.py`
   Read a source MP4, compute dense optical flow over a selected frame range,
   summarize motion in grid cells over rolling time windows, cluster those
   cell-window feature rows, and render a color-coded overlay video. Use this
   directly when debugging the instrumentation or trying one-off settings.

3. `run_motion_regime_chunks.py`
   Run `annotate_motion_regimes.py` over long frame ranges as restartable
   chunks. `run_analysis.py` can call this runner for chunked presets.

4. `run_motion_regime_samples.py`
   Run `annotate_motion_regimes.py` on evenly spaced short samples from a
   larger frame span. Use this for parameter checks that need broad coverage
   without processing the full video.

### Presets

`run_analysis.py` records the preset, resolved parameters, command, git commit,
runner version, and instrumentation version in `analysis_run.json`.

Examples from `hive_video/`:

```bash
uv run python src/analyze/run_analysis.py \
  example_5s_beginner \
  --video data/raw/start04_sample_5s.mp4 \
  --out data/qc/example_5s_beginner
```

```bash
uv run python src/analyze/run_analysis.py \
  b1_velocity_only \
  --video data/raw/start04_sample_5s.mp4 \
  --out data/qc/b1_velocity_only
```

Use `--set KEY=VALUE` for small controlled deviations from a preset:

```bash
uv run python src/analyze/run_analysis.py \
  example_5s_beginner \
  --video data/raw/start04_sample_5s.mp4 \
  --out data/qc/example_5s_beginner_grid16 \
  --set grid_rows=16 \
  --set grid_cols=16
```

Sampled presets use the same override pattern:

```bash
uv run python src/analyze/run_analysis.py \
  exp3_sampler \
  --video data/artifacts/resequenced/reseq_1_start04__20190609_175013_side0_top.mp4 \
  --out data/qc/exp3_sampler
```

### Raw Instrumentation

`annotate_motion_regimes.py` writes the raw feature table used for clustering.
Each row corresponds to one grid cell in one time window. Important fields
include:

- `frame_start`, `frame_stop`, `frame_mid`: source-frame timing for the window.
- `cell_row`, `cell_col`, `x_center`, `y_center`: local position on the sampled
  hive surface.
- `mean_vx`, `mean_vy`: average optical-flow vector in the cell.
- `mean_speed`, `mean_speed_sq`, `std_speed`: local velocity magnitude
  summaries.
- `active_fraction`: fraction of pixels whose optical-flow speed exceeds the
  activity threshold.
- `alignment`: strength of local vector alignment.
- `direction_concentration`: how tightly local directions occupy the unit
  circle.
- `angular_sweep_std`, `angular_sweep_abs_mean`: recent directional change
  summaries.
- `divergence`, `curl`: local flow expansion/rotation summaries.
- `neighbor_*`: contrasts with nearby grid cells, used as first-pass
  boids-like group-motion features.

The output CSV keeps these raw measurements even when clustering uses a reduced
feature set such as `velocity` or `beginner`.

### Clustering Knobs

The scripts support intentionally simple sklearn clustering:

- `--method gmm` or `--method kmeans`
- `--clusters`
- `--pca-components`
- `--feature-set full|exp1|velocity|beginner`
- `--velocity-transform raw|log1p|sqrt|asinh`
- `--angular-feature-weight`
- `--neighbor-feature-weight`
- `--top-mask-height`

These settings are instrumentation controls, not claims that a behavior label is
final. They are meant to generate reviewable groupings for human inspection and
follow-up experiments.

Use `--top-mask-height` when annotating a captioned resequenced video. It draws
an opaque black band across the top of the output before writing the annotation
timestamp, avoiding unreadable text-on-text overlays.

`feature-set=exp1` preserves the pre-angular-neighbor baseline used for
Experiment 1. The raw feature CSV still includes all computed instrumentation
columns, but clustering is restricted to the earlier baseline feature set.

### Long Runs

For long videos, use `run_motion_regime_chunks.py`. It writes:

- `chunks_manifest.csv`
- one output directory per chunk
- chunk-level `motion_regime_features.csv`
- chunk-level `motion_regime_overlay.mp4`
- run-level `metadata.json`
- optional `motion_regime_overlay_all_chunks.mp4`

Long chunked runs check `.safeword` between chunks. If `.safeword` contains
`sea cucumber` or `seacucubmer`, the run stops cleanly and can be resumed by
removing the file and rerunning the same command.

### Sampled Runs

For broad parameter checks, use `run_motion_regime_samples.py` or a sampled
preset such as `exp3_sampler`. It distributes short samples evenly over a
requested frame span and writes:

- `samples_manifest.csv`
- one output directory per sample
- sample-level `motion_regime_features.csv`
- sample-level `motion_regime_overlay.mp4`
- run-level `metadata.json`
- optional `motion_regime_overlay_all_samples.mp4`

### Outputs

Recommended output locations from `hive_video/`:

- `data/qc/` for exploratory runs, screenshots, and intermediate review
  outputs.
- `data/experiments/` for curated example outputs that are intended to stay with
  the project.

Large generated videos and chunk directories should generally stay out of git.
