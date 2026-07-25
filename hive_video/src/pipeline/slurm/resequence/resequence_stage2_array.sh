#!/bin/bash
# Resequencing stage 2: reassemble the Stage 1a-approved order and back it up.
#
#   sbatch src/pipeline/slurm/resequence/resequence_stage2_array.sh
#
# This is intentionally only the long final render. Stage 1a has already built
# the segments and trajectory/10-frame order and created the green-flash review
# MP4. Keeping the visual review outside this job lets an operator inspect it
# before spending the Stage 2 wall clock and starting the dependent upload.

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
hv_require_ffmpeg

LOCATOR="$(hv_locator_for_task "${LOCATORS}" "${SLURM_ARRAY_TASK_ID:-0}")"
hv_resolve "${LOCATOR}"

VERIFIED_CUTS="${HV_QC_DIR}/cut_review.verified.csv"
SEGMENTS="${HV_SEG_DIR}/segments.csv"
RANKED_EDGES="${HV_ORDER_DIR}/ranked_edges.csv"
GREEDY_ORDER="${HV_ORDER_DIR}/greedy_order.csv"
JOIN_REVIEW="${HV_REVIEW_DIR}/join_review_greedy_order.mp4"
JOIN_CAPTIONS="${HV_REVIEW_DIR}/join_review_greedy_order.captions.csv"
STAGE1A_DONE="${HV_REVIEW_DIR}/.stage1a.complete"
FINAL_VIDEO="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.mp4"
FINAL_MAPPING="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.frame_mapping.csv"
REASSEMBLE_DONE="${HV_OUT_DIR}/.reassemble.complete"
REASSEMBLE_INPUTS="${HV_OUT_DIR}/.reassemble.inputs"

hv_require_file "${RESEQ_PATH}" "The raw video is gone; re-run download_raw_array.sh."
hv_require_file "${VERIFIED_CUTS}" \
  "Stage 1a needs ${HV_QC_DIR}/cut_review.verified.csv; do not bypass the cut review."
hv_require_file "${SEGMENTS}" \
  "Stage 1a outputs are missing; run resequence_stage1a_review_array.sh first."
hv_require_file "${RANKED_EDGES}" \
  "Stage 1a outputs are missing; run resequence_stage1a_review_array.sh first."
hv_require_file "${GREEDY_ORDER}" \
  "Stage 1a outputs are missing; run resequence_stage1a_review_array.sh first."
hv_require_file "${JOIN_REVIEW}" \
  "Stage 1a green-flash review is missing; run resequence_stage1a_review_array.sh first."
hv_require_file "${JOIN_CAPTIONS}" \
  "Stage 1a review captions are missing; rerun resequence_stage1a_review_array.sh."
hv_require_file "${STAGE1A_DONE}" \
  "Stage 1a has not completed; run resequence_stage1a_review_array.sh first."

CUTS_FINGERPRINT="$(hv_file_fingerprint "${VERIFIED_CUTS}")"
if ! grep -Fq "v1|cuts=${CUTS_FINGERPRINT}" "${STAGE1A_DONE}"; then
  echo "Stage 1a was built from different verified cuts; rerun resequence_stage1a_review_array.sh." >&2
  exit 4
fi

mkdir -p "${HV_OUT_DIR}"
SEGMENTS_FINGERPRINT="$(hv_file_fingerprint "${SEGMENTS}")"
RANKED_FINGERPRINT="$(hv_file_fingerprint "${RANKED_EDGES}")"
ORDER_FINGERPRINT="$(hv_file_fingerprint "${GREEDY_ORDER}")"

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

REASSEMBLE_SIGNATURE="v3|segments=${SEGMENTS_FINGERPRINT}|ranked=${RANKED_FINGERPRINT}"
REASSEMBLE_SIGNATURE="${REASSEMBLE_SIGNATURE}|order=${ORDER_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/reassemble_video_from_segments.py)"
REASSEMBLE_SIGNATURE="${REASSEMBLE_SIGNATURE}|stage1a=$(hv_file_fingerprint "${STAGE1A_DONE}")"
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
