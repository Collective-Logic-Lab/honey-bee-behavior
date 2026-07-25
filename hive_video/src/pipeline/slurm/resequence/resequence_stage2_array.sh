#!/bin/bash
# Resequencing stage 2: consume verified cuts, order, reassemble, and back up.
#
#   sbatch src/pipeline/slurm/resequence/resequence_stage2_array.sh
#
# Assumes stage 1 has run and that you have inspected its discontinuity
# candidates and saved the reviewed cut table to
#
#   <work dir>/qc/cut_review.verified.csv
#
# The verified cuts are converted into segments, then ordered with the
# established trajectory signature and 10-frame windows used for start03 and
# start04. A green-flash QC video contains every join in that exact greedy
# order. Each array task also submits its own dependent upload job, which can
# start only after every stage succeeds and the final artifacts validate.

#SBATCH --job-name=bees-reseq2
#SBATCH --array=0-2
#SBATCH --cpus-per-task=8
#SBATCH --mem=192GB
#SBATCH -t 48:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.reseq2.%A_%a.out
#SBATCH -e slurm.reseq2.%A_%a.err
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

LOCATOR="$(hv_locator_for_task "${LOCATORS}" "${SLURM_ARRAY_TASK_ID:-0}")"
hv_resolve "${LOCATOR}"

VERIFIED_CUTS="${HV_QC_DIR}/cut_review.verified.csv"
SEGMENTS="${HV_SEG_DIR}/segments.csv"
RANKED_EDGES="${HV_ORDER_DIR}/ranked_edges.csv"
GREEDY_ORDER="${HV_ORDER_DIR}/greedy_order.csv"
JOIN_REVIEW="${HV_REVIEW_DIR}/join_review_greedy_order.mp4"
FINAL_VIDEO="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.mp4"
FINAL_MAPPING="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.frame_mapping.csv"

hv_require_file "${RESEQ_PATH}" "The raw video is gone; re-run download_raw_array.sh."
hv_require_file "${VERIFIED_CUTS}" \
  "Review ${HV_QC_DIR}/cut_review.proposed.csv and save the result as cut_review.verified.csv."

mkdir -p "${HV_SEG_DIR}" "${HV_ORDER_DIR}" "${HV_REVIEW_DIR}" "${HV_OUT_DIR}"

SEGMENTS_DONE="${HV_SEG_DIR}/.build_segments.complete"
ORDER_DONE="${HV_ORDER_DIR}/.order_segments.complete"
REVIEW_DONE="${HV_REVIEW_DIR}/.join_review.complete"
REASSEMBLE_DONE="${HV_OUT_DIR}/.reassemble.complete"
REASSEMBLE_INPUTS="${HV_OUT_DIR}/.reassemble.inputs"

CUTS_FINGERPRINT="$(hv_file_fingerprint "${VERIFIED_CUTS}")"
SEGMENTS_SIGNATURE="v2|cuts=${CUTS_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/build_segments_from_jumps.py)|frame_count=${FRAME_COUNT:-auto}"
SEGMENTS_SIGNATURE="${SEGMENTS_SIGNATURE}|count_frames=${COUNT_FRAMES:-0}"

if hv_step_needed "${SEGMENTS_DONE}" "${SEGMENTS_SIGNATURE}" "${SEGMENTS}"; then
  rm -f "${SEGMENTS_DONE}" "${ORDER_DONE}" "${REVIEW_DONE}" \
    "${REASSEMBLE_DONE}" "${REASSEMBLE_INPUTS}"
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

hv_require_file "${SEGMENTS}" \
  "Segment definitions are missing; rerun stage 2 with FORCE=1."
SEGMENTS_FINGERPRINT="$(hv_file_fingerprint "${SEGMENTS}")"
ORDER_SIGNATURE="v2|segments=${SEGMENTS_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/order_video_segments.py)|window=${WINDOW_FRAMES:-10}"
ORDER_SIGNATURE="${ORDER_SIGNATURE}|signature=${SIGNATURE:-trajectory}|top_k=${TOP_K:-10}"
ORDER_SIGNATURE="${ORDER_SIGNATURE}|sample_width=${ORDER_SAMPLE_WIDTH:-default}"

if hv_step_needed \
    "${ORDER_DONE}" "${ORDER_SIGNATURE}" "${RANKED_EDGES}" "${GREEDY_ORDER}"; then
  rm -f "${ORDER_DONE}" "${REVIEW_DONE}" \
    "${REASSEMBLE_DONE}" "${REASSEMBLE_INPUTS}"
  ORDER=(
    uv run --no-sync python src/resequence/order_video_segments.py
    --segments "${SEGMENTS}"
    --out "${HV_ORDER_DIR}"
    --window-frames "${WINDOW_FRAMES:-10}"
    --signature "${SIGNATURE:-trajectory}"
    --top-k "${TOP_K:-10}"
  )
  if [ -n "${ORDER_SAMPLE_WIDTH:-}" ]; then
    ORDER+=(--sample-width "${ORDER_SAMPLE_WIDTH}")
  fi
  hv_time_step "order_segments" "${ORDER[@]}"
  hv_require_file "${RANKED_EDGES}" "Ordering completed without ranked_edges.csv."
  hv_require_file "${GREEDY_ORDER}" "Ordering completed without greedy_order.csv."
  hv_mark_complete "${ORDER_DONE}" "${ORDER_SIGNATURE}"
fi

hv_require_file "${RANKED_EDGES}" \
  "Ranked edges are missing; rerun stage 2 with FORCE=1."
hv_require_file "${GREEDY_ORDER}" \
  "Greedy order is missing; rerun stage 2 with FORCE=1."
RANKED_FINGERPRINT="$(hv_file_fingerprint "${RANKED_EDGES}")"
ORDER_FINGERPRINT="$(hv_file_fingerprint "${GREEDY_ORDER}")"
REVIEW_SIGNATURE="v2|segments=${SEGMENTS_FINGERPRINT}|ranked=${RANKED_FINGERPRINT}"
REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|order=${ORDER_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/diagnostics/make_join_review_video.py)"
REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|limit=${JOIN_REVIEW_LIMIT:-all}"
REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|seconds=${JOIN_REVIEW_SECONDS:-default}"

if hv_step_needed "${REVIEW_DONE}" "${REVIEW_SIGNATURE}" "${JOIN_REVIEW}"; then
  rm -f "${REVIEW_DONE}"
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
  hv_mark_complete "${REVIEW_DONE}" "${REVIEW_SIGNATURE}"
fi

# Queue the backup now so it starts the moment this task succeeds, on its own
# wall clock rather than eating into the reassembly budget.
if [ "${SKIP_UPLOAD:-0}" != "1" ] && [ -n "${SLURM_JOB_ID:-}" ]; then
  UPLOAD_JOB=$(sbatch --parsable \
    --dependency="afterok:${SLURM_JOB_ID}" \
    --kill-on-invalid-dep=yes \
    --export="ALL,HV_UPLOAD_KEY=${RESEQ_KEY},HV_UPLOAD_WORK_DIR=${HV_WORK_DIR}" \
    "${SCRIPT_DIR}/resequence_upload.sh")
  echo "queued upload job ${UPLOAD_JOB}, dependent on ${SLURM_JOB_ID}"
fi

REASSEMBLE=(
  uv run --no-sync python src/resequence/reassemble_video_from_segments.py
  --segments "${SEGMENTS}"
  --ranked-edges "${RANKED_EDGES}"
  --order-csv "${GREEDY_ORDER}"
  --require-complete-order
  --out "${FINAL_VIDEO}"
  --safeword-file "${HV_WORK_DIR}/.safeword"
)
if [ -n "${SCALE_WIDTH:-}" ]; then REASSEMBLE+=(--scale-width "${SCALE_WIDTH}"); fi
if [ -n "${FPS:-}" ]; then REASSEMBLE+=(--fps "${FPS}"); fi
if [ -n "${SEGMENT_CHUNK_SIZE:-}" ]; then
  REASSEMBLE+=(--segment-chunk-size "${SEGMENT_CHUNK_SIZE}")
fi
if [ -n "${EDGE_RANK_LIMIT:-}" ]; then REASSEMBLE+=(--edge-rank-limit "${EDGE_RANK_LIMIT}"); fi

REASSEMBLE_SIGNATURE="v2|segments=${SEGMENTS_FINGERPRINT}|ranked=${RANKED_FINGERPRINT}"
REASSEMBLE_SIGNATURE="${REASSEMBLE_SIGNATURE}|order=${ORDER_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/reassemble_video_from_segments.py)"
REASSEMBLE_SIGNATURE="${REASSEMBLE_SIGNATURE}|scale_width=${SCALE_WIDTH:-default}"
REASSEMBLE_SIGNATURE="${REASSEMBLE_SIGNATURE}|fps=${FPS:-default}"
REASSEMBLE_SIGNATURE="${REASSEMBLE_SIGNATURE}|chunk_size=${SEGMENT_CHUNK_SIZE:-default}"
REASSEMBLE_SIGNATURE="${REASSEMBLE_SIGNATURE}|edge_rank_limit=${EDGE_RANK_LIMIT:-default}"

REASSEMBLE_OVERWRITE=0
if [ "${FORCE:-0}" = "1" ] || [ "${OVERWRITE:-0}" = "1" ]; then
  REASSEMBLE_OVERWRITE=1
elif [ ! -f "${REASSEMBLE_INPUTS}" ] || \
    [ "$(cat "${REASSEMBLE_INPUTS}")" != "${REASSEMBLE_SIGNATURE}" ]; then
  REASSEMBLE_OVERWRITE=1
  echo "--- inputs changed; rebuilding reassembly outputs"
fi
if [ "${REASSEMBLE_OVERWRITE}" = "1" ]; then REASSEMBLE+=(--overwrite); fi

# Record the active inputs before rendering. If the job is interrupted, a
# retry with the same signature can validate and resume completed part files.
hv_mark_complete "${REASSEMBLE_INPUTS}" "${REASSEMBLE_SIGNATURE}"
hv_time_step "reassemble" "${REASSEMBLE[@]}"
hv_require_file "${FINAL_VIDEO}" "Reassembly exited without a final video."
hv_require_file "${FINAL_MAPPING}" "Reassembly exited without a final frame mapping."
hv_mark_complete "${REASSEMBLE_DONE}" "${REASSEMBLE_SIGNATURE}"

echo
echo "Stage 2 complete for ${RESEQ_KEY}."
echo "  final video: ${FINAL_VIDEO}"
