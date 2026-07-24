#!/bin/bash
# Resequencing stage 1: detect discontinuities and prepare the manual cut review.
#
#   sbatch src/pipeline/slurm/resequence/resequence_stage1_array.sh
#
# Runs, per array task:
#   1. detect_video_discontinuities   -> qc/candidates.csv
#   2. summarize_jump_events          -> qc/jump_events.csv
#   3. prepare_cut_review             -> qc/cut_review.proposed.csv
#
# It stops there on purpose. Inspect the candidate before/after frames and the
# proposed cut table, edit keep/prev_frame_idx, and save the result as
# qc/cut_review.verified.csv. Stage 2 refuses to run without that file.
#
# A step is skipped only after its command writes a completion marker, so a
# task killed while writing output reruns that step. Set FORCE=1 to redo all.
#
# TOP_N defaults to 400 so the detector does not truncate the roughly 135-150
# single-jump events used by the established start03/start04 procedure.
# Override detection settings only for a separately reviewed plan:
#
#   sbatch --export=ALL,SAMPLE_WIDTH=256,TOP_N=400 \
#       src/pipeline/slurm/resequence/resequence_stage1_array.sh

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

hv_require_file "${RESEQ_PATH}" \
  "Run download_raw_array.sh first, or set DOWNLOAD_DIR to where the raw video lives."

mkdir -p "${HV_QC_DIR}"

CANDIDATES="${HV_QC_DIR}/candidates.csv"
EVENTS="${HV_QC_DIR}/jump_events.csv"
CUT_PROPOSAL="${HV_QC_DIR}/cut_review.proposed.csv"
DETECT_DONE="${HV_QC_DIR}/.detect.complete"
EVENTS_DONE="${HV_QC_DIR}/.summarize.complete"
CUT_REVIEW_DONE="${HV_QC_DIR}/.cut_review.complete"

DETECT_SIGNATURE="v2|key=${RESEQ_KEY}|tool=$(hv_file_fingerprint \
  src/resequence/detect_video_discontinuities.py)|top_n=${TOP_N:-400}"
DETECT_SIGNATURE="${DETECT_SIGNATURE}|sample_width=${SAMPLE_WIDTH:-default}"
DETECT_SIGNATURE="${DETECT_SIGNATURE}|mad_z=${MAD_Z:-default}"
DETECT_SIGNATURE="${DETECT_SIGNATURE}|min_distance=${MIN_DISTANCE:-default}"
DETECT_SIGNATURE="${DETECT_SIGNATURE}|threshold_mode=${THRESHOLD_MODE:-default}"
DETECT_SIGNATURE="${DETECT_SIGNATURE}|expected_interval=${EXPECTED_INTERVAL_FRAMES:-default}"

if hv_step_needed "${DETECT_DONE}" "${DETECT_SIGNATURE}" "${CANDIDATES}"; then
  rm -f "${DETECT_DONE}" "${EVENTS_DONE}" "${CUT_REVIEW_DONE}"
  DETECT=(
    uv run --no-sync python src/resequence/detect_video_discontinuities.py
    "${RESEQ_PATH}"
    --out "${HV_QC_DIR}"
    --top-n "${TOP_N:-400}"
    # Long jobs: keep the log readable rather than one line every 10 seconds.
    --progress-every-seconds "${PROGRESS_EVERY_SECONDS:-300}"
  )
  if [ -n "${SAMPLE_WIDTH:-}" ]; then DETECT+=(--sample-width "${SAMPLE_WIDTH}"); fi
  if [ -n "${MAD_Z:-}" ]; then DETECT+=(--mad-z "${MAD_Z}"); fi
  if [ -n "${MIN_DISTANCE:-}" ]; then DETECT+=(--min-distance "${MIN_DISTANCE}"); fi
  if [ -n "${THRESHOLD_MODE:-}" ]; then DETECT+=(--threshold-mode "${THRESHOLD_MODE}"); fi
  if [ -n "${EXPECTED_INTERVAL_FRAMES:-}" ]; then
    DETECT+=(--expected-interval-frames "${EXPECTED_INTERVAL_FRAMES}")
  fi
  hv_time_step "detect_discontinuities" "${DETECT[@]}"
  hv_require_file "${CANDIDATES}" "Detection completed without candidates.csv."
  hv_mark_complete "${DETECT_DONE}" "${DETECT_SIGNATURE}"
fi

hv_require_file "${CANDIDATES}" \
  "Detection output is missing; rerun stage 1 with FORCE=1."
CANDIDATES_FINGERPRINT="$(hv_file_fingerprint "${CANDIDATES}")"
EVENTS_SIGNATURE="v2|candidates=${CANDIDATES_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/summarize_jump_events.py)|fps=${FPS:-default}"
EVENTS_SIGNATURE="${EVENTS_SIGNATURE}|max_gap=${MAX_GAP_FRAMES:-default}"

if hv_step_needed "${EVENTS_DONE}" "${EVENTS_SIGNATURE}" "${EVENTS}"; then
  rm -f "${EVENTS_DONE}" "${CUT_REVIEW_DONE}"
  SUMMARIZE=(
    uv run --no-sync python src/resequence/summarize_jump_events.py
    --candidates "${CANDIDATES}"
    --out "${EVENTS}"
  )
  if [ -n "${FPS:-}" ]; then SUMMARIZE+=(--fps "${FPS}"); fi
  if [ -n "${MAX_GAP_FRAMES:-}" ]; then SUMMARIZE+=(--max-gap-frames "${MAX_GAP_FRAMES}"); fi
  hv_time_step "summarize_jump_events" "${SUMMARIZE[@]}"
  hv_require_file "${EVENTS}" "Jump-event summarization completed without an output CSV."
  hv_mark_complete "${EVENTS_DONE}" "${EVENTS_SIGNATURE}"
fi

hv_require_file "${EVENTS}" \
  "Jump-event summary is missing; rerun stage 1 with FORCE=1."
EVENTS_FINGERPRINT="$(hv_file_fingerprint "${EVENTS}")"
CUT_REVIEW_SIGNATURE="v2|events=${EVENTS_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/prepare_cut_review.py)|proposal=single-jump"

if hv_step_needed \
    "${CUT_REVIEW_DONE}" "${CUT_REVIEW_SIGNATURE}" "${CUT_PROPOSAL}"; then
  rm -f "${CUT_REVIEW_DONE}"
  hv_time_step "prepare_cut_review" \
    uv run --no-sync python src/resequence/prepare_cut_review.py \
      --events "${EVENTS}" \
      --out "${CUT_PROPOSAL}"
  hv_require_file "${CUT_PROPOSAL}" "Cut-review preparation completed without an output CSV."
  hv_mark_complete "${CUT_REVIEW_DONE}" "${CUT_REVIEW_SIGNATURE}"
fi

cat <<EOF

Stage 1 complete for ${RESEQ_KEY}.

  candidate frames : ${HV_QC_DIR}/candidates/
  event summary    : ${EVENTS}
  proposed cuts    : ${CUT_PROPOSAL}

Next: inspect the candidate frames and proposed cuts. Edit keep and
prev_frame_idx as needed, then save the reviewed table as

  ${HV_QC_DIR}/cut_review.verified.csv

Stage 2 refuses to run without that file, so the manual check cannot be
skipped by accident.
EOF
