#!/bin/bash
# Upload and byte-size verify the three QC-roll compression comparison files.

#SBATCH --job-name=bees-qc-compress-upload
#SBATCH --cpus-per-task=1
#SBATCH --mem=4GB
#SBATCH -t 02:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.qc-compress-upload.%j.out
#SBATCH -e slurm.qc-compress-upload.%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

if [ -z "${HV_QC_COMPRESSION_KEY:-}" ] || [ -z "${HV_QC_COMPRESSION_WORK_DIR:-}" ]; then
  echo "HV_QC_COMPRESSION_KEY and HV_QC_COMPRESSION_WORK_DIR are required." >&2
  exit 2
fi

hv_sync_env

KEY="${HV_QC_COMPRESSION_KEY}"
WORK_DIR="${HV_QC_COMPRESSION_WORK_DIR}"
SMOKE_DIR="${WORK_DIR}/qc_compression_smoke"
STAGING="${WORK_DIR}/qc_compression_smoke_upload"
REMOTE="${HF_RESEQ_PREFIX}/qc_compression_smoke/reseq_${KEY}"
REMOTE_PREFIX="${REMOTE#${HF_BUCKET}/}"
REMOTE_LISTING="${WORK_DIR}/qc_compression_smoke_upload.remote_listing.json"

for quality in high medium low; do
  hv_require_file "${SMOKE_DIR}/qc_roll_${KEY}.${quality}.mp4" \
    "QC compression output is missing for ${KEY} (${quality})."
  hv_require_file "${SMOKE_DIR}/qc_roll_${KEY}.${quality}.compression.json" \
    "QC compression metadata is missing for ${KEY} (${quality})."
done

# Check access before staging anything. The token itself is never printed.
if [ -z "${HF_TOKEN:-}" ] && [ ! -f "${HF_HOME:-${HOME}/.cache/huggingface}/token" ]; then
  echo "No Hugging Face credentials found." >&2
  echo "Set HF_TOKEN in the job environment, or run 'hf auth login' on the cluster." >&2
  exit 5
fi
echo "Checking Hugging Face identity"
uv run --no-sync hf auth whoami --format json

rm -rf "${STAGING}"
mkdir -p "${STAGING}"
for quality in high medium low; do
  cp "${SMOKE_DIR}/qc_roll_${KEY}.${quality}.mp4" "${STAGING}/"
  cp "${SMOKE_DIR}/qc_roll_${KEY}.${quality}.compression.json" "${STAGING}/"
done
printf '%s\n' \
  "# QC-roll compression comparison: ${KEY}" \
  "" \
  "These are H.264 sharing copies of the Stage 1a green-flash QC roll." \
  "They are comparison artifacts only and do not replace archival resequenced videos." \
  "" \
  "Profiles:" \
  "- high: CRF 18" \
  "- medium: CRF 23" \
  "- low: CRF 28" \
  >"${STAGING}/README.md"

echo "Uploading QC comparison files: ${STAGING} -> ${REMOTE}"
du -sh "${STAGING}"
hv_time_step "hf_sync_qc_compression_smoke" \
  uv run --no-sync hf sync "${STAGING}" "${REMOTE}" --exclude "**/.DS_Store"

echo "Listing remote destination for byte-size verification"
uv run --no-sync hf buckets list "${REMOTE}" --recursive --format json \
  >"${REMOTE_LISTING}.partial"
mv "${REMOTE_LISTING}.partial" "${REMOTE_LISTING}"
uv run --no-sync python src/utils/verify_bucket_listing.py \
  --local-dir "${STAGING}" \
  --listing "${REMOTE_LISTING}" \
  --remote-prefix "${REMOTE_PREFIX}"

echo "QC compression comparison backed up and verified at ${REMOTE}"
