#!/bin/bash

#SBATCH --job-name=bees-pipeline1
#SBATCH --array=0-3
#SBATCH --cpus-per-task=8
#SBATCH --mem=100GB
#SBATCH -t 24:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.pipeline1.%A_%a.out
#SBATCH -e slurm.pipeline1.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-/home/pdressla/workspace/honey-bee-behavior/hive_video}
export SCRATCH_ROOT=${SCRATCH_ROOT:-/scratch/pdressla/honey-bee}
export UV_CACHE_DIR=${UV_CACHE_DIR:-/scratch/pdressla/.cache/uv}
export UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT:-${SCRATCH_ROOT}/venvs/hive_video_pipeline_1}
export UV_LINK_MODE=${UV_LINK_MODE:-copy}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
export OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-1}
export MKL_NUM_THREADS=${MKL_NUM_THREADS:-1}
export VECLIB_MAXIMUM_THREADS=${VECLIB_MAXIMUM_THREADS:-1}

cd "${HIVE_VIDEO_ROOT}"

# Login shells may already have the repo-level venv active. Pipeline 1 uses a
# scratch venv so array jobs do not concurrently mutate the shared checkout.
unset VIRTUAL_ENV

mkdir -p "${SCRATCH_ROOT}/venvs" "${UV_CACHE_DIR}"

LOCK_DIR="${UV_PROJECT_ENVIRONMENT}.lock"
LOCK_WAIT_SECONDS=${LOCK_WAIT_SECONDS:-1800}
LOCK_START=$(date +%s)
while ! mkdir "${LOCK_DIR}" 2>/dev/null; do
  NOW=$(date +%s)
  if [ $((NOW - LOCK_START)) -gt "${LOCK_WAIT_SECONDS}" ]; then
    echo "Timed out waiting for uv environment lock: ${LOCK_DIR}" >&2
    exit 3
  fi
  echo "Waiting for uv environment lock: ${LOCK_DIR}"
  sleep 10
done
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

echo "Reconciling uv environment at ${UV_PROJECT_ENVIRONMENT}"
uv sync --no-dev

rmdir "${LOCK_DIR}" 2>/dev/null || true
trap - EXIT

resolve_video() {
  local flat_path="$1"
  local nested_path="$2"
  if [ -f "${flat_path}" ]; then
    printf '%s\n' "${flat_path}"
    return 0
  fi
  if [ -f "${nested_path}" ]; then
    printf '%s\n' "${nested_path}"
    return 0
  fi
  echo "Could not find resequenced video. Checked:" >&2
  echo "  ${flat_path}" >&2
  echo "  ${nested_path}" >&2
  return 1
}

case "${SLURM_ARRAY_TASK_ID}" in
  0)
    DAY_KEY="start03"
    MODE="fixed"
    VIDEO="$(resolve_video \
      "${SCRATCH_ROOT}/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4" \
      "${SCRATCH_ROOT}/artifacts/resequenced/reseq_start03_20190608_181426_side0_top/reseq_1_start03__20190608_181426_side0_top.mp4")"
    ;;
  1)
    DAY_KEY="start03"
    MODE="decay"
    VIDEO="$(resolve_video \
      "${SCRATCH_ROOT}/artifacts/resequenced/reseq_1_start03__20190608_181426_side0_top.mp4" \
      "${SCRATCH_ROOT}/artifacts/resequenced/reseq_start03_20190608_181426_side0_top/reseq_1_start03__20190608_181426_side0_top.mp4")"
    ;;
  2)
    DAY_KEY="start04"
    MODE="fixed"
    VIDEO="$(resolve_video \
      "${SCRATCH_ROOT}/artifacts/resequenced/reseq_1_start04__20190609_175013_side0_top.mp4" \
      "${SCRATCH_ROOT}/artifacts/resequenced/reseq_start04_20190609_175013_side0_top/reseq_1_start04__20190609_175013_side0_top.mp4")"
    ;;
  3)
    DAY_KEY="start04"
    MODE="decay"
    VIDEO="$(resolve_video \
      "${SCRATCH_ROOT}/artifacts/resequenced/reseq_1_start04__20190609_175013_side0_top.mp4" \
      "${SCRATCH_ROOT}/artifacts/resequenced/reseq_start04_20190609_175013_side0_top/reseq_1_start04__20190609_175013_side0_top.mp4")"
    ;;
  *)
    echo "Unsupported SLURM_ARRAY_TASK_ID=${SLURM_ARRAY_TASK_ID}" >&2
    exit 2
    ;;
esac

OUT_ROOT="${SCRATCH_ROOT}/artifacts/pipeline_1/${DAY_KEY}_${MODE}"
mkdir -p "${OUT_ROOT}"

COMMAND=(
  uv run --no-sync python src/pipeline/pipeline_1/run.py
  --video "${VIDEO}"
  --out-root "${OUT_ROOT}"
  --run-label "${DAY_KEY}_${MODE}"
  --mode "${MODE}"
  --fit-sample-stride "${FIT_SAMPLE_STRIDE:-250}"
  --chunk-target-frames "${CHUNK_TARGET_FRAMES:-1000}"
  --analysis-stride "${ANALYSIS_STRIDE:-10}"
  --flow-scale-width "${FLOW_SCALE_WIDTH:-824}"
  --top-mask-height "${TOP_MASK_HEIGHT:-72}"
  --decay-half-life-frames "${DECAY_HALF_LIFE_FRAMES:-125}"
  --stats "${STATS:-summary}"
)

if [ "${DIPTYCH:-1}" = "1" ]; then
  COMMAND+=(--diptych)
fi

if [ "${DRY_RUN:-0}" = "1" ]; then
  COMMAND+=(--dry-run)
fi

echo "Running Pipeline 1:"
printf ' %q' "${COMMAND[@]}"
printf '\n'

"${COMMAND[@]}"
