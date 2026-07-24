#!/bin/bash
# Back up one resequenced video to the Collective Logic Lab HuggingFace bucket.
#
# Normally submitted automatically by resequence_stage2_array.sh as a dependent
# child job, so it gets its own wall clock. To run it by hand:
#
#   sbatch --export=ALL,HV_UPLOAD_KEY=start47_20190731_184423_side1_top,\
# HV_UPLOAD_WORK_DIR=/scratch/pdressla/honey-bee/artifacts/resequence/reseq_start47_20190731_184423_side1_top \
#       src/pipeline/slurm/resequence/resequence_upload.sh
#
# Uploads the final MP4 plus the segment and ordering CSVs that make the
# resequencing reproducible. QC and detection artifacts stay on scratch.
#
# The bucket is public to read but writing needs a token. Log in once on the
# cluster with `hf auth login`, or set HF_TOKEN in the job environment.

#SBATCH --job-name=bees-reseq-upload
#SBATCH --cpus-per-task=1
#SBATCH --mem=4GB
#SBATCH -t 06:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.reseq-upload.%j.out
#SBATCH -e slurm.reseq-upload.%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

source "$(dirname "$(readlink -f "$0")")/common.sh"

if [ -z "${HV_UPLOAD_KEY:-}" ] || [ -z "${HV_UPLOAD_WORK_DIR:-}" ]; then
  echo "HV_UPLOAD_KEY and HV_UPLOAD_WORK_DIR must both be set." >&2
  exit 2
fi

hv_sync_env

WORK_DIR="${HV_UPLOAD_WORK_DIR}"
KEY="${HV_UPLOAD_KEY}"
FINAL_VIDEO="${WORK_DIR}/output/reseq_${KEY}.mp4"
STAGING="${WORK_DIR}/upload"
REMOTE="${HF_RESEQ_PREFIX}/reseq_${KEY}"

hv_require_file "${FINAL_VIDEO}" "Stage 2 has not produced a final video for ${KEY}."

# Check credentials before staging: copying a 33 GB MP4 and only then finding
# out there is no write token is an expensive way to fail.
if [ -z "${HF_TOKEN:-}" ] && [ ! -f "${HF_HOME:-${HOME}/.cache/huggingface}/token" ]; then
  echo "No HuggingFace credentials found." >&2
  echo "Set HF_TOKEN in the job environment, or run 'hf auth login' on the cluster." >&2
  exit 5
fi

# Stage exactly what should be published, so the sync cannot sweep up the
# large QC artifacts or leftover part files sitting in the work directory.
rm -rf "${STAGING}"
mkdir -p "${STAGING}"
cp "${FINAL_VIDEO}" "${STAGING}/"

for extra in \
  "${WORK_DIR}/output/reseq_${KEY}_frame_map.csv" \
  "${WORK_DIR}/segments/segments.csv" \
  "${WORK_DIR}/order/ranked_edges.csv" \
  "${WORK_DIR}/order/greedy_order.csv" \
  "${WORK_DIR}/order/greedy_order.verified.csv"; do
  if [ -f "${extra}" ]; then
    cp "${extra}" "${STAGING}/"
  else
    echo "note: ${extra} not present, skipping"
  fi
done

# reassemble_video_from_segments writes a frame mapping alongside the MP4; its
# exact name depends on the output path, so catch any stragglers.
for mapping in "${WORK_DIR}"/output/*.csv; do
  if [ -f "${mapping}" ] && [ ! -f "${STAGING}/$(basename "${mapping}")" ]; then
    cp "${mapping}" "${STAGING}/"
  fi
done

cat >"${STAGING}/README.md" <<EOF
# ${KEY}

Resequenced hive video produced by \`hive_video/src/resequence\`.

- Source archive: doi:10.17617/3.LLWRWR (Edmond), file \`${KEY}\`
- Segment ordering was verified by hand against the join review video.

Contents:

- \`reseq_${KEY}.mp4\` - the reassembled video
- \`segments.csv\` - source segment boundaries
- \`ranked_edges.csv\` - candidate joins with scores
- \`greedy_order.csv\` - automatic ordering proposal
- \`greedy_order.verified.csv\` - the hand-checked ordering actually rendered
EOF

echo "Uploading ${STAGING} -> ${REMOTE}"
du -sh "${STAGING}"

HF_CMD=(uv run --no-sync hf sync "${STAGING}" "${REMOTE}" --exclude "**/.DS_Store")
if [ "${DRY_RUN:-0}" = "1" ]; then
  HF_CMD+=(--dry-run)
fi

printf ' %q' "${HF_CMD[@]}"
printf '\n'

hv_time_step "hf_sync" "${HF_CMD[@]}"

echo "Backed up ${KEY} to ${REMOTE}"
