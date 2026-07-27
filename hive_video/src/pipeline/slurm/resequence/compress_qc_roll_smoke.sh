#!/bin/bash
# Compress one Stage 1a QC roll at high, medium, and low sharing profiles.
#
#   sbatch src/pipeline/slurm/resequence/compress_qc_roll_smoke.sh
#
# This is the comparison artifact for choosing the profile that will later be
# used on the full archival resequenced videos. It never changes a QC roll or
# a final reassembled video. A dependent job uploads only these three samples
# and their provenance to the designated Hugging Face comparison prefix.

#SBATCH --job-name=bees-qc-compress
#SBATCH --cpus-per-task=8
#SBATCH --mem=8GB
#SBATCH -t 02:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.qc-compress.%j.out
#SBATCH -e slurm.qc-compress.%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

# This QC roll is deliberately the entire review artifact, not a short excerpt:
# it is what the team will actually inspect to choose the sharing profile.
QC_LOCATOR=start4_side1_top
QC_QUALITIES="high medium low"
COMPRESS_PRESET=medium

hv_sync_env
hv_require_ffmpeg
hv_resolve "${QC_LOCATOR}"

QC_ROLL="${QC_ROLL:-${HV_REVIEW_DIR}/qc_roll_greedy_order.mp4}"
if [ ! -f "${QC_ROLL}" ] && [ -f "${HV_REVIEW_DIR}/qc_roll_flagged_joins.mp4" ]; then
  AUTO_QC_SUMMARY="${HV_REVIEW_DIR}/auto_qc.summary.json"
  if [ -f "${AUTO_QC_SUMMARY}" ]; then
    AUTO_QC_DECISION="$(uv run --no-sync python -c \
      'import json,sys; print(json.load(open(sys.argv[1]))["decision"])' \
      "${AUTO_QC_SUMMARY}")"
    if [ "${AUTO_QC_DECISION}" = "manual_review_required" ]; then
      QC_ROLL="${HV_REVIEW_DIR}/qc_roll_flagged_joins.mp4"
      echo "Using the current flagged-only Stage 1a roll: ${QC_ROLL}"
    fi
  fi
fi
SMOKE_DIR="${HV_WORK_DIR}/qc_compression_smoke"
hv_require_file "${QC_ROLL}" \
  "No QC roll exists. Rerun Stage 1a with WRITE_ALL_QC_ROLLS=1, or set QC_ROLL explicitly."
mkdir -p "${SMOKE_DIR}"

for quality in ${QC_QUALITIES}; do
  case "${quality}" in
    high|medium|low) ;;
    *)
      echo "Unknown QC comparison quality ${quality}; use high, medium, or low." >&2
      exit 2
      ;;
  esac
  OUTPUT="${SMOKE_DIR}/qc_roll_${RESEQ_KEY}.${quality}.mp4"
  METADATA="${SMOKE_DIR}/qc_roll_${RESEQ_KEY}.${quality}.compression.json"
  hv_time_step "compress_qc_roll_${quality}" \
    uv run --no-sync python src/resequence/compress_resequenced.py \
      "${QC_ROLL}" \
      --out "${OUTPUT}" \
      --metadata-out "${METADATA}" \
      --quality "${quality}" \
      --preset "${COMPRESS_PRESET}" \
      --threads "${SLURM_CPUS_PER_TASK:-8}"
done

if [ -n "${SLURM_JOB_ID:-}" ]; then
  UPLOAD_JOB=$(sbatch --parsable \
    --dependency="afterok:${SLURM_JOB_ID}" \
    --kill-on-invalid-dep=yes \
    --export="ALL,HV_QC_COMPRESSION_KEY=${RESEQ_KEY},HV_QC_COMPRESSION_WORK_DIR=${HV_WORK_DIR}" \
    "${SCRIPT_DIR}/compress_qc_roll_smoke_upload.sh")
  echo "queued QC-comparison upload job ${UPLOAD_JOB}, dependent on ${SLURM_JOB_ID}"
fi

echo
echo "QC compression comparison complete for ${RESEQ_KEY}."
echo "  local files: ${SMOKE_DIR}"
echo "  high / medium / low will be uploaded by the dependent verification job."
