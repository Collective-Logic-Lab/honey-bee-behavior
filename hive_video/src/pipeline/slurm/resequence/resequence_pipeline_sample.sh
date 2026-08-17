#!/bin/bash
# Copy-and-edit sample for a reviewed resequencing batch on Sol.
#
# Do not run this file in place. Copy it to a versioned zero-argument launcher,
# for example submit_start48_start49_top_e2e_v1.sh, then replace the three
# replace_me values below, review the resource plan, commit, and push it.
#
# This sample uses the manual scientific checkpoints:
#   download -> Stage 1 -> [inspect cuts] -> Stage 1a -> [inspect Auto-QC]
#            -> Stage 2 -> archival upload
#                        -> low compression -> compressed upload
#
# Stage 1a and Stage 2 are submitted held. The final message gives the exact
# scontrol commands to release them after their respective reviews.

set -eu

if [ "$#" -ne 0 ]; then
  echo "A resequencing parent launcher takes no arguments; edit tracked literals instead." >&2
  exit 2
fi
if [ -n "${SLURM_JOB_ID:-}" ]; then
  echo "Run the parent launcher on a Sol login node, not inside Slurm." >&2
  exit 2
fi
if [ "$(basename "${BASH_SOURCE[0]}")" = "resequence_pipeline_sample.sh" ]; then
  echo "This sample is fail-closed and cannot submit jobs unchanged." >&2
  echo "Copy it to a versioned submit_BATCH_e2e_v1.sh launcher and edit the plan." >&2
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
  PLAN_ID LOCATORS ARRAY_RANGE FORCE OVERWRITE SKIP_UPLOAD DRY_RUN \
  RETRIES PROGRESS_EVERY_SECONDS \
  TOP_N SAMPLE_WIDTH MAD_Z MIN_DISTANCE THRESHOLD_MODE EXPECTED_INTERVAL_FRAMES \
  FPS MAX_GAP_FRAMES FRAME_COUNT COUNT_FRAMES \
  WINDOW_FRAMES SIGNATURE TOP_K ORDER_SAMPLE_WIDTH \
  AUTO_QC_MAX_ROBUST_Z AUTO_QC_MIN_MARGIN_RATIO AUTO_QC_PROGRESS_EVERY_SECONDS \
  WRITE_ALL_QC_ROLLS JOIN_REVIEW_LIMIT JOIN_REVIEW_SECONDS \
  SCALE_WIDTH SEGMENT_CHUNK_SIZE EDGE_RANK_LIMIT \
  QUALITY COMPRESS_PRESET CUT_REVIEW_STATUS \
  E2E_PILOT_ID E2E_PILOT_QUALITY E2E_EXPECTED_GIT_REVISION \
  SCRATCH_ROOT DOWNLOAD_DIR RESEQ_ROOT HF_BUCKET HF_RESEQ_PREFIX HF_PILOT_PREFIX \
  SSL_CERT_FILE UPLOAD_MANIFEST_HASH_MAX_BYTES \
  UV_CACHE_DIR UV_PROJECT_ENVIRONMENT UV_LINK_MODE \
  OMP_NUM_THREADS OPENBLAS_NUM_THREADS MKL_NUM_THREADS VECLIB_MAXIMUM_THREADS; do
  if [ "${!variable+x}" = "x" ]; then
    echo "Refusing inherited pipeline override: ${variable}" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HIVE_VIDEO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

# Replace these literals in the copied, versioned launcher.
PLAN_ID="replace_me_v1"
LOCATORS="replace_me"
ARRAY_RANGE="replace_me"

# Reviewed sharing choice and ordinary canonical output locations.
QUALITY="low"
CUT_REVIEW_STATUS="inspected"
export SCRATCH_ROOT="/scratch/pdressla/honey-bee"
export DOWNLOAD_DIR="${SCRATCH_ROOT}/downloads"
export RESEQ_ROOT="${SCRATCH_ROOT}/artifacts/resequence"
export UV_CACHE_DIR="${SCRATCH_ROOT}/.cache/uv"
export UV_PROJECT_ENVIRONMENT="${SCRATCH_ROOT}/venvs/hive_video_resequence"
export UV_LINK_MODE="copy"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export HF_BUCKET="hf://buckets/collective-logic-lab/honey-bee"
export HF_RESEQ_PREFIX="${HF_BUCKET}/resequenced"
export SSL_CERT_FILE="/etc/pki/tls/certs/ca-bundle.crt"

# `--mem` is total memory for each Slurm allocation, not memory per CPU.
DOWNLOAD_CPUS=1
DOWNLOAD_MEM="4GB"
DOWNLOAD_TIME="08:00:00"
STAGE1_CPUS=8
STAGE1_MEM="32GB"
STAGE1_TIME="24:00:00"
STAGE1A_CPUS=8
STAGE1A_MEM="32GB"
STAGE1A_TIME="12:00:00"
STAGE2_CPUS=8
STAGE2_MEM="192GB"
STAGE2_TIME="48:00:00"
COMPRESSION_CPUS=8
COMPRESSION_MEM="8GB"
COMPRESSION_TIME="12:00:00"

# These child allocations are owned by the worker scripts that submit them.
# Keep them visible here because transfer memory is part of the pipeline plan.
ARCHIVAL_UPLOAD_CPUS=1
ARCHIVAL_UPLOAD_MEM="16GB"
ARCHIVAL_UPLOAD_TIME="06:00:00"
COMPRESSED_UPLOAD_CPUS=1
COMPRESSED_UPLOAD_MEM="4GB"
COMPRESSED_UPLOAD_TIME="06:00:00"

case "${PLAN_ID}:${LOCATORS}:${ARRAY_RANGE}" in
  *replace_me*)
    echo "Replace PLAN_ID, LOCATORS, and ARRAY_RANGE before submission." >&2
    exit 2
    ;;
esac
case "${QUALITY}" in
  high|medium|low) ;;
  *)
    echo "QUALITY must be high, medium, or low; got ${QUALITY}" >&2
    exit 2
    ;;
esac

read -r -a LOCATOR_ITEMS <<<"${LOCATORS}"
if [ "${#LOCATOR_ITEMS[@]}" -eq 0 ]; then
  echo "LOCATORS must contain at least one archive locator." >&2
  exit 2
fi
EXPECTED_RANGE="0-$((${#LOCATOR_ITEMS[@]} - 1))"
if [ "${ARRAY_RANGE}" != "${EXPECTED_RANGE}" ]; then
  echo "ARRAY_RANGE does not match LOCATORS." >&2
  echo "  expected ${EXPECTED_RANGE}" >&2
  echo "  observed ${ARRAY_RANGE}" >&2
  exit 2
fi
if [ ! -r "${SSL_CERT_FILE}" ]; then
  echo "Sol CA bundle is missing or unreadable: ${SSL_CERT_FILE}" >&2
  exit 5
fi

for command_name in git grep sbatch scontrol; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is unavailable: ${command_name}" >&2
    exit 2
  fi
done

require_worker_resource() {
  local worker="$1"
  local directive="$2"
  if ! grep -Fqx "#SBATCH ${directive}" "${worker}"; then
    echo "Worker resource contract changed: ${worker}" >&2
    echo "  expected #SBATCH ${directive}" >&2
    exit 4
  fi
}

require_worker_resource "${SCRIPT_DIR}/resequence_upload.sh" \
  "--cpus-per-task=${ARCHIVAL_UPLOAD_CPUS}"
require_worker_resource "${SCRIPT_DIR}/resequence_upload.sh" \
  "--mem=${ARCHIVAL_UPLOAD_MEM}"
require_worker_resource "${SCRIPT_DIR}/resequence_upload.sh" \
  "-t ${ARCHIVAL_UPLOAD_TIME}"
require_worker_resource "${SCRIPT_DIR}/compress_resequenced_upload.sh" \
  "--cpus-per-task=${COMPRESSED_UPLOAD_CPUS}"
require_worker_resource "${SCRIPT_DIR}/compress_resequenced_upload.sh" \
  "--mem=${COMPRESSED_UPLOAD_MEM}"
require_worker_resource "${SCRIPT_DIR}/compress_resequenced_upload.sh" \
  "-t ${COMPRESSED_UPLOAD_TIME}"

cd "${HIVE_VIDEO_ROOT}"
if [ -n "$(git status --porcelain --untracked-files=all)" ]; then
  echo "The checkout is dirty; commit or remove unexpected changes before launch." >&2
  git status --short >&2
  exit 2
fi
GIT_REVISION="$(git rev-parse HEAD)"
git fetch --quiet origin main
if [ "${GIT_REVISION}" != "$(git rev-parse refs/remotes/origin/main)" ]; then
  echo "HEAD is not published at origin/main; push the reviewed launcher first." >&2
  exit 2
fi

PLAN_DIR="${SCRATCH_ROOT}/artifacts/resequence_plans/${PLAN_ID}"
if [ -e "${PLAN_DIR}" ]; then
  echo "Plan directory already exists; use a new versioned PLAN_ID: ${PLAN_DIR}" >&2
  exit 4
fi
mkdir -p "$(dirname "${PLAN_DIR}")"
mkdir "${PLAN_DIR}"
SUBMISSION_PARTIAL="${PLAN_DIR}/submission.tsv.partial"

COMMON_EXPORT="ALL,LOCATORS=${LOCATORS},CUT_REVIEW_STATUS=${CUT_REVIEW_STATUS}"
COMMON_EXPORT="${COMMON_EXPORT},QUALITY=${QUALITY},SCRATCH_ROOT=${SCRATCH_ROOT}"
COMMON_EXPORT="${COMMON_EXPORT},DOWNLOAD_DIR=${DOWNLOAD_DIR},RESEQ_ROOT=${RESEQ_ROOT}"
COMMON_EXPORT="${COMMON_EXPORT},HF_BUCKET=${HF_BUCKET},HF_RESEQ_PREFIX=${HF_RESEQ_PREFIX}"
COMMON_EXPORT="${COMMON_EXPORT},SSL_CERT_FILE=${SSL_CERT_FILE}"

require_job_id() {
  case "$1" in
    ""|*[!0-9]*)
      echo "Unexpected Slurm job id: $1" >&2
      exit 4
      ;;
  esac
}

{
  printf 'plan_id\t%s\n' "${PLAN_ID}"
  printf 'git_revision\t%s\n' "${GIT_REVISION}"
  printf 'locators\t%s\n' "${LOCATORS}"
  printf 'array_range\t%s\n' "${ARRAY_RANGE}"
  printf 'cut_review_status\t%s\n' "${CUT_REVIEW_STATUS}"
  printf 'compression_quality\t%s\n' "${QUALITY}"
  printf 'download_resources\tcpus=%s,mem=%s,time=%s\n' \
    "${DOWNLOAD_CPUS}" "${DOWNLOAD_MEM}" "${DOWNLOAD_TIME}"
  printf 'stage1_resources\tcpus=%s,mem=%s,time=%s\n' \
    "${STAGE1_CPUS}" "${STAGE1_MEM}" "${STAGE1_TIME}"
  printf 'stage1a_resources\tcpus=%s,mem=%s,time=%s\n' \
    "${STAGE1A_CPUS}" "${STAGE1A_MEM}" "${STAGE1A_TIME}"
  printf 'stage2_resources\tcpus=%s,mem=%s,time=%s,concurrency=1\n' \
    "${STAGE2_CPUS}" "${STAGE2_MEM}" "${STAGE2_TIME}"
  printf 'archival_upload_resources\tcpus=%s,mem=%s,time=%s\n' \
    "${ARCHIVAL_UPLOAD_CPUS}" "${ARCHIVAL_UPLOAD_MEM}" "${ARCHIVAL_UPLOAD_TIME}"
  printf 'compression_resources\tcpus=%s,mem=%s,time=%s,concurrency=2\n' \
    "${COMPRESSION_CPUS}" "${COMPRESSION_MEM}" "${COMPRESSION_TIME}"
  printf 'compressed_upload_resources\tcpus=%s,mem=%s,time=%s\n' \
    "${COMPRESSED_UPLOAD_CPUS}" "${COMPRESSED_UPLOAD_MEM}" "${COMPRESSED_UPLOAD_TIME}"
  printf 'hf_reseq_prefix\t%s\n' "${HF_RESEQ_PREFIX}"
  printf 'submitted_at_utc\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${SUBMISSION_PARTIAL}"

DOWNLOAD_JOB="$(sbatch --parsable \
  --hold \
  --array="${ARRAY_RANGE}" \
  --cpus-per-task="${DOWNLOAD_CPUS}" \
  --mem="${DOWNLOAD_MEM}" \
  --time="${DOWNLOAD_TIME}" \
  --partition=public --qos=public \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/download_raw_array.sh")"
DOWNLOAD_JOB="${DOWNLOAD_JOB%%;*}"
require_job_id "${DOWNLOAD_JOB}"
printf 'download_job\t%s\n' "${DOWNLOAD_JOB}" >>"${SUBMISSION_PARTIAL}"

STAGE1_JOB="$(sbatch --parsable \
  --array="${ARRAY_RANGE}" \
  --dependency="aftercorr:${DOWNLOAD_JOB}" \
  --kill-on-invalid-dep=yes \
  --cpus-per-task="${STAGE1_CPUS}" \
  --mem="${STAGE1_MEM}" \
  --time="${STAGE1_TIME}" \
  --partition=public --qos=public \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/resequence_stage1_array.sh")"
STAGE1_JOB="${STAGE1_JOB%%;*}"
require_job_id "${STAGE1_JOB}"
printf 'stage1_job\t%s\n' "${STAGE1_JOB}" >>"${SUBMISSION_PARTIAL}"

STAGE1A_JOB="$(sbatch --parsable \
  --hold \
  --array="${ARRAY_RANGE}" \
  --dependency="aftercorr:${STAGE1_JOB}" \
  --kill-on-invalid-dep=yes \
  --cpus-per-task="${STAGE1A_CPUS}" \
  --mem="${STAGE1A_MEM}" \
  --time="${STAGE1A_TIME}" \
  --partition=public --qos=public \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/resequence_stage1a_review_array.sh")"
STAGE1A_JOB="${STAGE1A_JOB%%;*}"
require_job_id "${STAGE1A_JOB}"
printf 'stage1a_job\t%s\n' "${STAGE1A_JOB}" >>"${SUBMISSION_PARTIAL}"

STAGE2_JOB="$(sbatch --parsable \
  --hold \
  --array="${ARRAY_RANGE}%1" \
  --dependency="aftercorr:${STAGE1A_JOB}" \
  --kill-on-invalid-dep=yes \
  --cpus-per-task="${STAGE2_CPUS}" \
  --mem="${STAGE2_MEM}" \
  --time="${STAGE2_TIME}" \
  --partition=public --qos=public \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/resequence_stage2_array.sh")"
STAGE2_JOB="${STAGE2_JOB%%;*}"
require_job_id "${STAGE2_JOB}"
printf 'stage2_job\t%s\n' "${STAGE2_JOB}" >>"${SUBMISSION_PARTIAL}"

COMPRESSION_JOB="$(sbatch --parsable \
  --array="${ARRAY_RANGE}%2" \
  --dependency="aftercorr:${STAGE2_JOB}" \
  --kill-on-invalid-dep=yes \
  --cpus-per-task="${COMPRESSION_CPUS}" \
  --mem="${COMPRESSION_MEM}" \
  --time="${COMPRESSION_TIME}" \
  --partition=public --qos=public \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/compress_resequenced_array.sh")"
COMPRESSION_JOB="${COMPRESSION_JOB%%;*}"
require_job_id "${COMPRESSION_JOB}"
printf 'compression_job\t%s\n' "${COMPRESSION_JOB}" >>"${SUBMISSION_PARTIAL}"

mv "${SUBMISSION_PARTIAL}" "${PLAN_DIR}/submission.tsv"
scontrol release "${DOWNLOAD_JOB}"

cat <<EOF

Submitted ${PLAN_ID} at revision ${GIT_REVISION}.

  download array     ${DOWNLOAD_JOB} (released)
  Stage 1 array      ${STAGE1_JOB}
  Stage 1a array     ${STAGE1A_JOB} (held for source-cut review)
  Stage 2 array      ${STAGE2_JOB} (held for Auto-QC/manual approval)
  compression array  ${COMPRESSION_JOB} (waits for Stage 2)
  submission record  ${PLAN_DIR}/submission.tsv

After Stage 1 succeeds, inspect each cut_review.proposed.csv, create a
cut_review.verified.csv only where edits are needed, then release Stage 1a:

  scontrol release ${STAGE1A_JOB}

After Stage 1a succeeds, inspect auto_qc.summary.json and any flagged QC roll.
Record a report-bound approval where required, then release Stage 2:

  scontrol release ${STAGE2_JOB}

Stage 2 queues the 16 GB archival-upload child. Successful Stage 2 tasks release
the low-compression array, whose upload child uses 4 GB.
EOF
