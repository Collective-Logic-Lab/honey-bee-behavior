#!/bin/bash

# Resume wrapper for Pipeline 1.
#
# Pipeline 1 writes restartable fit-sample caches, fitted model bundles, chunk
# MP4s, and chunk stats under the same OUT_ROOT used by the original array job.
# Re-submitting this wrapper continues from those files and recomputes only the
# currently incomplete sample or chunk.

#SBATCH --job-name=bees-pipeline1-resume
#SBATCH --array=0-3
#SBATCH --cpus-per-task=8
#SBATCH --mem=100GB
#SBATCH -t 24:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.pipeline1.resume.%A_%a.out
#SBATCH -e slurm.pipeline1.resume.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/pipeline_1_day3_day4_array.sh"
