#!/bin/bash
# Resequencing stage 1a: turn verified cuts into an ordered green-flash review.
#
#   sbatch src/pipeline/slurm/resequence/resequence_stage1a_review_array.sh
#
# Run this only after stage 1's qc/cut_review.verified.csv exists. It builds
# source segments, applies the established trajectory/10-frame greedy order,
# and makes a compact MP4 that shows every proposed join with a green flash.
# It does not render the full archival video or upload anything. Stage 2 uses
# these validated outputs for that expensive final step.

#SBATCH --job-name=bees-reseq1a
#SBATCH --array=0-2
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB
#SBATCH -t 12:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.reseq1a.%A_%a.out
#SBATCH -e slurm.reseq1a.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

# Slurm executes a copy of this script from /var/spool/slurmd, so $0 does not
# identify the checkout. The documented submission command runs from the
# hive_video root, which Slurm records in SLURM_SUBMIT_DIR.
export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

LOCATORS=${LOCATORS:-"start4_side1_top start47_side0_top start47_side1_top"}

hv_sync_env
hv_require_ffmpeg

LOCATOR="$(hv_locator_for_task "${LOCATORS}" "${SLURM_ARRAY_TASK_ID:-0}")"
hv_resolve "${LOCATOR}"

VERIFIED_CUTS="${HV_QC_DIR}/cut_review.verified.csv"
SEGMENTS="${HV_SEG_DIR}/segments.csv"
RANKED_EDGES="${HV_ORDER_DIR}/ranked_edges.csv"
GREEDY_ORDER="${HV_ORDER_DIR}/greedy_order.csv"
JOIN_REVIEW="${HV_REVIEW_DIR}/join_review_greedy_order.mp4"
JOIN_CAPTIONS="${HV_REVIEW_DIR}/join_review_greedy_order.captions.csv"
SEGMENTS_DONE="${HV_SEG_DIR}/.build_segments.complete"
ORDER_DONE="${HV_ORDER_DIR}/.order_segments.complete"
REVIEW_DONE="${HV_REVIEW_DIR}/.join_review.complete"
STAGE1A_DONE="${HV_REVIEW_DIR}/.stage1a.complete"

hv_require_file "${RESEQ_PATH}" "The raw video is gone; re-run download_raw_array.sh."
hv_require_file "${VERIFIED_CUTS}" \
  "Review ${HV_QC_DIR}/cut_review.proposed.csv and save the result as cut_review.verified.csv."

mkdir -p "${HV_SEG_DIR}" "${HV_ORDER_DIR}" "${HV_REVIEW_DIR}"

CUTS_FINGERPRINT="$(hv_file_fingerprint "${VERIFIED_CUTS}")"
SEGMENTS_SIGNATURE="v3|cuts=${CUTS_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/build_segments_from_jumps.py)|frame_count=${FRAME_COUNT:-auto}"
SEGMENTS_SIGNATURE="${SEGMENTS_SIGNATURE}|count_frames=${COUNT_FRAMES:-0}"

if hv_step_needed "${SEGMENTS_DONE}" "${SEGMENTS_SIGNATURE}" "${SEGMENTS}"; then
  rm -f "${SEGMENTS_DONE}" "${ORDER_DONE}" "${REVIEW_DONE}" "${STAGE1A_DONE}"
  BUILD_SEGMENTS=(
    uv run --no-sync python src/resequence/build_segments_from_jumps.py
    "${RESEQ_PATH}"
    --jumps "${VERIFIED_CUTS}"
    --input-kind cut-review
    --out "${SEGMENTS}"
  )
  if [ -n "${FRAME_COUNT:-}" ]; then BUILD_SEGMENTS+=(--frame-count "${FRAME_COUNT}"); fi
  if [ "${COUNT_FRAMES:-0}" = "1" ]; then BUILD_SEGMENTS+=(--count-frames); fi
  hv_time_step "build_segments" "${BUILD_SEGMENTS[@]}"
  hv_require_file "${SEGMENTS}" "Segment construction completed without segments.csv."
  hv_mark_complete "${SEGMENTS_DONE}" "${SEGMENTS_SIGNATURE}"
fi

hv_require_file "${SEGMENTS}" "Segment definitions are missing; rerun stage 1a with FORCE=1."
SEGMENTS_FINGERPRINT="$(hv_file_fingerprint "${SEGMENTS}")"
ORDER_SIGNATURE="v3|segments=${SEGMENTS_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/order_video_segments.py)|window=${WINDOW_FRAMES:-10}"
ORDER_SIGNATURE="${ORDER_SIGNATURE}|signature=${SIGNATURE:-trajectory}|top_k=${TOP_K:-10}"
ORDER_SIGNATURE="${ORDER_SIGNATURE}|sample_width=${ORDER_SAMPLE_WIDTH:-default}"

if hv_step_needed \
    "${ORDER_DONE}" "${ORDER_SIGNATURE}" "${RANKED_EDGES}" "${GREEDY_ORDER}"; then
  rm -f "${ORDER_DONE}" "${REVIEW_DONE}" "${STAGE1A_DONE}"
  ORDER=(
    uv run --no-sync python src/resequence/order_video_segments.py
    --segments "${SEGMENTS}"
    --out "${HV_ORDER_DIR}"
    --window-frames "${WINDOW_FRAMES:-10}"
    --signature "${SIGNATURE:-trajectory}"
    --top-k "${TOP_K:-10}"
  )
  if [ -n "${ORDER_SAMPLE_WIDTH:-}" ]; then ORDER+=(--sample-width "${ORDER_SAMPLE_WIDTH}"); fi
  hv_time_step "order_segments" "${ORDER[@]}"
  hv_require_file "${RANKED_EDGES}" "Ordering completed without ranked_edges.csv."
  hv_require_file "${GREEDY_ORDER}" "Ordering completed without greedy_order.csv."
  hv_mark_complete "${ORDER_DONE}" "${ORDER_SIGNATURE}"
fi

hv_require_file "${RANKED_EDGES}" "Ranked edges are missing; rerun stage 1a with FORCE=1."
hv_require_file "${GREEDY_ORDER}" "Greedy order is missing; rerun stage 1a with FORCE=1."
RANKED_FINGERPRINT="$(hv_file_fingerprint "${RANKED_EDGES}")"
ORDER_FINGERPRINT="$(hv_file_fingerprint "${GREEDY_ORDER}")"
REVIEW_SIGNATURE="v3|segments=${SEGMENTS_FINGERPRINT}|ranked=${RANKED_FINGERPRINT}"
REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|order=${ORDER_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/diagnostics/make_join_review_video.py)"
REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|limit=${JOIN_REVIEW_LIMIT:-all}"
REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|seconds=${JOIN_REVIEW_SECONDS:-default}"

if hv_step_needed "${REVIEW_DONE}" "${REVIEW_SIGNATURE}" "${JOIN_REVIEW}" "${JOIN_CAPTIONS}"; then
  rm -f "${REVIEW_DONE}" "${STAGE1A_DONE}"
  REVIEW=(
    uv run --no-sync python src/resequence/diagnostics/make_join_review_video.py
    "${RESEQ_PATH}"
    --ranked-edges "${RANKED_EDGES}"
    --segments "${SEGMENTS}"
    --order-csv "${GREEDY_ORDER}"
    --out "${JOIN_REVIEW}"
  )
  if [ -n "${JOIN_REVIEW_LIMIT:-}" ]; then REVIEW+=(--limit "${JOIN_REVIEW_LIMIT}"); fi
  if [ -n "${JOIN_REVIEW_SECONDS:-}" ]; then
    REVIEW+=(--seconds-each-side "${JOIN_REVIEW_SECONDS}")
  fi
  hv_time_step "join_review_video" "${REVIEW[@]}"
  hv_require_file "${JOIN_REVIEW}" "Join-review rendering completed without an output video."
  hv_require_file "${JOIN_CAPTIONS}" "Join-review rendering completed without captions."
  hv_mark_complete "${REVIEW_DONE}" "${REVIEW_SIGNATURE}"
fi

STAGE1A_SIGNATURE="v1|cuts=${CUTS_FINGERPRINT}|segments=${SEGMENTS_SIGNATURE}"
STAGE1A_SIGNATURE="${STAGE1A_SIGNATURE}|order=${ORDER_SIGNATURE}|review=${REVIEW_SIGNATURE}"
hv_mark_complete "${STAGE1A_DONE}" "${STAGE1A_SIGNATURE}"

cat <<EOF

Stage 1a complete for ${RESEQ_KEY}.

  segments          : ${SEGMENTS}
  greedy order      : ${GREEDY_ORDER}
  green-flash review: ${JOIN_REVIEW}
  captions          : ${JOIN_CAPTIONS}

Inspect the green-flash review before committing the long reassembly run.
The ordering itself remains the established automatic trajectory/10-frame
procedure; this stage separates its visual QA from Stage 2's render/upload.
EOF
