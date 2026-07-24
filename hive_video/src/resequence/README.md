## Resequence

These scripts repair shuffled hive videos by detecting visual discontinuities,
turning those discontinuities into source segments, ordering the segments, and
rendering a captioned review video. They are written as command-line tools and
are intended to be run from the `hive_video/` directory with `uv run python`.

### Start here: the scripted pipeline

On the cluster you should not be driving these tools one at a time. The wrappers
in `src/pipeline/slurm/resequence/` run the whole sequence, resolve every path
from a single locator, and stop at the one point that needs a human:

```bash
sbatch src/pipeline/slurm/resequence/download_raw_array.sh       # fetch raw video from Edmond
sbatch src/pipeline/slurm/resequence/resequence_smoke_test.sh    # time it, then set wall clocks
sbatch src/pipeline/slurm/resequence/resequence_stage1_array.sh  # steps 1-4 plus the join review

# watch review/join_review_rank1.mp4, fix the ordering, then:
#   cp order/greedy_order.csv order/greedy_order.verified.csv

sbatch src/pipeline/slurm/resequence/resequence_stage2_array.sh  # step 5, then upload to HuggingFace
```

Stage 1 covers steps 1 through 4 below and then builds the join review video.
Stage 2 runs step 5, and will not start until `greedy_order.verified.csv`
exists. Both stages skip work whose output is already present, so resubmitting
after a wall-clock kill resumes rather than restarting.

`src/pipeline/slurm/resequence/common.sh` holds the shared environment, the uv
scratch-venv locking, and `hv_resolve`, which turns a locator such as
`day47_side1_top` into the raw video path, the canonical key, and every work
directory. The full walkthrough, including how to select other files, is in
`hive_video/README.md`.

The rest of this document describes the underlying tools, which is what you
want when diagnosing a bad join or running a step by hand.

### The tools

The current pipeline is:

1. `detect_video_discontinuities.py`
   Compute frame-to-frame visual distances from a raw MP4. This produces ranked
   candidate cuts and, optionally, all frame-to-frame distances.

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

### Diagnostics

The `diagnostics/` directory contains tools used to validate or review the
pipeline rather than produce the final video directly.

- `diagnostics/diagnose_segment_discontinuities.py`
  Scores frame-to-frame distances inside specified source segments or source
  frame ranges. Use this to justify any forced cuts added to segment production.

- `diagnostics/make_join_review_video.py`
  Builds short before/after clips for candidate joins. This is useful for human
  review of ordering quality before rendering a full reassembled video.

### Safeword

Long-running, restartable scripts use `.safeword` in the current working
directory. If the file contains `sea cucumber` or `seacucubmer`, processing
stops cleanly between restartable units.

```bash
printf 'sea cucumber\n' > .safeword
```

Remove `.safeword` and rerun the same command to resume.

### Outputs

Recommended output locations from `hive_video/`:

- `data/qc/` for discontinuity candidates, event summaries, join reviews, and
  other inspection artifacts.
- `data/artifacts/segments/` for segment CSVs and segment metadata.
- `data/experiments/` for rendered review videos and full reassembled videos.

Large videos and generated part files should stay out of git.
