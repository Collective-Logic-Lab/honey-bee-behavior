#!/bin/bash

#SBATCH --job-name=bees-exp6e-486-overlay
#SBATCH --cpus-per-task=8
#SBATCH --mem=80GB
#SBATCH -t 12:00:00
#SBATCH -p htc
#SBATCH -q public
#SBATCH -o slurm.exp6e_486_overlay.%j.out
#SBATCH -e slurm.exp6e_486_overlay.%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-/home/pdressla/workspace/honey-bee-behavior/hive_video}
export RUN_ROOT=${RUN_ROOT:-/scratch/pdressla/bees/exp6e_profile486_overlay}
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

uv run python src/pipeline/exp6e_profile_overlay.py \
  --base-setting-id 486 \
  --vertical-weight "${VERTICAL_WEIGHT:-1.0}" \
  --start-frame 215000 \
  --end-frame 235000 \
  --out "${RUN_ROOT}/exp6e_profile486_vert${VERTICAL_WEIGHT:-1.0}_frames215000_235000.mp4" \
  --chunk-target-frames "${CHUNK_TARGET_FRAMES:-250}" \
  --flow-scale-width "${FLOW_SCALE_WIDTH:-824}" \
  --stride "${STRIDE:-1}"
