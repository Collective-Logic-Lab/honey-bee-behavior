# Motion-Regime Overlay Video Explainer

This document walks through how the current overlay videos are generated from a
resequenced hive video. The concrete example is Experiment 7b, which renders a
short stabilized overlay for base setting `486` with repaired
`vertical_feature_weight=2.0`.

The current command is:

```bash
cd hive_video
uv run python src/pipeline/exp7b_setting486_vert2_stabilized_overlay.py
```

That wrapper calls the reusable renderer:

```bash
python src/pipeline/exp6e_profile_overlay.py \
  --video data/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4 \
  --source-manifest data/no-sync/exp6d_focused_sweep_start03/exp6d_focused_sweep_manifest.csv \
  --out data/no-sync/exp7b_setting486_vert2_stabilized_overlay_start03/exp7b_setting486_vert2_stabilized_frames228000_231000_endnotes.mp4 \
  --base-setting-id 486 \
  --vertical-weight 2.0 \
  --start-frame 228000 \
  --end-frame 231001 \
  --stride 1 \
  --stabilize-colors \
  --endnotes
```

`--end-frame` is exclusive, so `231001` means that frame `231000` is included.

## 1. Choose A Profile

The overlay is controlled by a previously discovered parameter profile. In this
case the wrapper chooses profile `486`, which came from the Experiment 6d sweep
manifest. The renderer reads that row from:

```text
data/no-sync/exp6d_focused_sweep_start03/exp6d_focused_sweep_manifest.csv
```

The profile row defines the motion feature settings:

```python
base_setting = read_base_settings(args.source_manifest.expanduser(), [args.base_setting_id])[0]
setting = replace(base_setting, vertical_feature_weight=args.vertical_weight)
```

The important values for Experiment 7b are:

```text
base_setting_id = 486
window_frames = 500
grid_size = 64
clusters = 13
feature_set = exp1
velocity_transform = asinh
activity_threshold = 0.15
angular_feature_weight = 0.0
neighbor_feature_weight = 1.0
vertical_feature_weight = 2.0
```

The `vertical_feature_weight` value is supplied by Experiment 7b, not inherited
from the original 6d row. This uses the repaired weighting path: vertical
features are included as columns, standardized with the rest of the feature
matrix, and then weighted after scaling.

## 2. Select The Frame Interval

Experiment 7b renders every frame from `228000` through `231000`.

```python
first_target = max(args.start_frame, setting.window_frames - 1)
target_frames = list(range(first_target, args.end_frame, args.stride))
```

With `stride=1`, every frame becomes a target frame. For each target frame, the
pipeline looks backward `window_frames` frames and computes one motion-regime
classification for the grid cells at that target time.

For profile `486`, each target frame is described using the previous `500`
video frames. The optical-flow stack contains `499` frame-to-frame flows.

## 3. Read Frames In Chunks

The pipeline does not load the whole interval at once. It processes target
frames in chunks. For each chunk, it reads just enough source video to cover the
largest history window needed by the chunk.

```python
for chunk_start in range(0, len(target_frames), args.chunk_target_frames):
    chunk_targets = target_frames[chunk_start : chunk_start + args.chunk_target_frames]
    read_start = chunk_targets[0] - setting.window_frames + 1
    read_stop = chunk_targets[-1]
    gray_frames, _ = read_frames(video, read_start, read_stop - read_start + 1, args.flow_scale_width)
```

For example, if the chunk starts at target frame `228000`, the source video read
starts at:

```text
228000 - 500 + 1 = 227501
```

The video is resized to `flow_scale_width`, currently `824`, before optical
flow is computed. This keeps the computation tractable while preserving the
large-scale hive structure needed for review.

The color frames are read separately for rendering:

```python
color_frames, fps = read_color_frames(
    video,
    chunk_targets[0],
    chunk_targets[-1] + 1,
    args.stride,
    args.flow_scale_width,
)
```

## 4. Compute Optical Flow

The grayscale frames are converted into dense optical flow using OpenCV's
Farneback optical-flow estimator:

```python
flows = compute_flows(gray_frames)
```

The underlying function computes a flow field between each adjacent pair of
frames:

```python
flow = cv2.calcOpticalFlowFarneback(
    frames[i],
    frames[i + 1],
    None,
    pyr_scale=0.5,
    levels=3,
    winsize=15,
    iterations=3,
    poly_n=5,
    poly_sigma=1.2,
    flags=0,
)
```

Each flow field stores local x/y motion. In biological terms, this is not a
tracked identity for a bee. It is a local motion estimate for the image.

## 5. Convert Motion Into Grid-Cell Features

For each target frame, the pipeline extracts a window of flow fields ending at
that target frame:

```python
local_start = target_frame - setting.window_frames + 1 - read_start
local_stop = target_frame - read_start
flow_slice = flows[local_start:local_stop]
```

Then it summarizes motion within a `64 x 64` grid:

```python
features, vertical = extract_one_window_features(
    flow_slice,
    target_frame,
    setting.window_frames,
    setting,
)
```

Each grid cell receives motion features such as:

- `mean_vx`, `mean_vy`: mean x/y flow.
- `mean_speed`: mean local movement speed.
- `active_fraction`: fraction of pixels whose speed exceeds the activity threshold.
- `alignment`: how consistently local flow points in one direction.
- `direction_concentration`: temporal concentration of movement direction across the window.
- `divergence`, `curl`: coarse local expansion/rotation measures.
- `neighbor_speed_contrast`, `neighbor_alignment_contrast`: cell behavior relative to neighboring cells.

The cell-level extraction happens here:

```python
for row, col, y_slice, x_slice in cell_slices(height, width, setting.grid_size, setting.grid_size):
    features.append(
        summarize_cell(
            0,
            frame_start,
            target_frame,
            row,
            col,
            y_slice,
            x_slice,
            flow_stack,
            setting.activity_threshold,
        )
    )
features = add_neighbor_contrasts(features, setting.grid_size, setting.grid_size)
```

## 6. Add Vertical Strand Features

The overlay profiles also include vertical-strand features. These were added
because the visible festoon often appears as vertically coherent strands of
bees, not merely a patch of slow movement.

For each grid cell, the pipeline compares vertical neighbors against horizontal
neighbors:

```python
vertical = [
    by_cell[key]
    for key in ((feature.cell_row - 1, feature.cell_col), (feature.cell_row + 1, feature.cell_col))
    if key in by_cell
]
horizontal = [
    by_cell[key]
    for key in ((feature.cell_row, feature.cell_col - 1), (feature.cell_row, feature.cell_col + 1))
    if key in by_cell
]
```

It then computes:

- `vertical_activity_coherence`
- `vertical_alignment_coherence`
- `vertical_direction_coherence`
- `column_continuity`
- `vertical_strand_score`

The strand score combines vertical-vs-horizontal coherence and column
continuity:

```python
strand_score = (
    (vertical_activity - horizontal_activity)
    + (vertical_alignment - horizontal_alignment)
    + (vertical_direction - horizontal_direction)
    + column_continuity
)
```

This is still a heuristic. It does not prove that a cell is part of a real
festoon. It marks a local motion pattern that resembles vertical strand-like
organization.

## 7. Build The Feature Matrix

The raw grid-cell summaries are converted into a numeric matrix:

```python
x, feature_names = feature_matrix_with_vertical(features, vertical, setting)
```

For setting `486`, the base feature set is `exp1`, which includes:

```text
x_center
y_center
mean_vx
mean_vy
mean_speed
mean_speed_sq
std_speed
active_fraction
alignment
divergence
curl
neighbor_speed_contrast
neighbor_alignment_contrast
```

Then the vertical feature columns are appended:

```python
vertical_names = [
    "vertical_activity_coherence",
    "vertical_alignment_coherence",
    "vertical_direction_coherence",
    "column_continuity",
    "vertical_strand_score",
]
v = np.array(vertical_rows, dtype=np.float64)
return np.column_stack([x, v]), [*names, *vertical_names]
```

The velocity transform for this profile is `asinh`. That transform compresses
large motion values while preserving sign for signed features.

## 8. Cluster The Current Frame

Each target frame is clustered independently. The current implementation uses a
Gaussian mixture model with `13` clusters:

```python
labels, probs, _ = fit_clusters(
    x,
    setting.method,
    setting.clusters,
    setting.pca_components,
    0,
    "diag",
    1e-4,
    setting.angular_feature_weight,
    setting.neighbor_feature_weight,
    feature_names,
    setting.vertical_feature_weight,
)
```

Inside `fit_clusters`, all features are standardized:

```python
scaler = StandardScaler()
z = scaler.fit_transform(x)
```

Then feature-family weights are applied after scaling:

```python
apply_feature_weights(
    z,
    feature_names,
    angular_feature_weight,
    neighbor_feature_weight,
    vertical_feature_weight,
)
```

This order matters. Applying `vertical_feature_weight` after standardization
makes values such as `0`, `1`, and `2` meaningful. Earlier test runs applied the
vertical multiplier before standardization, which mostly collapsed nonzero
vertical weights into the same effective scale.

The GMM produces:

- `labels`: one cluster label for each grid cell.
- `probs`: per-cluster probabilities for each grid cell.

## 9. Stabilize Cluster Colors

Because the GMM is refit independently for every target frame, cluster IDs can
change from frame to frame. Without stabilization, the biological pattern may
look stable while the colors flicker.

Experiment 7b uses:

```bash
--stabilize-colors
```

For each new frame, the renderer compares the current cluster labels to the
previous frame's displayed labels. It counts how many grid cells overlap between
each current cluster and each previous display color:

```python
counts = np.zeros((cluster_count, cluster_count), dtype=np.int64)
for current_label, previous_label in zip(labels, previous_display_labels, strict=True):
    if 0 <= current_label < cluster_count and 0 <= previous_label < cluster_count:
        counts[current_label, previous_label] += 1
```

It then greedily maps current clusters to previous display colors by maximum
overlap:

```python
for count, current_label, display_label in sorted(candidates, reverse=True):
    if count <= 0:
        break
    if current_label in used_current or display_label in used_display:
        continue
    mapping[current_label] = display_label
```

This does not make the clusters scientifically identical across all time. It is
a display stabilization method. It says: if a cluster covers mostly the same
grid cells as a color in the previous frame, keep using that color.

## 10. Draw The Overlay

The renderer draws one output frame per target frame:

```python
writer.write(
    draw_overlay_frame(
        frame,
        features,
        vertical,
        display_labels,
        probs,
        setting,
        target_frame,
        fps,
        args.top_mask_height,
        args.min_active_fraction,
    )
)
```

Each grid cell is colored by its stabilized display label:

```python
color = colors[int(label)]
cv2.rectangle(overlay, (x0, y0), (x1, y1), color, thickness=-1)
```

The overlay is blended with the original video:

```python
frame = cv2.addWeighted(overlay, 0.28, frame, 0.72, 0)
```

Arrows are drawn for cells whose `active_fraction` exceeds the minimum display
threshold:

```python
if feature.active_fraction >= min_active_fraction:
    end = (int(cx + feature.mean_vx * 10), int(cy + feature.mean_vy * 10))
    cv2.arrowedLine(frame, (cx, cy), end, color, 2, tipLength=0.35)
```

The caption at the top records the current frame, time, profile, and parameter
settings:

```text
frame 228000 t=9120.0s base 0486
w500 g64 k13 exp1 asinh ang0 nbr1 vert2
```

## 11. Accumulate Cluster Interpretation Statistics

Experiment 7b also asks the renderer to append explanatory endnotes:

```bash
--endnotes
```

As each frame is rendered, the renderer accumulates statistics for each
stabilized display cluster:

```python
update_cluster_stats(cluster_stats, features, vertical, display_labels, args.top_mask_height)
```

The statistics are computed over visible grid cells after excluding the caption
band. For each display cluster, the renderer accumulates:

- cell count and share of visible cells
- mean speed
- active fraction
- alignment
- direction concentration
- column continuity
- vertical strand score
- upper-right share
- lower-right share

The update step looks like this:

```python
row["count"] += 1
row["mean_speed"] += feature.mean_speed
row["active_fraction"] += feature.active_fraction
row["alignment"] += feature.alignment
row["direction_concentration"] += feature.direction_concentration
row["column_continuity"] += vertical_values["column_continuity"]
row["vertical_strand_score"] += vertical_values["vertical_strand_score"]
```

The upper-right and lower-right shares are included because they help reviewers
see whether a color is concentrated in the region of visible festoon formation
or whether it is also present in lower-comb regions.

These region summaries are interpretive aids, not ground-truth labels.

## 12. Append The Endnote Card

At the end of the video, the renderer writes a short black-background card:

```python
if args.endnotes and written:
    for frame in endnote_frames(...):
        writer.write(frame)
```

The card contains the profile settings and one row per stabilized display color:

```text
C  color  share  speed  active  align  dir  strand  column  UR  LR
```

The intent is to make the overlay communicable. Instead of saying "red looks
like festooning," the viewer can ask:

- Is the red cluster low or high speed?
- Does it have high `vertical_strand_score`?
- Is it spatially enriched in the upper-right region?
- Does it also appear elsewhere in the hive?

This supports a more careful interpretation: a color may represent a
festoon-like motion regime without being identical to the realized visible
festoon.

## 13. Write The MP4

The output video is written frame by frame with OpenCV:

```python
writer = cv2.VideoWriter(
    str(out),
    cv2.VideoWriter_fourcc(*"mp4v"),
    fps / max(1, args.stride),
    (scale_width, scale_height),
)
```

For Experiment 7b the default output is:

```text
data/no-sync/exp7b_setting486_vert2_stabilized_overlay_start03/exp7b_setting486_vert2_stabilized_frames228000_231000_endnotes.mp4
```

## Current Interpretation

The overlay does not identify individual bees. It classifies local image-motion
regimes over a grid. The current best profiles appear to separate a
festoon-like regime: slow or coherent motion with strand-like vertical
organization. That regime may occur outside the visually obvious festoon. This
is scientifically important rather than merely a failure mode.

The working interpretation is:

- The cluster color marks a local motion regime.
- The visible festoon is a region where that regime becomes spatially stable.
- Similar motion regimes elsewhere may indicate colony-wide readiness,
  transient local organization, or behavior that does not stabilize because the
  local geometry is not suitable for comb building.

This is why the endnote statistics report both feature values and regional
enrichment. The goal is not only to find the upper-right patch, but to
understand what motion features distinguish the cluster and where else that
behavior appears.

