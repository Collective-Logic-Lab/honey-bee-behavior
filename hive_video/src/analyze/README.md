## Analyze

This directory contains instrumentation scripts for exploratory motion-regime
analysis. The scripts here are deliberately close to the raw measurements:
optical flow, local grid-cell summaries, clustering inputs, labels, and overlay
videos. The higher-level scientific framing for experiments lives in
`../../docs/experiments.ipynb`.

The current analysis tools are:

1. `annotate_motion_regimes.py`
   Read a source MP4, compute dense optical flow over a selected frame range,
   summarize motion in grid cells over rolling time windows, cluster those
   cell-window feature rows, and render a color-coded overlay video.

2. `run_motion_regime_chunks.py`
   Run `annotate_motion_regimes.py` over long frame ranges as restartable
   chunks. This is the preferred entry point for long laptop runs.

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
- `--feature-set full|velocity|beginner`
- `--velocity-transform raw|log1p|sqrt|asinh`
- `--angular-feature-weight`
- `--neighbor-feature-weight`

These settings are instrumentation controls, not claims that a behavior label is
final. They are meant to generate reviewable groupings for human inspection and
follow-up experiments.

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

### Outputs

Recommended output locations from `hive_video/`:

- `data/qc/` for exploratory runs, screenshots, and intermediate review
  outputs.
- `data/experiments/` for curated example outputs that are intended to stay with
  the project.

Large generated videos and chunk directories should generally stay out of git.
