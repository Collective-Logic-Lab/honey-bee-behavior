#!/bin/bash
# Upload one verified compressed derivative after its compression job succeeds.

#SBATCH --job-name=bees-compress-upload
#SBATCH --cpus-per-task=1
#SBATCH --mem=4GB
#SBATCH -t 06:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.compress-upload.%j.out
#SBATCH -e slurm.compress-upload.%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

if [ -z "${HV_COMPRESSION_KEY:-}" ] || \
   [ -z "${HV_COMPRESSION_WORK_DIR:-}" ] || \
   [ -z "${HV_COMPRESSION_QUALITY:-}" ]; then
  echo "HV_COMPRESSION_KEY, HV_COMPRESSION_WORK_DIR, and HV_COMPRESSION_QUALITY are required." >&2
  exit 2
fi

case "${HV_COMPRESSION_QUALITY}" in
  high|medium|low) ;;
  *)
    echo "Unsupported compression quality: ${HV_COMPRESSION_QUALITY}" >&2
    exit 2
    ;;
esac

hv_sync_env

WORK_DIR="${HV_COMPRESSION_WORK_DIR}"
KEY="${HV_COMPRESSION_KEY}"
QUALITY="${HV_COMPRESSION_QUALITY}"
hv_require_pilot_root_for_path "${WORK_DIR}"
VIDEO="${WORK_DIR}/compressed/reseq_${KEY}.${QUALITY}.mp4"
METADATA="${WORK_DIR}/compressed/reseq_${KEY}.${QUALITY}.compression.json"
STAGING="${WORK_DIR}/compression_upload_${KEY}_${QUALITY}"
REMOTE="${HF_RESEQ_PREFIX}/compressed/reseq_${KEY}/${QUALITY}"
REMOTE_PREFIX="${REMOTE#${HF_BUCKET}/}"
REMOTE_LISTING="${WORK_DIR}/compression_upload_${KEY}_${QUALITY}.remote_listing.json"

hv_require_file "${VIDEO}" "Compression output is missing for ${KEY}."
hv_require_file "${METADATA}" "Compression metadata is missing for ${KEY}."

if [ -z "${HF_TOKEN:-}" ] && [ ! -f "${HF_HOME:-${HOME}/.cache/huggingface}/token" ]; then
  echo "No Hugging Face credentials found." >&2
  echo "Set HF_TOKEN in the job environment, or run 'hf auth login' on the cluster." >&2
  exit 5
fi
uv run --no-sync hf auth whoami --format json

rm -rf "${STAGING}"
mkdir -p "${STAGING}"
cp "${VIDEO}" "${METADATA}" "${STAGING}/"

cat >"${STAGING}/README.md" <<EOF
# ${KEY}: ${QUALITY} share derivative

This H.264 MP4 is a smaller sharing copy of the archival resequenced video.
It does not replace the full-fidelity original under the main resequenced path.

- Quality profile: \`${QUALITY}\`
- Encoding settings and source provenance: \`$(basename "${METADATA}")\`
- Video: \`$(basename "${VIDEO}")\`
EOF

HF_CMD=(uv run --no-sync hf sync "${STAGING}" "${REMOTE}" --exclude "**/.DS_Store")
if [ "${DRY_RUN:-0}" = "1" ]; then
  HF_CMD+=(--dry-run)
fi
hv_time_step "hf_sync_compressed" "${HF_CMD[@]}"

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "Dry run complete; nothing was uploaded."
  exit 0
fi

uv run --no-sync hf buckets list "${REMOTE}" --recursive --format json \
  >"${REMOTE_LISTING}.partial"
mv "${REMOTE_LISTING}.partial" "${REMOTE_LISTING}"
uv run --no-sync python src/utils/verify_bucket_listing.py \
  --local-dir "${STAGING}" \
  --listing "${REMOTE_LISTING}" \
  --remote-prefix "${REMOTE_PREFIX}"

echo "Backed up and remotely verified ${KEY} (${QUALITY}) at ${REMOTE}"
