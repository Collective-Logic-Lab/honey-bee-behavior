#!/bin/bash
# Resequencing stage 1: everything up to the manual join check.
#
#   sbatch src/resequence/slurm/resequence_stage1_array.sh
#
# Runs, per array task:
#   1. detect_video_discontinuities   -> qc/candidates.csv
#   2. summarize_jump_events          -> qc/jump_events.csv
#   3. build_segments_from_jumps      -> segments/segments.csv
#   4. order_video_segments           -> order/ranked_edges.csv, order/greedy_order.csv
#   5. make_join_review_video         -> review/join_review_rank1.mp4
#
# It stops there on purpose. Step 5 is the green-flash review video: short clips
# of each segment end followed by the proposed next segment start, separated by
# a green flash. Watch it, fix the ordering, and save the corrected order as
# order/greedy_order.verified.csv before running stage 2.
#
# Every step is skipped when its output already exists, so a task that dies
# partway through resumes on resubmission. Set FORCE=1 to redo everything.
#
# Detection parameters default to whatever the underlying tools default to,
# which is what the start03 work was validated with. Override individually:
#
#   sbatch --export=ALL,SAMPLE_WIDTH=256,TOP_N=400 \
#       src/resequence/slurm/resequence_stage1_array.sh

#SBATCH --job-name=bees-reseq1
#SBATCH --array=0-2
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB
#SBATCH -t 24:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.reseq1.%A_%a.out
#SBATCH -e slurm.reseq1.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

source "$(dirname "$(readlink -f "$0")")/common.sh"

LOCATORS=${LOCATORS:-"day4_side1_top day47_side0_top day47_side1_top"}

hv_sync_env

LOCATOR="$(hv_locator_for_task "${LOCATORS}" "${SLURM_ARRAY_TASK_ID:-0}")"
hv_resolve "${LOCATOR}"

hv_require_file "${RESEQ_PATH}" \
  "Run download_raw_array.sh first, or set DOWNLOAD_DIR to where the raw video lives."

mkdir -p "${HV_QC_DIR}" "${HV_SEG_DIR}" "${HV_ORDER_DIR}" "${HV_REVIEW_DIR}"

CANDIDATES="${HV_QC_DIR}/candidates.csv"
EVENTS="${HV_QC_DIR}/jump_events.csv"
SEGMENTS="${HV_SEG_DIR}/segments.csv"
RANKED_EDGES="${HV_ORDER_DIR}/ranked_edges.csv"
JOIN_REVIEW="${HV_REVIEW_DIR}/join_review_rank${JOIN_REVIEW_RANK:-1}.mp4"

# Treat an existing output as done unless the caller forces a rebuild.
hv_step_needed() {
  if [ "${FORCE:-0}" = "1" ]; then
    return 0
  fi
  if [ -f "$1" ]; then
    echo "--- skipping, already present: $1"
    return 1
  fi
  return 0
}

if hv_step_needed "${CANDIDATES}"; then
  DETECT=(
    uv run --no-sync python src/resequence/detect_video_discontinuities.py
    "${RESEQ_PATH}"
    --out "${HV_QC_DIR}"
    # Long jobs: keep the log readable rather than one line every 10 seconds.
    --progress-every-seconds "${PROGRESS_EVERY_SECONDS:-300}"
  )
  if [ -n "${SAMPLE_WIDTH:-}" ]; then DETECT+=(--sample-width "${SAMPLE_WIDTH}"); fi
  if [ -n "${TOP_N:-}" ]; then DETECT+=(--top-n "${TOP_N}"); fi
  if [ -n "${MAD_Z:-}" ]; then DETECT+=(--mad-z "${MAD_Z}"); fi
  if [ -n "${MIN_DISTANCE:-}" ]; then DETECT+=(--min-distance "${MIN_DISTANCE}"); fi
  if [ -n "${THRESHOLD_MODE:-}" ]; then DETECT+=(--threshold-mode "${THRESHOLD_MODE}"); fi
  if [ -n "${EXPECTED_INTERVAL_FRAMES:-}" ]; then
    DETECT+=(--expected-interval-frames "${EXPECTED_INTERVAL_FRAMES}")
  fi
  hv_time_step "detect_discontinuities" "${DETECT[@]}"
fi

if hv_step_needed "${EVENTS}"; then
  SUMMARIZE=(
    uv run --no-sync python src/resequence/summarize_jump_events.py
    --candidates "${CANDIDATES}"
    --out "${EVENTS}"
  )
  if [ -n "${FPS:-}" ]; then SUMMARIZE+=(--fps "${FPS}"); fi
  if [ -n "${MAX_GAP_FRAMES:-}" ]; then SUMMARIZE+=(--max-gap-frames "${MAX_GAP_FRAMES}"); fi
  hv_time_step "summarize_jump_events" "${SUMMARIZE[@]}"
fi

if hv_step_needed "${SEGMENTS}"; then
  BUILD_SEGMENTS=(
    uv run --no-sync python src/resequence/build_segments_from_jumps.py
    "${RESEQ_PATH}"
    --jumps "${EVENTS}"
    --input-kind events
    --out "${SEGMENTS}"
  )
  # ffprobe -count_frames on a 33 GB file is very slow; pass FRAME_COUNT when known.
  if [ -n "${FRAME_COUNT:-}" ]; then BUILD_SEGMENTS+=(--frame-count "${FRAME_COUNT}"); fi
  if [ "${COUNT_FRAMES:-0}" = "1" ]; then BUILD_SEGMENTS+=(--count-frames); fi
  if [ -n "${SEGMENT_TOP_N:-}" ]; then BUILD_SEGMENTS+=(--top-n "${SEGMENT_TOP_N}"); fi
  if [ "${SINGLE_JUMP_EVENTS_ONLY:-0}" = "1" ]; then
    BUILD_SEGMENTS+=(--single-jump-events-only)
  fi
  if [ -n "${MAX_DURATION_FRAMES:-}" ]; then
    BUILD_SEGMENTS+=(--max-duration-frames "${MAX_DURATION_FRAMES}")
  fi
  hv_time_step "build_segments" "${BUILD_SEGMENTS[@]}"
fi

if hv_step_needed "${RANKED_EDGES}"; then
  ORDER=(
    uv run --no-sync python src/resequence/order_video_segments.py
    --segments "${SEGMENTS}"
    --out "${HV_ORDER_DIR}"
  )
  if [ -n "${WINDOW_FRAMES:-}" ]; then ORDER+=(--window-frames "${WINDOW_FRAMES}"); fi
  if [ -n "${ORDER_SAMPLE_WIDTH:-}" ]; then ORDER+=(--sample-width "${ORDER_SAMPLE_WIDTH}"); fi
  if [ -n "${TOP_K:-}" ]; then ORDER+=(--top-k "${TOP_K}"); fi
  if [ -n "${SIGNATURE:-}" ]; then ORDER+=(--signature "${SIGNATURE}"); fi
  hv_time_step "order_segments" "${ORDER[@]}"
fi

if hv_step_needed "${JOIN_REVIEW}"; then
  REVIEW=(
    uv run --no-sync python src/resequence/diagnostics/make_join_review_video.py
    "${RESEQ_PATH}"
    --ranked-edges "${RANKED_EDGES}"
    --out "${JOIN_REVIEW}"
    --rank "${JOIN_REVIEW_RANK:-1}"
  )
  if [ -n "${JOIN_REVIEW_LIMIT:-}" ]; then REVIEW+=(--limit "${JOIN_REVIEW_LIMIT}"); fi
  if [ -n "${JOIN_REVIEW_SECONDS:-}" ]; then
    REVIEW+=(--seconds-each-side "${JOIN_REVIEW_SECONDS}")
  fi
  hv_time_step "join_review_video" "${REVIEW[@]}"
fi

cat <<EOF

Stage 1 complete for ${RESEQ_KEY}.

  join review video : ${JOIN_REVIEW}
  proposed ordering : ${HV_ORDER_DIR}/greedy_order.csv

Next: watch the review video, correct the ordering, and save it as

  ${HV_ORDER_DIR}/greedy_order.verified.csv

Stage 2 refuses to run without that file, so the manual check cannot be
skipped by accident.
EOF
