#!/bin/bash
# Backfill maximum-compression sharing derivatives for five existing resequenced videos.
#
#   sbatch src/pipeline/slurm/resequence/compress_existing_low_backfill_array.sh
#
# The first three sources are the current Stage 2 outputs. The final two are
# earlier archival reassemblies kept under prior_batch. Every task writes an
# H.264 low (CRF 28) sharing derivative beside its source work area, preserves
# the original MP4, and queues a separately resourced verified upload.

#SBATCH --job-name=bees-compress-low-backfill
#SBATCH --array=0-4%2
#SBATCH --cpus-per-task=8
#SBATCH --mem=8GB
#SBATCH -t 12:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.compress-low.%A_%a.out
#SBATCH -e slurm.compress-low.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

# This is the reviewed, one-time backfill plan. Keep source paths and canonical
# keys side by side so the five resulting remote folders are unambiguous.
KEYS=(
  "start04_20190609_175013_side1_top"
  "start47_20190731_184423_side0_top"
  "start47_20190731_184423_side1_top"
  "start04_20190609_175013_side0_top"
  "start03_20190608_181426_side0_top"
)
SOURCES=(
  "${RESEQ_ROOT}/reseq_start04_20190609_175013_side1_top/output/reseq_start04_20190609_175013_side1_top.mp4"
  "${RESEQ_ROOT}/reseq_start47_20190731_184423_side0_top/output/reseq_start47_20190731_184423_side0_top.mp4"
  "${RESEQ_ROOT}/reseq_start47_20190731_184423_side1_top/output/reseq_start47_20190731_184423_side1_top.mp4"
  "${RESEQ_ROOT}/prior_batch/reseq_1_start04__20190609_175013_side0_top.mp4"
  "${RESEQ_ROOT}/prior_batch/reseq_1_start03__20190608_181426_side0_top.mp4"
)
WORK_DIRS=(
  "${RESEQ_ROOT}/reseq_start04_20190609_175013_side1_top"
  "${RESEQ_ROOT}/reseq_start47_20190731_184423_side0_top"
  "${RESEQ_ROOT}/reseq_start47_20190731_184423_side1_top"
  "${RESEQ_ROOT}/prior_batch"
  "${RESEQ_ROOT}/prior_batch"
)

TASK_ID=${SLURM_ARRAY_TASK_ID:-0}
if [ "${TASK_ID}" -lt 0 ] || [ "${TASK_ID}" -ge "${#KEYS[@]}" ]; then
  echo "SLURM_ARRAY_TASK_ID=${TASK_ID} is outside the five-item backfill plan." >&2
  exit 2
fi

KEY="${KEYS[${TASK_ID}]}"
SOURCE="${SOURCES[${TASK_ID}]}"
WORK_DIR="${WORK_DIRS[${TASK_ID}]}"
QUALITY=low
COMPRESSED_DIR="${WORK_DIR}/compressed"
COMPRESSED_VIDEO="${COMPRESSED_DIR}/reseq_${KEY}.${QUALITY}.mp4"
COMPRESSED_METADATA="${COMPRESSED_DIR}/reseq_${KEY}.${QUALITY}.compression.json"

hv_sync_env
hv_require_ffmpeg

echo "Maximum-compression backfill task ${TASK_ID} of 5"
echo "  key    : ${KEY}"
echo "  source : ${SOURCE}"
echo "  output : ${COMPRESSED_VIDEO}"
hv_require_file "${SOURCE}" "Expected archival resequenced source is missing."
mkdir -p "${COMPRESSED_DIR}"

hv_time_step "compress_low" \
  uv run --no-sync python src/resequence/compress_resequenced.py \
    "${SOURCE}" \
    --out "${COMPRESSED_VIDEO}" \
    --metadata-out "${COMPRESSED_METADATA}" \
    --quality "${QUALITY}" \
    --preset medium \
    --threads "${SLURM_CPUS_PER_TASK:-8}"

hv_require_file "${COMPRESSED_VIDEO}" "Compression exited without an MP4."
hv_require_file "${COMPRESSED_METADATA}" "Compression exited without metadata."

if [ -n "${SLURM_JOB_ID:-}" ]; then
  UPLOAD_JOB=$(sbatch --parsable \
    --dependency="afterok:${SLURM_JOB_ID}" \
    --kill-on-invalid-dep=yes \
    --export="ALL,HV_COMPRESSION_KEY=${KEY},HV_COMPRESSION_WORK_DIR=${WORK_DIR},\
HV_COMPRESSION_QUALITY=${QUALITY}" \
    "${SCRIPT_DIR}/compress_resequenced_upload.sh")
  echo "queued upload job ${UPLOAD_JOB}, dependent on ${SLURM_JOB_ID}"
fi

echo "Maximum-compression sharing derivative complete for ${KEY}: ${COMPRESSED_VIDEO}"
