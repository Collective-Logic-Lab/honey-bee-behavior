#!/bin/bash
# Download raw hive videos from the Edmond archive, one file per array task.
#
#   sbatch src/pipeline/slurm/resequence/download_raw_array.sh
#
# The default locator list covers the three files for the Day 4 / Day 47 top
# comparison. Override it, and the array bound, to fetch anything else:
#
#   sbatch --array=0-1 --export=ALL,LOCATORS="day3_side0_top day3_side1_top" \
#       src/pipeline/slurm/resequence/download_raw_array.sh
#
# Downloads are resumable and checksum-verified, so re-running a failed task is
# safe and cheap: a completed file is skipped after its MD5 is confirmed.

#SBATCH --job-name=bees-download
#SBATCH --array=0-2
#SBATCH --cpus-per-task=1
#SBATCH --mem=4GB
#SBATCH -t 08:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.download.%A_%a.out
#SBATCH -e slurm.download.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

# Slurm executes a copy of this script from /var/spool/slurmd, so $0 does not
# identify the checkout. The documented submission command runs from the
# hive_video root, which Slurm records in SLURM_SUBMIT_DIR.
export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

# Day 4 side 1 top, plus both Day 47 tops.
LOCATORS=${LOCATORS:-"day4_side1_top day47_side0_top day47_side1_top"}

hv_sync_env

LOCATOR="$(hv_locator_for_task "${LOCATORS}" "${SLURM_ARRAY_TASK_ID:-0}")"

echo "Downloading ${LOCATOR} into ${DOWNLOAD_DIR}"

COMMAND=(
  uv run --no-sync python src/download/download_raw.py
  --locator "${LOCATOR}"
  --target "${DOWNLOAD_DIR}"
  --progress-every-seconds "${PROGRESS_EVERY_SECONDS:-120}"
  --retries "${RETRIES:-8}"
)

if [ "${FORCE:-0}" = "1" ]; then
  COMMAND+=(--force)
fi

printf ' %q' "${COMMAND[@]}"
printf '\n'

"${COMMAND[@]}"
