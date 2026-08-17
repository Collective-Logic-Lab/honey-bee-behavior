#!/bin/bash
# Submit the bounded unattended Start 03 / Start 38, both-sides-top pipeline
# pilot.
#
# Run with no arguments from any directory:
#
#   bash src/pipeline/slurm/resequence/submit_start03_start38_both_sides_top_e2e_v1.sh
#
# The tracked plan is intentionally fixed. It verifies the exact four archive
# inputs and their actual media redirect paths before allocating Slurm jobs,
# then records the complete dependency chain before releasing downloads.

set -eu

if [ "$#" -ne 0 ]; then
  echo "This is a zero-argument tracked launcher; edit and review it for a new plan." >&2
  exit 2
fi
if [ -n "${SLURM_JOB_ID:-}" ]; then
  echo "Run this submitter on a Sol login node, not inside a Slurm allocation." >&2
  exit 2
fi

while IFS='=' read -r variable _; do
  case "${variable}" in
    SBATCH_*)
      echo "Refusing inherited scheduler override: ${variable}" >&2
      exit 2
      ;;
  esac
done < <(env)

for variable in \
  FORCE OVERWRITE SKIP_UPLOAD DRY_RUN \
  LOCATORS RETRIES PROGRESS_EVERY_SECONDS \
  TOP_N SAMPLE_WIDTH MAD_Z MIN_DISTANCE THRESHOLD_MODE EXPECTED_INTERVAL_FRAMES \
  FPS MAX_GAP_FRAMES FRAME_COUNT COUNT_FRAMES \
  WINDOW_FRAMES SIGNATURE TOP_K ORDER_SAMPLE_WIDTH \
  AUTO_QC_MAX_ROBUST_Z AUTO_QC_MIN_MARGIN_RATIO AUTO_QC_PROGRESS_EVERY_SECONDS \
  WRITE_ALL_QC_ROLLS JOIN_REVIEW_LIMIT JOIN_REVIEW_SECONDS \
  SCALE_WIDTH SEGMENT_CHUNK_SIZE EDGE_RANK_LIMIT \
  QUALITY COMPRESS_PRESET CUT_REVIEW_STATUS \
  E2E_PILOT_ID E2E_PILOT_QUALITY \
  SCRATCH_ROOT DOWNLOAD_DIR RESEQ_ROOT HF_BUCKET HF_RESEQ_PREFIX HF_PILOT_PREFIX \
  SSL_CERT_FILE UPLOAD_MANIFEST_HASH_MAX_BYTES; do
  if [ "${!variable+x}" = "x" ]; then
    echo "Refusing inherited pipeline override: ${variable}" >&2
    exit 2
  fi
done

for command_name in git sbatch scontrol uv; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is unavailable: ${command_name}" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HIVE_VIDEO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
TRACKED_PILOT_ID="start03_start38_both_sides_top_v1"
SOL_CA_BUNDLE="/etc/pki/tls/certs/ca-bundle.crt"
if [ ! -r "${SOL_CA_BUNDLE}" ]; then
  echo "The tracked Sol CA bundle is missing or unreadable: ${SOL_CA_BUNDLE}" >&2
  exit 5
fi
export SSL_CERT_FILE="${SOL_CA_BUNDLE}"
export SCRATCH_ROOT="/scratch/pdressla/honey-bee"
export DOWNLOAD_DIR="${SCRATCH_ROOT}/downloads"
export RESEQ_ROOT="${SCRATCH_ROOT}/artifacts/resequence_pilots/${TRACKED_PILOT_ID}"
export UV_CACHE_DIR="${SCRATCH_ROOT}/.cache/uv"
export UV_PROJECT_ENVIRONMENT="${SCRATCH_ROOT}/venvs/hive_video_resequence"
export UV_LINK_MODE="copy"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export HF_BUCKET="hf://buckets/collective-logic-lab/honey-bee"
cd "${HIVE_VIDEO_ROOT}"

if [ -n "$(git status --porcelain --untracked-files=all)" ]; then
  echo "The checkout is dirty; commit or remove the unexpected changes before launch." >&2
  git status --short >&2
  exit 2
fi
GIT_REVISION="$(git rev-parse HEAD)"
git fetch --quiet origin main
if ! git show-ref --verify --quiet refs/remotes/origin/main; then
  echo "origin/main is unavailable after fetch; refusing an unverified launch." >&2
  exit 2
fi
if [ "${GIT_REVISION}" != "$(git rev-parse refs/remotes/origin/main)" ]; then
  echo "HEAD is not published at origin/main; push and pull the reviewed revision first." >&2
  exit 2
fi

source "${SCRIPT_DIR}/common.sh"

PILOT_ID="${TRACKED_PILOT_ID}"
LOCATORS="start3_side0_top start3_side1_top start38_side0_top start38_side1_top"
ARRAY_RANGE="0-3"
E2E_PILOT_QUALITY="low"
CUT_REVIEW_STATUS="unreviewed_pilot"
E2E_EXPECTED_GIT_REVISION="${GIT_REVISION}"
export PILOT_ID LOCATORS E2E_PILOT_QUALITY CUT_REVIEW_STATUS
export E2E_EXPECTED_GIT_REVISION
export HF_RESEQ_PREFIX="${HF_BUCKET}/resequenced"
export HF_PILOT_PREFIX="${HF_RESEQ_PREFIX}/pilots/${PILOT_ID}"

# locator|canonical key|archive filename|bytes|archive MD5
EXPECTED_INPUTS=(
  "start3_side0_top|start03_20190608_181426_side0_top|start03__20190608_181426_side0_top.mp4|32135449433|90944e39f3c88989c867d8ecd3037a69"
  "start3_side1_top|start03_20190608_181426_side1_top|start03__20190608_181426_side1_top.mp4|32148250648|38920d37de18b08ddcb8dae196b800dc"
  "start38_side0_top|start38_20190722_200917_side0_top|start38__20190722_200917_side0_top.mp4|29847838843|94c5dfd1b140be69b933db3806cb8272"
  "start38_side1_top|start38_20190722_200917_side1_top|start38__20190722_200917_side1_top.mp4|29857909536|c9909adb163a6942732ad9539e0263be"
)

echo "Preparing the shared environment before submitting arrays."
hv_sync_env
echo "Checking Hugging Face write identity."
uv run --no-sync hf auth whoami --format json

echo "Refreshing the manifest, checking the exact inputs, and probing each media redirect."
REFRESH_MANIFEST=1
for expected_input in "${EXPECTED_INPUTS[@]}"; do
  IFS='|' read -r \
    expected_locator expected_key expected_filename expected_size expected_md5 \
    <<<"${expected_input}"
  RESOLVE_OPTIONS=()
  if [ "${REFRESH_MANIFEST}" -eq 1 ]; then
    RESOLVE_OPTIONS+=(--refresh-manifest)
    REFRESH_MANIFEST=0
  fi
  assignments="$(uv run --no-sync python src/download/download_raw.py \
    --locator "${expected_locator}" \
    --target "${DOWNLOAD_DIR}" \
    --resolve-only --format sh \
    "${RESOLVE_OPTIONS[@]}")"
  eval "${assignments}"
  if [ "${RESEQ_LOCATOR}" != "${expected_locator}" ] || \
      [ "${RESEQ_KEY}" != "${expected_key}" ] || \
      [ "${RESEQ_FILENAME}" != "${expected_filename}" ] || \
      [ "${RESEQ_SIZE}" != "${expected_size}" ] || \
      [ "${RESEQ_MD5}" != "${expected_md5}" ]; then
    echo "Archive manifest entry changed for ${expected_locator}; refusing launch." >&2
    echo "  expected ${expected_key} ${expected_filename} ${expected_size} ${expected_md5}" >&2
    echo "  observed ${RESEQ_KEY} ${RESEQ_FILENAME} ${RESEQ_SIZE} ${RESEQ_MD5}" >&2
    exit 4
  fi
  uv run --no-sync python src/download/download_raw.py \
    --locator "${expected_locator}" \
    --target "${DOWNLOAD_DIR}" \
    --probe-only
done

REMOTE_STATE="$(uv run --no-sync hf buckets list \
  "${HF_PILOT_PREFIX}" --recursive --format json)"
case "${REMOTE_STATE}" in
  ""|"[]") ;;
  *)
    echo "Pilot destination is not empty; refusing to overwrite an existing run:" >&2
    echo "  ${HF_PILOT_PREFIX}" >&2
    exit 4
    ;;
esac

PILOT_ROOT_MARKER="${RESEQ_ROOT}/.unreviewed_pilot_root"
EXPECTED_ROOT_MARKER="v1|pilot_id=${PILOT_ID}"
EXPECTED_ROOT_MARKER="${EXPECTED_ROOT_MARKER}|git_revision=${E2E_EXPECTED_GIT_REVISION}"
EXPECTED_ROOT_MARKER="${EXPECTED_ROOT_MARKER}|hf_prefix=${HF_PILOT_PREFIX}"
if [ -f "${PILOT_ROOT_MARKER}" ]; then
  if [ "$(cat "${PILOT_ROOT_MARKER}")" != "${EXPECTED_ROOT_MARKER}" ]; then
    echo "Existing pilot root marker does not match this tracked plan:" >&2
    echo "  ${PILOT_ROOT_MARKER}" >&2
    exit 4
  fi
else
  printf '%s\n' "${EXPECTED_ROOT_MARKER}" >"${PILOT_ROOT_MARKER}.partial"
  mv "${PILOT_ROOT_MARKER}.partial" "${PILOT_ROOT_MARKER}"
fi

PLAN_DIR="${RESEQ_ROOT}/pilot_run"
PUBLISH_DIR="${RESEQ_ROOT}/pilot_submission_publish"
PUBLISH_LISTING="${RESEQ_ROOT}/pilot_submission.remote_listing.json"
if [ -e "${PLAN_DIR}/submission.tsv" ] || \
    [ -e "${PLAN_DIR}/submission.tsv.partial" ] || \
    [ -e "${PUBLISH_DIR}" ] || \
    [ -e "${PUBLISH_LISTING}" ] || \
    [ -e "${PUBLISH_LISTING}.partial" ]; then
  echo "A submission record already exists for ${PILOT_ID}: ${PLAN_DIR}" >&2
  exit 4
fi
mkdir -p "${PLAN_DIR}" "${PUBLISH_DIR}"
SUBMISSION_PARTIAL="${PLAN_DIR}/submission.tsv.partial"
REMOTE_PLAN="${HF_PILOT_PREFIX}/pilot_run"
REMOTE_PLAN_PREFIX="${HF_PILOT_PREFIX#${HF_BUCKET}/}/pilot_run"

publish_submission_record() {
  local source="$1"
  local remote_name="$2"
  case "${remote_name}" in
    submission.step0[0-4].tsv|submission.tsv) ;;
    *)
      echo "Unexpected pilot submission filename: ${remote_name}" >&2
      exit 4
      ;;
  esac
  cp "${source}" "${PUBLISH_DIR}/${remote_name}.partial"
  mv "${PUBLISH_DIR}/${remote_name}.partial" "${PUBLISH_DIR}/${remote_name}"
  uv run --no-sync hf buckets cp \
    "${PUBLISH_DIR}/${remote_name}" \
    "${REMOTE_PLAN}/${remote_name}"
  uv run --no-sync hf buckets list "${REMOTE_PLAN}" --recursive --format json \
    >"${PUBLISH_LISTING}.partial"
  mv "${PUBLISH_LISTING}.partial" "${PUBLISH_LISTING}"
  uv run --no-sync python src/utils/verify_bucket_listing.py \
    --local-dir "${PUBLISH_DIR}" \
    --listing "${PUBLISH_LISTING}" \
    --remote-prefix "${REMOTE_PLAN_PREFIX}"
}

require_job_id() {
  case "$1" in
    ""|*[!0-9]*)
      echo "Unexpected sbatch job id: $1" >&2
      exit 4
      ;;
  esac
}

{
  printf 'pilot_id\t%s\n' "${PILOT_ID}"
  printf 'git_revision\t%s\n' "${GIT_REVISION}"
  printf 'locators\t%s\n' "${LOCATORS}"
  printf 'input_0\t%s\n' "${EXPECTED_INPUTS[0]}"
  printf 'input_1\t%s\n' "${EXPECTED_INPUTS[1]}"
  printf 'input_2\t%s\n' "${EXPECTED_INPUTS[2]}"
  printf 'input_3\t%s\n' "${EXPECTED_INPUTS[3]}"
  printf 'cut_review_status\t%s\n' "${CUT_REVIEW_STATUS}"
  printf 'compression_quality\t%s\n' "${E2E_PILOT_QUALITY}"
  printf 'ssl_cert_file\t%s\n' "${SSL_CERT_FILE}"
  printf 'release_policy\t%s\n' "download_held_until_submission_record_verified"
  printf 'hf_prefix\t%s\n' "${HF_PILOT_PREFIX}"
  printf 'hf_pilot_prefix\t%s\n' "${HF_PILOT_PREFIX}"
  printf 'hf_reseq_prefix\t%s\n' "${HF_RESEQ_PREFIX}"
  printf 'submitted_at_utc\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${SUBMISSION_PARTIAL}"
publish_submission_record "${SUBMISSION_PARTIAL}" "submission.step00.tsv"

COMMON_EXPORT="ALL,LOCATORS=${LOCATORS},CUT_REVIEW_STATUS=${CUT_REVIEW_STATUS}"
COMMON_EXPORT="${COMMON_EXPORT},E2E_PILOT_ID=${PILOT_ID}"
COMMON_EXPORT="${COMMON_EXPORT},E2E_PILOT_QUALITY=${E2E_PILOT_QUALITY}"
COMMON_EXPORT="${COMMON_EXPORT},E2E_EXPECTED_GIT_REVISION=${E2E_EXPECTED_GIT_REVISION}"
COMMON_EXPORT="${COMMON_EXPORT},HF_RESEQ_PREFIX=${HF_RESEQ_PREFIX}"
COMMON_EXPORT="${COMMON_EXPORT},HF_PILOT_PREFIX=${HF_PILOT_PREFIX}"
COMMON_EXPORT="${COMMON_EXPORT},SSL_CERT_FILE=${SSL_CERT_FILE}"

DOWNLOAD_JOB="$(sbatch --parsable \
  --hold \
  --array="${ARRAY_RANGE}" \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/download_raw_array.sh")"
DOWNLOAD_JOB="${DOWNLOAD_JOB%%;*}"
require_job_id "${DOWNLOAD_JOB}"
printf 'download_job\t%s\n' "${DOWNLOAD_JOB}" >>"${SUBMISSION_PARTIAL}"
publish_submission_record "${SUBMISSION_PARTIAL}" "submission.step01.tsv"

STAGE1_JOB="$(sbatch --parsable \
  --array="${ARRAY_RANGE}" \
  --dependency="aftercorr:${DOWNLOAD_JOB}" \
  --kill-on-invalid-dep=yes \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/resequence_stage1_array.sh")"
STAGE1_JOB="${STAGE1_JOB%%;*}"
require_job_id "${STAGE1_JOB}"
printf 'stage1_job\t%s\n' "${STAGE1_JOB}" >>"${SUBMISSION_PARTIAL}"
publish_submission_record "${SUBMISSION_PARTIAL}" "submission.step02.tsv"

STAGE1A_JOB="$(sbatch --parsable \
  --array="${ARRAY_RANGE}" \
  --dependency="aftercorr:${STAGE1_JOB}" \
  --kill-on-invalid-dep=yes \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/resequence_stage1a_review_array.sh")"
STAGE1A_JOB="${STAGE1A_JOB%%;*}"
require_job_id "${STAGE1A_JOB}"
printf 'stage1a_job\t%s\n' "${STAGE1A_JOB}" >>"${SUBMISSION_PARTIAL}"
publish_submission_record "${SUBMISSION_PARTIAL}" "submission.step03.tsv"

STAGE2_GATE_JOB="$(sbatch --parsable \
  --array="${ARRAY_RANGE}%1" \
  --dependency="aftercorr:${STAGE1A_JOB}" \
  --kill-on-invalid-dep=yes \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/resequence_e2e_stage2_gate_array.sh")"
STAGE2_GATE_JOB="${STAGE2_GATE_JOB%%;*}"
require_job_id "${STAGE2_GATE_JOB}"
printf 'stage2_gate_job\t%s\n' "${STAGE2_GATE_JOB}" >>"${SUBMISSION_PARTIAL}"
publish_submission_record "${SUBMISSION_PARTIAL}" "submission.step04.tsv"

mv "${SUBMISSION_PARTIAL}" "${PLAN_DIR}/submission.tsv"
publish_submission_record "${PLAN_DIR}/submission.tsv" "submission.tsv"
scontrol release "${DOWNLOAD_JOB}"

cat <<EOF

Submitted ${PILOT_ID} at revision ${GIT_REVISION}.

  inputs            Start 03 and Start 38, sides 0 and 1, top panel
  download array    ${DOWNLOAD_JOB} (released after durable submission record)
  Stage 1 array     ${STAGE1_JOB}
  Stage 1a array    ${STAGE1A_JOB}
  Stage 2 gate      ${STAGE2_GATE_JOB} (serialized at one 192 GB task)
  pilot evidence    ${HF_PILOT_PREFIX}
  archival outputs  ${HF_RESEQ_PREFIX}/reseq_<key>
  share derivatives ${HF_RESEQ_PREFIX}/compressed/reseq_<key>/${E2E_PILOT_QUALITY}
  submission record ${PLAN_DIR}/submission.tsv
  durable record    ${REMOTE_PLAN}/submission.tsv

Each corresponding video advances independently. A manual-review decision is
filed and stops cleanly; an automatic pass proceeds to archival render/upload
and a separate low-quality (CRF 28, maximum-compression) derivative.

Monitor with:

  squeue -u pdressla --iterate=120
EOF
