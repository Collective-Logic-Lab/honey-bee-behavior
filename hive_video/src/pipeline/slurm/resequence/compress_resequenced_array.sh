#!/bin/bash
# Create one share-oriented H.264 derivative per completed resequenced video.
#
#   sbatch src/pipeline/slurm/resequence/compress_resequenced_array.sh
#
# Run compress_resequenced_smoke_test.sh first and inspect all three samples.
# This array creates exactly one selected quality per source (medium by default)
# and leaves the archival resequenced MP4 untouched.

#SBATCH --job-name=bees-compress
#SBATCH --array=0-2
#SBATCH --cpus-per-task=8
#SBATCH --mem=8GB
#SBATCH -t 12:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.compress.%A_%a.out
#SBATCH -e slurm.compress.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

LOCATORS=${LOCATORS:-"start4_side1_top start47_side0_top start47_side1_top"}
QUALITY=${QUALITY:-medium}
COMPRESS_PRESET=${COMPRESS_PRESET:-medium}

case "${QUALITY}" in
  high|medium|low) ;;
  *)
    echo "QUALITY must be high, medium, or low; got ${QUALITY}" >&2
    exit 2
    ;;
esac

hv_sync_env
hv_require_ffmpeg
LOCATOR="$(hv_locator_for_task "${LOCATORS}" "${SLURM_ARRAY_TASK_ID:-0}")"
hv_resolve "${LOCATOR}"

FINAL_VIDEO="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.mp4"
COMPRESSED_DIR="${HV_WORK_DIR}/compressed"
COMPRESSED_VIDEO="${COMPRESSED_DIR}/reseq_${RESEQ_KEY}.${QUALITY}.mp4"
COMPRESSED_METADATA="${COMPRESSED_DIR}/reseq_${RESEQ_KEY}.${QUALITY}.compression.json"

hv_require_file "${FINAL_VIDEO}" \
  "Stage 2 must finish before this video can be compressed."
mkdir -p "${COMPRESSED_DIR}"

hv_time_step "compress_${QUALITY}" \
  uv run --no-sync python src/resequence/compress_resequenced.py \
    "${FINAL_VIDEO}" \
    --out "${COMPRESSED_VIDEO}" \
    --metadata-out "${COMPRESSED_METADATA}" \
    --quality "${QUALITY}" \
    --preset "${COMPRESS_PRESET}" \
    --threads "${SLURM_CPUS_PER_TASK:-8}"

hv_require_file "${COMPRESSED_VIDEO}" "Compression exited without an MP4."
hv_require_file "${COMPRESSED_METADATA}" "Compression exited without metadata."

if [ "${SKIP_UPLOAD:-0}" != "1" ] && [ -n "${SLURM_JOB_ID:-}" ]; then
  UPLOAD_JOB=$(sbatch --parsable \
    --dependency="afterok:${SLURM_JOB_ID}" \
    --kill-on-invalid-dep=yes \
    --export="ALL,HV_COMPRESSION_KEY=${RESEQ_KEY},HV_COMPRESSION_WORK_DIR=${HV_WORK_DIR},\
HV_COMPRESSION_QUALITY=${QUALITY}" \
    "${SCRIPT_DIR}/compress_resequenced_upload.sh")
  echo "queued compression upload job ${UPLOAD_JOB}, dependent on ${SLURM_JOB_ID}"
fi

echo "Compression complete for ${RESEQ_KEY}: ${COMPRESSED_VIDEO}"
