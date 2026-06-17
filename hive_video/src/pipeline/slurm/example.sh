#!/bin/bash

#SBATCH --job-name=bees-expname
#SBATCH --cpus-per-task=8.   # number of "cores"
#SBATCH --mem=40GB        # for example
#SBATCH -t 4:00:00     # time in d-hh:mm:ss .... Note that greater than 4 hours and the partion must be public not htc
#SBATCH -p htc
#SBATCH -q public
#SBATCH -o slurm.%j.out
#SBATCH -e slurm.%j.err
#SBATCH --mail-type=ALL
#SBATCH --mail-user="pdressla@asu.edu"
#SBATCH --export=NONE

set -eu

export REPO_ROOT=${REPO_ROOT:-/home/pdressla/workspace/honey_bee_behavior}
export BATTERY_DIR=${BATTERY_DIR:-${REPO_ROOT}/battery/data/battery_6_all}
export RUN_ROOT=${RUN_ROOT:-/scratch/pdressla/bees}

export UV_CACHE_DIR=/scratch/pdressla/.cache/uv

cd "${REPO_ROOT}"
source "${REPO_ROOT}/script/_load_env.sh"
load_repo_env "${REPO_ROOT}"
source .venv/bin/activate

ARTIFACT_DIR="${RUN_ROOT}/artifacts"
OUTDIR="${OUT_ROOT}/${MODEL_KEY}_permuted_target_$(date +%Y%m%d_%H%M%S)"

# The following is an example command

uv run -m src.pipeline.example --outdir "${OUTDIR}" --artifact-dir "${ARTIFACT_DIR}"
