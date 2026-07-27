#!/bin/bash
# Resequencing stage 2: reassemble an auto-cleared or manually approved order.
#
#   sbatch src/pipeline/slurm/resequence/resequence_stage2_array.sh
#
# This is intentionally only the long final render. Stage 1a has already built
# the segments and trajectory/10-frame order and scored every selected join.
# Automatically cleared videos proceed directly. A flagged video proceeds only
# when its compact green-flash roll has a report-bound manual approval.

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

PROPOSED_CUTS="${HV_QC_DIR}/cut_review.proposed.csv"
VERIFIED_CUTS="${HV_QC_DIR}/cut_review.verified.csv"
DETECT_METADATA="${HV_QC_DIR}/metadata.json"
SEGMENTS="${HV_SEG_DIR}/segments.csv"
RANKED_EDGES="${HV_ORDER_DIR}/ranked_edges.csv"
GREEDY_ORDER="${HV_ORDER_DIR}/greedy_order.csv"
AUTO_QC_SCORES="${HV_REVIEW_DIR}/auto_qc.join_scores.csv"
AUTO_QC_FLAGGED="${HV_REVIEW_DIR}/auto_qc.flagged_joins.csv"
AUTO_QC_SUMMARY="${HV_REVIEW_DIR}/auto_qc.summary.json"
AUTO_QC_APPROVAL="${HV_REVIEW_DIR}/auto_qc.manual_approval.json"
AUTO_QC_DONE="${HV_REVIEW_DIR}/.auto_qc.complete"
FLAGGED_QC_ROLL="${HV_REVIEW_DIR}/qc_roll_flagged_joins.mp4"
FLAGGED_QC_ROLL_CAPTIONS="${HV_REVIEW_DIR}/qc_roll_flagged_joins.captions.csv"
STAGE1A_DONE="${HV_REVIEW_DIR}/.stage1a.complete"
FINAL_VIDEO="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.mp4"
FINAL_MAPPING="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.frame_mapping.csv"
FINAL_METADATA="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.metadata.json"
FINAL_ORDER="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.order.csv"
FINAL_PARTS_MANIFEST="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.parts_manifest.csv"
REASSEMBLE_DONE="${HV_OUT_DIR}/.reassemble.complete"
REASSEMBLE_INPUTS="${HV_OUT_DIR}/.reassemble.inputs"

hv_require_file "${RESEQ_PATH}" "The raw video is gone; re-run download_raw_array.sh."
hv_require_file "${PROPOSED_CUTS}" "Stage 1 cut proposal is missing; rerun resequence_stage1_array.sh."
hv_require_file "${DETECT_METADATA}" \
  "Stage 1 detector metadata is missing; rerun resequence_stage1_array.sh."
if [ -f "${VERIFIED_CUTS}" ]; then
  CUTS="${VERIFIED_CUTS}"
else
  CUTS="${PROPOSED_CUTS}"
fi
hv_require_file "${SEGMENTS}" \
  "Stage 1a outputs are missing; run resequence_stage1a_review_array.sh first."
hv_require_file "${RANKED_EDGES}" \
  "Stage 1a outputs are missing; run resequence_stage1a_review_array.sh first."
hv_require_file "${GREEDY_ORDER}" \
  "Stage 1a outputs are missing; run resequence_stage1a_review_array.sh first."
hv_require_file "${AUTO_QC_SCORES}" \
  "Stage 1a auto-QC scores are missing; rerun resequence_stage1a_review_array.sh."
hv_require_file "${AUTO_QC_FLAGGED}" \
  "Stage 1a flagged-join table is missing; rerun resequence_stage1a_review_array.sh."
hv_require_file "${AUTO_QC_SUMMARY}" \
  "Stage 1a auto-QC summary is missing; rerun resequence_stage1a_review_array.sh."
hv_require_file "${AUTO_QC_DONE}" \
  "Stage 1a auto-QC marker is missing; rerun resequence_stage1a_review_array.sh."
hv_require_file "${STAGE1A_DONE}" \
  "Stage 1a has not completed; run resequence_stage1a_review_array.sh first."

AUTO_QC_OUTPUT_SIGNATURE="outputs=$(hv_file_bundle_fingerprint \
  "${AUTO_QC_SCORES}" "${AUTO_QC_FLAGGED}" "${AUTO_QC_SUMMARY}")"
if ! grep -Fq "|${AUTO_QC_OUTPUT_SIGNATURE}" "${AUTO_QC_DONE}"; then
  echo "Auto-QC outputs do not match their completion marker; rerun Stage 1a." >&2
  exit 4
fi

CUTS_FINGERPRINT="$(hv_file_fingerprint "${CUTS}")"
CUT_REVIEW_STATUS="$(hv_stage1a_cut_review_status "${STAGE1A_DONE}")"
if [ "${CUT_REVIEW_STATUS}" = "unreviewed_pilot" ]; then
  if [ -z "${E2E_PILOT_ID:-}" ] || [ -z "${E2E_EXPECTED_GIT_REVISION:-}" ]; then
    echo "Unreviewed cuts may only render inside the tracked pilot context." >&2
    exit 4
  fi
  hv_require_pilot_context_if_set
  hv_require_expected_revision
  if ! grep -Fq \
      "|git_revision=${E2E_EXPECTED_GIT_REVISION}|" "${STAGE1A_DONE}"; then
    echo "Stage 1a marker does not match the tracked pilot revision." >&2
    exit 4
  fi
fi
STAGE1A_CUT_PREFIX="v3|cuts_file=$(basename "${CUTS}")|cuts=${CUTS_FINGERPRINT}"
STAGE1A_CUT_PREFIX="${STAGE1A_CUT_PREFIX}|cut_review_status=${CUT_REVIEW_STATUS}|"
if ! grep -Fq "${STAGE1A_CUT_PREFIX}" "${STAGE1A_DONE}"; then
  echo "Stage 1a was built from different cut-review inputs; rerun resequence_stage1a_review_array.sh." >&2
  exit 4
fi
AUTO_QC_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_SUMMARY}")"
if ! grep -Fq "|auto_qc_report=${AUTO_QC_FINGERPRINT}|" "${STAGE1A_DONE}"; then
  echo "Stage 1a was completed with a different auto-QC report; rerun Stage 1a." >&2
  exit 4
fi
AUTO_QC_BUNDLE_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_DONE}")"
if ! grep -Fq "|auto_qc_bundle=${AUTO_QC_BUNDLE_FINGERPRINT}|" "${STAGE1A_DONE}"; then
  echo "Stage 1a was completed with a different auto-QC artifact bundle; rerun Stage 1a." >&2
  exit 4
fi
uv run --no-sync python -c '
from pathlib import Path
import sys
from src.resequence.diagnostics.auto_qc_segment_joins import validate_summary_inputs

valid, message = validate_summary_inputs(*(Path(value) for value in sys.argv[1:]))
print(message)
raise SystemExit(0 if valid else 1)
' \
  "${AUTO_QC_SUMMARY}" \
  "${RESEQ_PATH}" \
  "${SEGMENTS}" \
  "${GREEDY_ORDER}" \
  "${DETECT_METADATA}"

AUTO_QC_DECISION="$(uv run --no-sync python -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["decision"])' \
  "${AUTO_QC_SUMMARY}")"
APPROVAL_FINGERPRINT="not_required"
case "${AUTO_QC_DECISION}" in
  auto_pass)
    echo "Automatic join QC passed; no manual join review is required."
    ;;
  manual_review_required)
    hv_require_file "${FLAGGED_QC_ROLL}" \
      "Flagged-join QC roll is missing; rerun resequence_stage1a_review_array.sh."
    hv_require_file "${FLAGGED_QC_ROLL_CAPTIONS}" \
      "Flagged-join captions are missing; rerun resequence_stage1a_review_array.sh."
    if [ ! -f "${AUTO_QC_APPROVAL}" ]; then
      echo "Automatic join QC requires manual review, but no approval exists." >&2
      echo "Inspect ${FLAGGED_QC_ROLL}, then run:" >&2
      echo "  uv run --no-sync python src/resequence/diagnostics/approve_manual_join_qc.py create \\" >&2
      echo "    --summary \"${AUTO_QC_SUMMARY}\" --out \"${AUTO_QC_APPROVAL}\"" >&2
      exit 4
    fi
    uv run --no-sync python src/resequence/diagnostics/approve_manual_join_qc.py check \
      --summary "${AUTO_QC_SUMMARY}" \
      --approval "${AUTO_QC_APPROVAL}"
    APPROVAL_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_APPROVAL}")"
    ;;
  *)
    echo "Unexpected auto-QC decision: ${AUTO_QC_DECISION}" >&2
    exit 4
    ;;
esac

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
REASSEMBLE_SIGNATURE="${REASSEMBLE_SIGNATURE}|auto_qc=${AUTO_QC_FINGERPRINT}"
REASSEMBLE_SIGNATURE="${REASSEMBLE_SIGNATURE}|approval=${APPROVAL_FINGERPRINT}"
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
hv_require_file "${FINAL_METADATA}" "Reassembly exited without final metadata."
hv_require_file "${FINAL_ORDER}" "Reassembly exited without its resolved order."
hv_require_file "${FINAL_PARTS_MANIFEST}" "Reassembly exited without its parts manifest."
REASSEMBLE_OUTPUT_SIGNATURE="outputs=video=$(hv_file_stat_fingerprint "${FINAL_VIDEO}")"
REASSEMBLE_OUTPUT_SIGNATURE="${REASSEMBLE_OUTPUT_SIGNATURE}|mapping=$(hv_file_fingerprint \
  "${FINAL_MAPPING}")"
REASSEMBLE_OUTPUT_SIGNATURE="${REASSEMBLE_OUTPUT_SIGNATURE}|metadata=$(hv_file_fingerprint \
  "${FINAL_METADATA}")"
REASSEMBLE_OUTPUT_SIGNATURE="${REASSEMBLE_OUTPUT_SIGNATURE}|order=$(hv_file_fingerprint \
  "${FINAL_ORDER}")"
REASSEMBLE_OUTPUT_SIGNATURE="${REASSEMBLE_OUTPUT_SIGNATURE}|parts=$(hv_file_fingerprint \
  "${FINAL_PARTS_MANIFEST}")"
hv_mark_complete \
  "${REASSEMBLE_DONE}" "${REASSEMBLE_SIGNATURE}|${REASSEMBLE_OUTPUT_SIGNATURE}"

echo
echo "Stage 2 complete for ${RESEQ_KEY}."
echo "  final video: ${FINAL_VIDEO}"
