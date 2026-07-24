#!/bin/bash
# Resequencing stage 2: reassemble the verified ordering, then back up to HuggingFace.
#
#   sbatch src/pipeline/slurm/resequence/resequence_stage2_array.sh
#
# Assumes stage 1 has run and that you have watched the green-flash join review
# video and written the corrected ordering to
#
#   <work dir>/order/greedy_order.verified.csv
#
# The job refuses to start without that file. If the greedy ordering was already
# correct, copy it across unchanged:
#
#   cp order/greedy_order.csv order/greedy_order.verified.csv
#
# Each array task submits its own dependent upload job up front, so the backup
# runs on a separate, shorter wall clock as soon as that task succeeds. The
# reassembly itself is restartable: it writes part videos, skips completed
# parts, and honours .safeword between parts, so resubmitting a task that hit
# the wall clock picks up where it left off.

#SBATCH --job-name=bees-reseq2
#SBATCH --array=0-2
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB
#SBATCH -t 48:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.reseq2.%A_%a.out
#SBATCH -e slurm.reseq2.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
source "${SCRIPT_DIR}/common.sh"

LOCATORS=${LOCATORS:-"day4_side1_top day47_side0_top day47_side1_top"}

hv_sync_env

LOCATOR="$(hv_locator_for_task "${LOCATORS}" "${SLURM_ARRAY_TASK_ID:-0}")"
hv_resolve "${LOCATOR}"

SEGMENTS="${HV_SEG_DIR}/segments.csv"
RANKED_EDGES="${HV_ORDER_DIR}/ranked_edges.csv"
VERIFIED_ORDER="${HV_ORDER_DIR}/greedy_order.verified.csv"
FINAL_VIDEO="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.mp4"

hv_require_file "${RESEQ_PATH}" "The raw video is gone; re-run download_raw_array.sh."
hv_require_file "${SEGMENTS}" "Stage 1 has not produced segments for this locator yet."
hv_require_file "${RANKED_EDGES}" "Stage 1 has not produced ranked edges for this locator yet."
hv_require_file "${VERIFIED_ORDER}" \
  "Watch ${HV_REVIEW_DIR}/join_review_rank1.mp4, then save the corrected ordering there."

mkdir -p "${HV_OUT_DIR}"

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
  --order-csv "${VERIFIED_ORDER}"
  --out "${FINAL_VIDEO}"
  --safeword-file "${HV_WORK_DIR}/.safeword"
)
if [ -n "${SCALE_WIDTH:-}" ]; then REASSEMBLE+=(--scale-width "${SCALE_WIDTH}"); fi
if [ -n "${FPS:-}" ]; then REASSEMBLE+=(--fps "${FPS}"); fi
if [ -n "${SEGMENT_CHUNK_SIZE:-}" ]; then
  REASSEMBLE+=(--segment-chunk-size "${SEGMENT_CHUNK_SIZE}")
fi
if [ -n "${EDGE_RANK_LIMIT:-}" ]; then REASSEMBLE+=(--edge-rank-limit "${EDGE_RANK_LIMIT}"); fi
if [ "${OVERWRITE:-0}" = "1" ]; then REASSEMBLE+=(--overwrite); fi

hv_time_step "reassemble" "${REASSEMBLE[@]}"

echo
echo "Stage 2 complete for ${RESEQ_KEY}."
echo "  final video: ${FINAL_VIDEO}"
