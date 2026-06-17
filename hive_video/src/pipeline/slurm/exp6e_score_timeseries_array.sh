#!/bin/bash

#SBATCH --job-name=bees-exp6e-score
#SBATCH --array=0-167
#SBATCH --cpus-per-task=8
#SBATCH --mem=48GB
#SBATCH -t 12:00:00
#SBATCH -p htc
#SBATCH -q public
#SBATCH -o slurm.exp6e_score.%A_%a.out
#SBATCH -e slurm.exp6e_score.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-/home/pdressla/workspace/honey-bee-behavior/hive_video}
export RUN_ROOT=${RUN_ROOT:-/scratch/pdressla/bees/exp6e_score_timeseries}
export UV_CACHE_DIR=${UV_CACHE_DIR:-/scratch/pdressla/.cache/uv}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
export OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-1}
export MKL_NUM_THREADS=${MKL_NUM_THREADS:-1}
export VECLIB_MAXIMUM_THREADS=${VECLIB_MAXIMUM_THREADS:-1}

cd "${HIVE_VIDEO_ROOT}"
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

mkdir -p "${RUN_ROOT}"

PROFILE_INDEX=${SLURM_ARRAY_TASK_ID}
OUT="${RUN_ROOT}/exp6e_profile_${PROFILE_INDEX}_timeseries.csv"

uv run python src/pipeline/exp6e_score_profile_timeseries.py \
  --profile-index "${PROFILE_INDEX}" \
  --out "${OUT}" \
  --chunk-target-frames "${CHUNK_TARGET_FRAMES:-1000}" \
  --flow-scale-width "${FLOW_SCALE_WIDTH:-824}" \
  --stride "${STRIDE:-1}"
