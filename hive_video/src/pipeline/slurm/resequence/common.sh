#!/bin/bash
# Shared setup for the hive_video resequencing slurm jobs.
#
# Source this from a job script; it is not meant to be run on its own:
#
#   export HIVE_VIDEO_ROOT="${SLURM_SUBMIT_DIR:-${PWD}}"
#   source "${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence/common.sh"
#   hv_sync_env
#   hv_resolve start47_side1_top
#
# After hv_resolve, these are set:
#   RESEQ_KEY       start47_20190731_184423_side1_top
#   RESEQ_FILENAME  start47__20190731_184423_side1_top.mp4
#   RESEQ_PATH      absolute path to the raw download
#   RESEQ_DIRNAME   reseq_start47_20190731_184423_side1_top
#   HV_WORK_DIR     ${RESEQ_ROOT}/${RESEQ_DIRNAME}
#   HV_QC_DIR / HV_SEG_DIR / HV_ORDER_DIR / HV_REVIEW_DIR / HV_OUT_DIR

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-/home/pdressla/workspace/honey-bee-behavior/hive_video}
export SCRATCH_ROOT=${SCRATCH_ROOT:-/scratch/pdressla/honey-bee}
export DOWNLOAD_DIR=${DOWNLOAD_DIR:-${SCRATCH_ROOT}/downloads}
export RESEQ_ROOT=${RESEQ_ROOT:-${SCRATCH_ROOT}/artifacts/resequence}

export UV_CACHE_DIR=${UV_CACHE_DIR:-${SCRATCH_ROOT}/.cache/uv}
export UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT:-${SCRATCH_ROOT}/venvs/hive_video_resequence}
export UV_LINK_MODE=${UV_LINK_MODE:-copy}

# The resequencing tools are single-threaded per task; keep BLAS from oversubscribing.
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
export OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-1}
export MKL_NUM_THREADS=${MKL_NUM_THREADS:-1}
export VECLIB_MAXIMUM_THREADS=${VECLIB_MAXIMUM_THREADS:-1}

export HF_BUCKET=${HF_BUCKET:-hf://buckets/collective-logic-lab/honey-bee}
export HF_RESEQ_PREFIX=${HF_RESEQ_PREFIX:-${HF_BUCKET}/resequenced}

cd "${HIVE_VIDEO_ROOT}"

# Login shells may already have the repo-level venv active. These jobs use a
# scratch venv so array tasks do not concurrently mutate the shared checkout.
unset VIRTUAL_ENV

# Reconcile the scratch uv environment under a directory lock so concurrent
# array tasks do not race each other into a half-written venv.
hv_sync_env() {
  mkdir -p "${SCRATCH_ROOT}/venvs" "${UV_CACHE_DIR}" "${DOWNLOAD_DIR}" "${RESEQ_ROOT}"

  local lock_dir="${UV_PROJECT_ENVIRONMENT}.lock"
  local wait_seconds=${LOCK_WAIT_SECONDS:-1800}
  local start
  start=$(date +%s)

  while ! mkdir "${lock_dir}" 2>/dev/null; do
    local now
    now=$(date +%s)
    if [ $((now - start)) -gt "${wait_seconds}" ]; then
      echo "Timed out waiting for uv environment lock: ${lock_dir}" >&2
      exit 3
    fi
    echo "Waiting for uv environment lock: ${lock_dir}"
    sleep 10
  done
  trap 'rmdir "'"${lock_dir}"'" 2>/dev/null || true' EXIT

  echo "Reconciling uv environment at ${UV_PROJECT_ENVIRONMENT}"
  uv sync --frozen --no-dev

  rmdir "${lock_dir}" 2>/dev/null || true
  trap - EXIT
}

# FFmpeg is a Sol module rather than a Python dependency. Load the confirmed
# cluster build when a compute-node environment does not already provide it.
# This keeps rendering jobs independent of the login shell that submitted them.
hv_require_ffmpeg() {
  if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
    return 0
  fi
  if ! type module >/dev/null 2>&1 && [ -r /etc/profile.d/modules.sh ]; then
    # shellcheck source=/etc/profile.d/modules.sh
    source /etc/profile.d/modules.sh
  fi
  if type module >/dev/null 2>&1; then
    echo "Loading ffmpeg-6.0-gcc-12.1.0 module"
    module load ffmpeg-6.0-gcc-12.1.0
  fi
  if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    echo "ffmpeg and ffprobe are required but unavailable after loading ffmpeg-6.0-gcc-12.1.0." >&2
    exit 5
  fi
}

# Resolve a locator such as start47_side1_top into every path the pipeline needs.
hv_resolve() {
  local locator="$1"
  local assignments
  if ! assignments="$(uv run --no-sync python src/download/download_raw.py \
      --locator "${locator}" \
      --target "${DOWNLOAD_DIR}" \
      --resolve-only --format sh)"; then
    echo "Could not resolve locator: ${locator}" >&2
    exit 2
  fi
  eval "${assignments}"

  export HV_WORK_DIR="${RESEQ_ROOT}/${RESEQ_DIRNAME}"
  export HV_QC_DIR="${HV_WORK_DIR}/qc"
  export HV_SEG_DIR="${HV_WORK_DIR}/segments"
  export HV_ORDER_DIR="${HV_WORK_DIR}/order"
  export HV_REVIEW_DIR="${HV_WORK_DIR}/review"
  export HV_OUT_DIR="${HV_WORK_DIR}/output"

  echo "locator   ${locator}"
  echo "key       ${RESEQ_KEY}"
  echo "raw video ${RESEQ_PATH}"
  echo "work dir  ${HV_WORK_DIR}"
}

# Pick the array element for this task out of a space-separated list.
hv_locator_for_task() {
  local -a locators=($1)
  local index=${2:-0}
  if [ "${index}" -ge "${#locators[@]}" ]; then
    echo "SLURM_ARRAY_TASK_ID=${index} exceeds the ${#locators[@]} configured locators." >&2
    exit 2
  fi
  printf '%s\n' "${locators[${index}]}"
}

hv_require_file() {
  if [ ! -f "$1" ]; then
    echo "Required input is missing: $1" >&2
    echo "$2" >&2
    exit 4
  fi
}

# Return success when a step must run. A marker is reusable only when its
# recorded input signature matches the current one.
hv_step_needed() {
  local marker="$1"
  local signature="$2"
  shift 2
  if [ "${FORCE:-0}" = "1" ]; then
    return 0
  fi
  local output
  for output in "$@"; do
    if [ ! -s "${output}" ]; then
      echo "--- output missing or empty; rerunning step: ${output}"
      return 0
    fi
  done
  if [ -f "${marker}" ] && [ "$(cat "${marker}")" = "${signature}" ]; then
    echo "--- skipping completed step: ${marker}"
    return 1
  fi
  if [ -f "${marker}" ]; then
    echo "--- inputs changed; rerunning step: ${marker}"
  fi
  return 0
}

hv_mark_complete() {
  local marker="$1"
  local signature="$2"
  local partial="${marker}.partial"
  printf '%s\n' "${signature}" >"${partial}"
  mv "${partial}" "${marker}"
}

hv_file_fingerprint() {
  cksum "$1" | awk '{ print $1 ":" $2 }'
}

# Print a wall-clock duration for a named step so the smoke test can report timings.
hv_time_step() {
  local label="$1"
  shift
  local started
  started=$(date +%s)
  echo "--- ${label}: starting"
  "$@"
  local elapsed=$(($(date +%s) - started))
  echo "--- ${label}: done in ${elapsed}s"
  printf '%s\t%s\n' "${label}" "${elapsed}" >>"${HV_TIMING_LOG:-/dev/null}"
}
