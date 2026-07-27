#!/bin/bash
# Submit the bounded unattended Start 01 / Start 02 side-0-top pipeline pilot.
#
# Run with no arguments from any directory:
#
#   bash src/pipeline/slurm/resequence/submit_start01_start02_side0_top_e2e.sh
#
# The tracked plan is intentionally fixed. It downloads both videos, runs
# Stage 1 and Stage 1a with corresponding-task dependencies, files every
# Stage 1a outcome, renders only auto-cleared videos, and creates the selected
# maximum-compression sharing derivative. Pilot outputs stay under a dedicated
# Hugging Face prefix rather than replacing validated inventory.

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
  SCRATCH_ROOT DOWNLOAD_DIR RESEQ_ROOT HF_BUCKET HF_RESEQ_PREFIX \
  UPLOAD_MANIFEST_HASH_MAX_BYTES; do
  if [ "${!variable+x}" = "x" ]; then
    echo "Refusing inherited pipeline override: ${variable}" >&2
    exit 2
  fi
done

for command_name in git sbatch uv; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is unavailable: ${command_name}" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HIVE_VIDEO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
TRACKED_PILOT_ID="start01_start02_side0_top_v1"
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
LOCATORS="start1_side0_top start2_side0_top"
ARRAY_RANGE="0-1"
E2E_PILOT_QUALITY="low"
CUT_REVIEW_STATUS="unreviewed_pilot"
E2E_EXPECTED_GIT_REVISION="${GIT_REVISION}"
export PILOT_ID LOCATORS E2E_PILOT_QUALITY CUT_REVIEW_STATUS
export E2E_EXPECTED_GIT_REVISION
export HF_RESEQ_PREFIX="${HF_BUCKET}/resequenced/pilots/${PILOT_ID}"

echo "Preparing the shared environment before submitting arrays."
hv_sync_env
echo "Checking Hugging Face write identity."
uv run --no-sync hf auth whoami --format json

echo "Resolving the fixed pilot inputs without downloading media."
for locator in ${LOCATORS}; do
  uv run --no-sync python src/download/download_raw.py \
    --locator "${locator}" \
    --target "${DOWNLOAD_DIR}" \
    --resolve-only
done

REMOTE_STATE="$(uv run --no-sync hf buckets list \
  "${HF_RESEQ_PREFIX}" --recursive --format json)"
case "${REMOTE_STATE}" in
  ""|"[]") ;;
  *)
    echo "Pilot destination is not empty; refusing to overwrite an existing run:" >&2
    echo "  ${HF_RESEQ_PREFIX}" >&2
    exit 4
    ;;
esac

PILOT_ROOT_MARKER="${RESEQ_ROOT}/.unreviewed_pilot_root"
EXPECTED_ROOT_MARKER="v1|pilot_id=${PILOT_ID}"
EXPECTED_ROOT_MARKER="${EXPECTED_ROOT_MARKER}|git_revision=${E2E_EXPECTED_GIT_REVISION}"
EXPECTED_ROOT_MARKER="${EXPECTED_ROOT_MARKER}|hf_prefix=${HF_RESEQ_PREFIX}"
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
if [ -e "${PLAN_DIR}/submission.tsv" ] || [ -e "${PLAN_DIR}/submission.tsv.partial" ]; then
  echo "A submission record already exists for ${PILOT_ID}: ${PLAN_DIR}" >&2
  exit 4
fi
mkdir -p "${PLAN_DIR}"
SUBMISSION_PARTIAL="${PLAN_DIR}/submission.tsv.partial"
{
  printf 'pilot_id\t%s\n' "${PILOT_ID}"
  printf 'git_revision\t%s\n' "${GIT_REVISION}"
  printf 'locators\t%s\n' "${LOCATORS}"
  printf 'cut_review_status\t%s\n' "${CUT_REVIEW_STATUS}"
  printf 'compression_quality\t%s\n' "${E2E_PILOT_QUALITY}"
  printf 'hf_prefix\t%s\n' "${HF_RESEQ_PREFIX}"
  printf 'submitted_at_utc\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${SUBMISSION_PARTIAL}"

COMMON_EXPORT="ALL,LOCATORS=${LOCATORS},CUT_REVIEW_STATUS=${CUT_REVIEW_STATUS}"
COMMON_EXPORT="${COMMON_EXPORT},E2E_PILOT_ID=${PILOT_ID}"
COMMON_EXPORT="${COMMON_EXPORT},E2E_PILOT_QUALITY=${E2E_PILOT_QUALITY}"
COMMON_EXPORT="${COMMON_EXPORT},E2E_EXPECTED_GIT_REVISION=${E2E_EXPECTED_GIT_REVISION}"
COMMON_EXPORT="${COMMON_EXPORT},HF_RESEQ_PREFIX=${HF_RESEQ_PREFIX}"

DOWNLOAD_JOB="$(sbatch --parsable \
  --array="${ARRAY_RANGE}" \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/download_raw_array.sh")"
DOWNLOAD_JOB="${DOWNLOAD_JOB%%;*}"
printf 'download_job\t%s\n' "${DOWNLOAD_JOB}" >>"${SUBMISSION_PARTIAL}"

STAGE1_JOB="$(sbatch --parsable \
  --array="${ARRAY_RANGE}" \
  --dependency="aftercorr:${DOWNLOAD_JOB}" \
  --kill-on-invalid-dep=yes \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/resequence_stage1_array.sh")"
STAGE1_JOB="${STAGE1_JOB%%;*}"
printf 'stage1_job\t%s\n' "${STAGE1_JOB}" >>"${SUBMISSION_PARTIAL}"

STAGE1A_JOB="$(sbatch --parsable \
  --array="${ARRAY_RANGE}" \
  --dependency="aftercorr:${STAGE1_JOB}" \
  --kill-on-invalid-dep=yes \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/resequence_stage1a_review_array.sh")"
STAGE1A_JOB="${STAGE1A_JOB%%;*}"
printf 'stage1a_job\t%s\n' "${STAGE1A_JOB}" >>"${SUBMISSION_PARTIAL}"

STAGE2_GATE_JOB="$(sbatch --parsable \
  --array="${ARRAY_RANGE}%1" \
  --dependency="aftercorr:${STAGE1A_JOB}" \
  --kill-on-invalid-dep=yes \
  --export="${COMMON_EXPORT}" \
  "${SCRIPT_DIR}/resequence_e2e_stage2_gate_array.sh")"
STAGE2_GATE_JOB="${STAGE2_GATE_JOB%%;*}"
printf 'stage2_gate_job\t%s\n' "${STAGE2_GATE_JOB}" >>"${SUBMISSION_PARTIAL}"

for job_id in \
  "${DOWNLOAD_JOB}" \
  "${STAGE1_JOB}" \
  "${STAGE1A_JOB}" \
  "${STAGE2_GATE_JOB}"; do
  case "${job_id}" in
    ""|*[!0-9]*)
      echo "Unexpected sbatch job id: ${job_id}" >&2
      exit 4
      ;;
  esac
done

mv "${SUBMISSION_PARTIAL}" "${PLAN_DIR}/submission.tsv"

cat <<EOF

Submitted ${PILOT_ID} at revision ${GIT_REVISION}.

  download array    ${DOWNLOAD_JOB}
  Stage 1 array     ${STAGE1_JOB}
  Stage 1a array    ${STAGE1A_JOB}
  Stage 2 gate      ${STAGE2_GATE_JOB} (serialized at one 192 GB task)
  pilot artifacts   ${HF_RESEQ_PREFIX}
  submission record ${PLAN_DIR}/submission.tsv

Each corresponding video advances independently. A manual-review decision is
filed and stops cleanly; an automatic pass proceeds to archival render/upload
and a separate low-quality (CRF 28, maximum-compression) derivative.

Monitor with:

  squeue -u pdressla --iterate=120
EOF
