#!/bin/bash

#SBATCH --job-name=bees-pipeline1
#SBATCH --array=0-3
#SBATCH --cpus-per-task=8
#SBATCH --mem=100GB
#SBATCH -t 24:00:00
#SBATCH -p htc
#SBATCH -q public
#SBATCH -o slurm.pipeline1.%A_%a.out
#SBATCH -e slurm.pipeline1.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-/home/pdressla/workspace/honey-bee-behavior/hive_video}
export SCRATCH_ROOT=${SCRATCH_ROOT:-/scratch/pdressla/honey-bee}
export UV_CACHE_DIR=${UV_CACHE_DIR:-/scratch/pdressla/.cache/uv}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
export OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-1}
export MKL_NUM_THREADS=${MKL_NUM_THREADS:-1}
export VECLIB_MAXIMUM_THREADS=${VECLIB_MAXIMUM_THREADS:-1}

cd "${HIVE_VIDEO_ROOT}"
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

case "${SLURM_ARRAY_TASK_ID}" in
  0)
    DAY_KEY="start03"
    MODE="fixed"
    VIDEO="${SCRATCH_ROOT}/artifacts/resequenced/reseq_start03_20190608_181426_side0_top/reseq_1_start03__20190608_181426_side0_top.mp4"
    ;;
  1)
    DAY_KEY="start03"
    MODE="decay"
    VIDEO="${SCRATCH_ROOT}/artifacts/resequenced/reseq_start03_20190608_181426_side0_top/reseq_1_start03__20190608_181426_side0_top.mp4"
    ;;
  2)
    DAY_KEY="start04"
    MODE="fixed"
    VIDEO="${SCRATCH_ROOT}/artifacts/resequenced/reseq_start04_20190609_175013_side0_top/reseq_1_start04__20190609_175013_side0_top.mp4"
    ;;
  3)
    DAY_KEY="start04"
    MODE="decay"
    VIDEO="${SCRATCH_ROOT}/artifacts/resequenced/reseq_start04_20190609_175013_side0_top/reseq_1_start04__20190609_175013_side0_top.mp4"
    ;;
  *)
    echo "Unsupported SLURM_ARRAY_TASK_ID=${SLURM_ARRAY_TASK_ID}" >&2
    exit 2
    ;;
esac

OUT_ROOT="${SCRATCH_ROOT}/artifacts/pipeline_1/${DAY_KEY}_${MODE}"
mkdir -p "${OUT_ROOT}"

COMMAND=(
  uv run python src/pipeline/pipeline_1/run.py
  --video "${VIDEO}"
  --out-root "${OUT_ROOT}"
  --run-label "${DAY_KEY}_${MODE}"
  --mode "${MODE}"
  --fit-sample-stride "${FIT_SAMPLE_STRIDE:-250}"
  --chunk-target-frames "${CHUNK_TARGET_FRAMES:-250}"
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
