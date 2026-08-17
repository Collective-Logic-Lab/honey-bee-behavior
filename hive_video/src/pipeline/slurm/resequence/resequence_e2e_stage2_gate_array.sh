#!/bin/bash
# File every Stage 1a outcome, then render and compress only cleared videos.
#
# This is the Stage 2 worker for tracked unattended resequencing pilots. Submit
# it only through a versioned parent launcher so the locators, provenance mode,
# dependencies, pilot-evidence destination, and canonical release destination
# are fixed together.
#
# A manual_review_required result is a successful scientific outcome here:
# its compact report bundle is published and the task stops without requesting
# a final render. An auto_pass result runs the ordinary Stage 2 worker in this
# allocation; Stage 2 queues its archival upload, and this gate queues the
# selected compressed derivative on a separate dependent allocation.

#SBATCH --job-name=bees-e2e-stage2
#SBATCH --array=0-3%1
#SBATCH --cpus-per-task=8
#SBATCH --mem=192GB
#SBATCH -t 48:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.e2e-stage2.%A_%a.out
#SBATCH -e slurm.e2e-stage2.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

: "${LOCATORS:?LOCATORS must be supplied by the tracked pilot launcher.}"
: "${E2E_PILOT_ID:?E2E_PILOT_ID must be supplied by the tracked pilot launcher.}"
: "${E2E_PILOT_QUALITY:?E2E_PILOT_QUALITY must be supplied by the tracked pilot launcher.}"
: "${E2E_EXPECTED_GIT_REVISION:?The tracked pilot revision is required.}"
: "${HF_PILOT_PREFIX:?The tracked pilot evidence prefix is required.}"

case "${E2E_PILOT_ID}" in
  start01_start02_side0_top_v1|start01_start02_side0_top_v2)
    EXPECTED_LOCATORS="start1_side0_top start2_side0_top"
    ;;
  start03_start38_both_sides_top_v1)
    EXPECTED_LOCATORS="start3_side0_top start3_side1_top start38_side0_top start38_side1_top"
    ;;
  *)
    echo "Unexpected E2E_PILOT_ID: ${E2E_PILOT_ID}" >&2
    exit 2
    ;;
esac
if [ "${LOCATORS}" != "${EXPECTED_LOCATORS}" ]; then
  echo "Unexpected pilot locators: ${LOCATORS}" >&2
  echo "Expected for ${E2E_PILOT_ID}: ${EXPECTED_LOCATORS}" >&2
  exit 2
fi
if [ "${E2E_PILOT_QUALITY}" != "low" ]; then
  echo "The tracked pilot compression quality must be low; got ${E2E_PILOT_QUALITY}" >&2
  exit 2
fi

hv_sync_env

LOCATOR="$(hv_locator_for_task "${LOCATORS}" "${SLURM_ARRAY_TASK_ID:-0}")"
hv_resolve "${LOCATOR}"

PROPOSED_CUTS="${HV_QC_DIR}/cut_review.proposed.csv"
VERIFIED_CUTS="${HV_QC_DIR}/cut_review.verified.csv"
DETECT_METADATA="${HV_QC_DIR}/metadata.json"
CANDIDATES="${HV_QC_DIR}/candidates.csv"
EVENTS="${HV_QC_DIR}/jump_events.csv"
SEGMENTS="${HV_SEG_DIR}/segments.csv"
RANKED_EDGES="${HV_ORDER_DIR}/ranked_edges.csv"
GREEDY_ORDER="${HV_ORDER_DIR}/greedy_order.csv"
AUTO_QC_SCORES="${HV_REVIEW_DIR}/auto_qc.join_scores.csv"
AUTO_QC_FLAGGED="${HV_REVIEW_DIR}/auto_qc.flagged_joins.csv"
AUTO_QC_SUMMARY="${HV_REVIEW_DIR}/auto_qc.summary.json"
AUTO_QC_DONE="${HV_REVIEW_DIR}/.auto_qc.complete"
STAGE1A_DONE="${HV_REVIEW_DIR}/.stage1a.complete"
FLAGGED_QC_ROLL="${HV_REVIEW_DIR}/qc_roll_flagged_joins.mp4"
FLAGGED_QC_CAPTIONS="${HV_REVIEW_DIR}/qc_roll_flagged_joins.captions.csv"

for required in \
  "${PROPOSED_CUTS}" \
  "${DETECT_METADATA}" \
  "${CANDIDATES}" \
  "${EVENTS}" \
  "${SEGMENTS}" \
  "${RANKED_EDGES}" \
  "${GREEDY_ORDER}" \
  "${AUTO_QC_SCORES}" \
  "${AUTO_QC_FLAGGED}" \
  "${AUTO_QC_SUMMARY}" \
  "${AUTO_QC_DONE}" \
  "${STAGE1A_DONE}"; do
  hv_require_file "${required}" "Stage 1 or Stage 1a did not finish for ${RESEQ_KEY}."
done

CUT_REVIEW_STATUS="$(hv_stage1a_cut_review_status "${STAGE1A_DONE}")"
if [ "${CUT_REVIEW_STATUS}" != "unreviewed_pilot" ]; then
  echo "The unattended pilot requires cut_review_status=unreviewed_pilot; got" \
    "${CUT_REVIEW_STATUS}" >&2
  exit 4
fi
if [ -f "${VERIFIED_CUTS}" ]; then
  echo "The unattended pilot found an unexpected verified cut table: ${VERIFIED_CUTS}" >&2
  exit 4
fi
CUTS_FINGERPRINT="$(hv_file_fingerprint "${PROPOSED_CUTS}")"
STAGE1A_CUT_PREFIX="v3|cuts_file=$(basename "${PROPOSED_CUTS}")"
STAGE1A_CUT_PREFIX="${STAGE1A_CUT_PREFIX}|cuts=${CUTS_FINGERPRINT}"
STAGE1A_CUT_PREFIX="${STAGE1A_CUT_PREFIX}|cut_review_status=unreviewed_pilot|"
if ! grep -Fq "${STAGE1A_CUT_PREFIX}" "${STAGE1A_DONE}"; then
  echo "Stage 1a marker does not bind the current unreviewed cut proposal." >&2
  exit 4
fi
if ! grep -Fq "|git_revision=${E2E_EXPECTED_GIT_REVISION}|" "${STAGE1A_DONE}"; then
  echo "Stage 1a marker was produced by a different Git revision." >&2
  exit 4
fi

AUTO_QC_OUTPUT_SIGNATURE="outputs=$(hv_file_bundle_fingerprint \
  "${AUTO_QC_SCORES}" "${AUTO_QC_FLAGGED}" "${AUTO_QC_SUMMARY}")"
if ! grep -Fq "|${AUTO_QC_OUTPUT_SIGNATURE}" "${AUTO_QC_DONE}"; then
  echo "Auto-QC outputs do not match their completion marker; refusing to file them." >&2
  exit 4
fi
AUTO_QC_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_SUMMARY}")"
if ! grep -Fq "|auto_qc_report=${AUTO_QC_FINGERPRINT}|" "${STAGE1A_DONE}"; then
  echo "Stage 1a completion marker does not bind the current Auto-QC report." >&2
  exit 4
fi
AUTO_QC_BUNDLE_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_DONE}")"
if ! grep -Fq "|auto_qc_bundle=${AUTO_QC_BUNDLE_FINGERPRINT}|" "${STAGE1A_DONE}"; then
  echo "Stage 1a completion marker does not bind the current Auto-QC bundle." >&2
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
case "${AUTO_QC_DECISION}" in
  auto_pass) ;;
  manual_review_required)
    hv_require_file "${FLAGGED_QC_ROLL}" \
      "A flagged pilot must include its compact green-flash QC roll."
    hv_require_file "${FLAGGED_QC_CAPTIONS}" \
      "A flagged pilot must include its QC-roll captions."
    ;;
  *)
    echo "Unexpected Auto-QC decision: ${AUTO_QC_DECISION}" >&2
    exit 4
    ;;
esac

if [ -z "${HF_TOKEN:-}" ] && [ ! -f "${HF_HOME:-${HOME}/.cache/huggingface}/token" ]; then
  echo "No Hugging Face credentials found." >&2
  echo "Run 'hf auth login' on the cluster before launching the pilot." >&2
  exit 5
fi
uv run --no-sync hf auth whoami --format json

STAGING="${HV_WORK_DIR}/e2e_pilot_stage1a_upload"
COMMIT_DIR="${HV_WORK_DIR}/e2e_pilot_stage1a_commit"
REMOTE="${HF_PILOT_PREFIX}/stage1a/reseq_${RESEQ_KEY}"
REMOTE_PREFIX="${REMOTE#${HF_BUCKET}/}"
REMOTE_LISTING="${HV_WORK_DIR}/e2e_pilot_stage1a.remote_listing.json"

rm -rf "${STAGING}" "${COMMIT_DIR}"
mkdir -p "${STAGING}" "${COMMIT_DIR}"
cp "${CANDIDATES}" "${EVENTS}" "${PROPOSED_CUTS}" "${STAGING}/"
cp "${DETECT_METADATA}" "${STAGING}/detector_metadata.json"
cp "${SEGMENTS}" "${RANKED_EDGES}" "${GREEDY_ORDER}" "${STAGING}/"
cp "${AUTO_QC_SCORES}" "${AUTO_QC_FLAGGED}" "${AUTO_QC_SUMMARY}" "${STAGING}/"
cp "${AUTO_QC_DONE}" "${STAGING}/auto_qc.complete"
cp "${STAGE1A_DONE}" "${STAGING}/stage1a.complete"
if [ -f "${VERIFIED_CUTS}" ]; then
  cp "${VERIFIED_CUTS}" "${STAGING}/"
fi
if [ "${AUTO_QC_DECISION}" = "manual_review_required" ]; then
  cp "${FLAGGED_QC_ROLL}" "${FLAGGED_QC_CAPTIONS}" "${STAGING}/"
fi

cat >"${STAGING}/PILOT_STATUS.txt" <<EOF
pilot_id=${E2E_PILOT_ID}
locator=${LOCATOR}
key=${RESEQ_KEY}
cut_review_status=${CUT_REVIEW_STATUS}
auto_qc_decision=${AUTO_QC_DECISION}
git_revision=${E2E_EXPECTED_GIT_REVISION}
slurm_array_job_id=${SLURM_ARRAY_JOB_ID:-not_available}
slurm_array_task_id=${SLURM_ARRAY_TASK_ID:-not_available}
EOF
cat >"${STAGING}/README.md" <<EOF
# ${RESEQ_KEY}: unattended end-to-end pilot

This is the Stage 1a outcome from pilot \`${E2E_PILOT_ID}\`.

The Stage 1 source-cut proposal was intentionally **not manually inspected**.
Automatic QC checks the selected segment joins, but it cannot certify that
Stage 1 found every source cut. These artifacts are pilot evidence, not a
human-validated resequencing result.

- Auto-QC decision: \`${AUTO_QC_DECISION}\`
- Source-cut review status: \`${CUT_REVIEW_STATUS}\`
- \`CURRENT_STAGE1A.json\` is published last and copies the exact Auto-QC
  summary associated with the complete payload.
EOF

echo "Uploading Stage 1a pilot evidence ${STAGING} -> ${REMOTE}"
uv run --no-sync hf sync \
  "${STAGING}" \
  "${REMOTE}" \
  --no-delete \
  --exclude "**/.DS_Store"

uv run --no-sync hf buckets list "${REMOTE}" --recursive --format json \
  >"${REMOTE_LISTING}.partial"
mv "${REMOTE_LISTING}.partial" "${REMOTE_LISTING}"
uv run --no-sync python src/utils/verify_bucket_listing.py \
  --local-dir "${STAGING}" \
  --listing "${REMOTE_LISTING}" \
  --remote-prefix "${REMOTE_PREFIX}"

cp "${AUTO_QC_SUMMARY}" "${COMMIT_DIR}/CURRENT_STAGE1A.json"
uv run --no-sync hf buckets cp \
  "${COMMIT_DIR}/CURRENT_STAGE1A.json" \
  "${REMOTE}/CURRENT_STAGE1A.json"
uv run --no-sync hf buckets list "${REMOTE}" --recursive --format json \
  >"${REMOTE_LISTING}.partial"
mv "${REMOTE_LISTING}.partial" "${REMOTE_LISTING}"
uv run --no-sync python src/utils/verify_bucket_listing.py \
  --local-dir "${COMMIT_DIR}" \
  --listing "${REMOTE_LISTING}" \
  --remote-prefix "${REMOTE_PREFIX}"

if [ "${AUTO_QC_DECISION}" = "manual_review_required" ]; then
  echo
  echo "Stage 1a requested manual review for ${RESEQ_KEY}."
  echo "The report and flagged-join roll were filed at ${REMOTE}."
  echo "No Stage 2 render or compression job was submitted."
  exit 0
fi

echo
echo "Stage 1a automatically cleared ${RESEQ_KEY}; starting the ordinary Stage 2 worker."
bash "${SCRIPT_DIR}/resequence_stage2_array.sh"

if [ -n "${SLURM_JOB_ID:-}" ]; then
  COMPRESSION_JOB="$(sbatch --parsable \
    --array=0-0 \
    --dependency="afterok:${SLURM_JOB_ID}" \
    --kill-on-invalid-dep=yes \
    --export="ALL,LOCATORS=${LOCATOR},QUALITY=${E2E_PILOT_QUALITY}" \
    "${SCRIPT_DIR}/compress_resequenced_array.sh")"
  COMPRESSION_JOB="${COMPRESSION_JOB%%;*}"
  echo "queued ${E2E_PILOT_QUALITY} compression job ${COMPRESSION_JOB}," \
    "dependent on ${SLURM_JOB_ID}"
fi
