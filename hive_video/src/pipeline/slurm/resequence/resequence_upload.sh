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
# Uploads the final MP4 plus the cuts, segment definitions, ordering, automatic
# join-QC decision, frame mapping, and metadata needed to audit the
# resequencing. Detection images and intermediate part videos stay on scratch.
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

# Slurm executes a copy of this script from /var/spool/slurmd, so $0 does not
# identify the checkout. The documented submission command runs from the
# hive_video root, which Slurm records in SLURM_SUBMIT_DIR.
export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

if [ -z "${HV_UPLOAD_KEY:-}" ] || [ -z "${HV_UPLOAD_WORK_DIR:-}" ]; then
  echo "HV_UPLOAD_KEY and HV_UPLOAD_WORK_DIR must both be set." >&2
  exit 2
fi

hv_sync_env

WORK_DIR="${HV_UPLOAD_WORK_DIR}"
KEY="${HV_UPLOAD_KEY}"
FINAL_VIDEO="${WORK_DIR}/output/reseq_${KEY}.mp4"
FINAL_MAPPING="${WORK_DIR}/output/reseq_${KEY}.frame_mapping.csv"
FINAL_METADATA="${WORK_DIR}/output/reseq_${KEY}.metadata.json"
FINAL_ORDER="${WORK_DIR}/output/reseq_${KEY}.order.csv"
PARTS_MANIFEST="${WORK_DIR}/output/reseq_${KEY}.parts_manifest.csv"
PROPOSED_CUTS="${WORK_DIR}/qc/cut_review.proposed.csv"
VERIFIED_CUTS="${WORK_DIR}/qc/cut_review.verified.csv"
DETECT_METADATA="${WORK_DIR}/qc/metadata.json"
SEGMENTS="${WORK_DIR}/segments/segments.csv"
RANKED_EDGES="${WORK_DIR}/order/ranked_edges.csv"
GREEDY_ORDER="${WORK_DIR}/order/greedy_order.csv"
AUTO_QC_SCORES="${WORK_DIR}/review/auto_qc.join_scores.csv"
AUTO_QC_FLAGGED="${WORK_DIR}/review/auto_qc.flagged_joins.csv"
AUTO_QC_SUMMARY="${WORK_DIR}/review/auto_qc.summary.json"
AUTO_QC_APPROVAL="${WORK_DIR}/review/auto_qc.manual_approval.json"
AUTO_QC_DONE="${WORK_DIR}/review/.auto_qc.complete"
STAGE1A_DONE="${WORK_DIR}/review/.stage1a.complete"
REASSEMBLE_INPUTS="${WORK_DIR}/output/.reassemble.inputs"
REASSEMBLE_DONE="${WORK_DIR}/output/.reassemble.complete"
STAGING="${WORK_DIR}/upload"
MANIFEST_COMMIT_DIR="${WORK_DIR}/upload_commit"
CURRENT_MANIFEST="${MANIFEST_COMMIT_DIR}/CURRENT_ARTIFACTS.json"
REMOTE="${HF_RESEQ_PREFIX}/reseq_${KEY}"
REMOTE_PREFIX="${REMOTE#${HF_BUCKET}/}"
REMOTE_LISTING="${WORK_DIR}/upload.remote_listing.json"

hv_require_file "${FINAL_VIDEO}" "Stage 2 has not produced a final video for ${KEY}."
hv_require_file "${FINAL_MAPPING}" "Stage 2 has not produced a frame mapping for ${KEY}."
hv_require_file "${FINAL_METADATA}" "Stage 2 has not produced metadata for ${KEY}."
hv_require_file "${FINAL_ORDER}" "Stage 2 has not produced its resolved order for ${KEY}."
hv_require_file "${PARTS_MANIFEST}" "Stage 2 has not produced its parts manifest for ${KEY}."
hv_require_file "${PROPOSED_CUTS}" "Stage 1 cut proposal is missing for ${KEY}."
hv_require_file "${DETECT_METADATA}" "Stage 1 detector metadata is missing for ${KEY}."
hv_require_file "${SEGMENTS}" "Stage 1a segment table is missing for ${KEY}."
hv_require_file "${RANKED_EDGES}" "Stage 1a ranked edges are missing for ${KEY}."
hv_require_file "${GREEDY_ORDER}" "Stage 1a greedy order is missing for ${KEY}."
hv_require_file "${AUTO_QC_SCORES}" "Stage 1a auto-QC scores are missing for ${KEY}."
hv_require_file "${AUTO_QC_FLAGGED}" "Stage 1a flagged-join table is missing for ${KEY}."
hv_require_file "${AUTO_QC_SUMMARY}" "Stage 1a auto-QC summary is missing for ${KEY}."
hv_require_file "${AUTO_QC_DONE}" "Stage 1a auto-QC completion marker is missing for ${KEY}."
hv_require_file "${STAGE1A_DONE}" "Stage 1a completion marker is missing for ${KEY}."
hv_require_file "${REASSEMBLE_INPUTS}" "Stage 2 input manifest is missing for ${KEY}."
hv_require_file "${REASSEMBLE_DONE}" "Stage 2 completion manifest is missing for ${KEY}."

if [ -f "${VERIFIED_CUTS}" ]; then
  CUTS="${VERIFIED_CUTS}"
  CUT_REVIEW_LINE="Source cuts use the manually edited cut_review.verified.csv table."
else
  CUTS="${PROPOSED_CUTS}"
  CUT_REVIEW_LINE="Source cuts use the inspected, unchanged cut_review.proposed.csv table."
fi
CUTS_NAME="$(basename "${CUTS}")"

AUTO_QC_OUTPUT_SIGNATURE="outputs=$(hv_file_bundle_fingerprint \
  "${AUTO_QC_SCORES}" "${AUTO_QC_FLAGGED}" "${AUTO_QC_SUMMARY}")"
if ! grep -Fq "|${AUTO_QC_OUTPUT_SIGNATURE}" "${AUTO_QC_DONE}"; then
  echo "Auto-QC outputs do not match their completion marker; refusing upload." >&2
  exit 4
fi

CUTS_FINGERPRINT="$(hv_file_fingerprint "${CUTS}")"
if ! grep -Fq \
    "v2|cuts_file=$(basename "${CUTS}")|cuts=${CUTS_FINGERPRINT}" \
    "${STAGE1A_DONE}"; then
  echo "Current cut-review inputs do not match the completed Stage 1a run." >&2
  exit 4
fi
AUTO_QC_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_SUMMARY}")"
if ! grep -Fq "|auto_qc_report=${AUTO_QC_FINGERPRINT}|" "${STAGE1A_DONE}"; then
  echo "Current auto-QC report does not match the completed Stage 1a run." >&2
  exit 4
fi
AUTO_QC_BUNDLE_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_DONE}")"
if ! grep -Fq "|auto_qc_bundle=${AUTO_QC_BUNDLE_FINGERPRINT}|" "${STAGE1A_DONE}"; then
  echo "Current auto-QC bundle does not match the completed Stage 1a run." >&2
  exit 4
fi

uv run --no-sync python -c '
import json
from pathlib import Path
import sys
from src.resequence.diagnostics.auto_qc_segment_joins import validate_summary_inputs

summary_path = Path(sys.argv[1])
summary = json.loads(summary_path.read_text())
video = Path(summary["paths"]["video"])
valid, message = validate_summary_inputs(
    summary_path,
    video,
    Path(sys.argv[2]),
    Path(sys.argv[3]),
    Path(sys.argv[4]),
)
print(message)
raise SystemExit(0 if valid else 1)
' \
  "${AUTO_QC_SUMMARY}" \
  "${SEGMENTS}" \
  "${GREEDY_ORDER}" \
  "${DETECT_METADATA}"

AUTO_QC_DECISION="$(uv run --no-sync python -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["decision"])' \
  "${AUTO_QC_SUMMARY}")"
APPROVAL_FINGERPRINT="not_required"
case "${AUTO_QC_DECISION}" in
  auto_pass)
    JOIN_QC_LINE="Segment joins passed the automatic direct-boundary and ambiguity checks."
    ;;
  manual_review_required)
    hv_require_file "${AUTO_QC_APPROVAL}" \
      "Flagged join QC has no manual approval; refusing to publish it as validated."
    uv run --no-sync python src/resequence/diagnostics/approve_manual_join_qc.py check \
      --summary "${AUTO_QC_SUMMARY}" \
      --approval "${AUTO_QC_APPROVAL}"
    APPROVAL_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_APPROVAL}")"
    JOIN_QC_LINE="Automatic join QC flagged joins; the current report-bound"
    JOIN_QC_LINE="${JOIN_QC_LINE} approval records the subsequent manual review."
    ;;
  *)
    echo "Unexpected auto-QC decision: ${AUTO_QC_DECISION}" >&2
    exit 4
    ;;
esac

REASSEMBLE_INPUT_SIGNATURE="$(cat "${REASSEMBLE_INPUTS}")"
CURRENT_REASSEMBLE_PREFIX="v3|segments=$(hv_file_fingerprint "${SEGMENTS}")"
CURRENT_REASSEMBLE_PREFIX="${CURRENT_REASSEMBLE_PREFIX}|ranked=$(hv_file_fingerprint \
  "${RANKED_EDGES}")"
CURRENT_REASSEMBLE_PREFIX="${CURRENT_REASSEMBLE_PREFIX}|order=$(hv_file_fingerprint \
  "${GREEDY_ORDER}")"
CURRENT_REASSEMBLE_PREFIX="${CURRENT_REASSEMBLE_PREFIX}|tool=$(hv_file_fingerprint \
  src/resequence/reassemble_video_from_segments.py)"
CURRENT_REASSEMBLE_PREFIX="${CURRENT_REASSEMBLE_PREFIX}|stage1a=$(hv_file_fingerprint \
  "${STAGE1A_DONE}")"
CURRENT_REASSEMBLE_PREFIX="${CURRENT_REASSEMBLE_PREFIX}|auto_qc=${AUTO_QC_FINGERPRINT}"
CURRENT_REASSEMBLE_PREFIX="${CURRENT_REASSEMBLE_PREFIX}|approval=${APPROVAL_FINGERPRINT}"
if ! grep -Fq "${CURRENT_REASSEMBLE_PREFIX}|scale_width=" "${REASSEMBLE_INPUTS}"; then
  echo "Current pipeline inputs do not match the completed Stage 2 render." >&2
  exit 4
fi

REASSEMBLE_OUTPUT_SIGNATURE="outputs=video=$(hv_file_stat_fingerprint "${FINAL_VIDEO}")"
REASSEMBLE_OUTPUT_SIGNATURE="${REASSEMBLE_OUTPUT_SIGNATURE}|mapping=$(hv_file_fingerprint \
  "${FINAL_MAPPING}")"
REASSEMBLE_OUTPUT_SIGNATURE="${REASSEMBLE_OUTPUT_SIGNATURE}|metadata=$(hv_file_fingerprint \
  "${FINAL_METADATA}")"
REASSEMBLE_OUTPUT_SIGNATURE="${REASSEMBLE_OUTPUT_SIGNATURE}|order=$(hv_file_fingerprint \
  "${FINAL_ORDER}")"
REASSEMBLE_OUTPUT_SIGNATURE="${REASSEMBLE_OUTPUT_SIGNATURE}|parts=$(hv_file_fingerprint \
  "${PARTS_MANIFEST}")"
if [ "$(cat "${REASSEMBLE_DONE}")" != \
    "${REASSEMBLE_INPUT_SIGNATURE}|${REASSEMBLE_OUTPUT_SIGNATURE}" ]; then
  echo "Final render artifacts do not match the Stage 2 completion manifest." >&2
  exit 4
fi

# Check credentials before staging: copying a 33 GB MP4 and only then finding
# out there is no write token is an expensive way to fail.
if [ -z "${HF_TOKEN:-}" ] && [ ! -f "${HF_HOME:-${HOME}/.cache/huggingface}/token" ]; then
  echo "No HuggingFace credentials found." >&2
  echo "Set HF_TOKEN in the job environment, or run 'hf auth login' on the cluster." >&2
  exit 5
fi
echo "Checking Hugging Face identity"
uv run --no-sync hf auth whoami --format json

# Stage exactly what should be published, so the sync cannot sweep up the
# large QC artifacts or leftover part files sitting in the work directory.
rm -rf "${STAGING}"
mkdir -p "${STAGING}"
cp "${FINAL_VIDEO}" "${FINAL_MAPPING}" "${FINAL_METADATA}" "${FINAL_ORDER}" "${STAGING}/"
cp "${PARTS_MANIFEST}" "${STAGING}/"
cp "${AUTO_QC_DONE}" "${STAGING}/auto_qc.complete"
cp "${STAGE1A_DONE}" "${STAGING}/stage1a.complete"
cp "${REASSEMBLE_DONE}" "${STAGING}/reassemble.complete"
cp "${DETECT_METADATA}" "${STAGING}/detector_metadata.json"

for extra in \
  "${CUTS}" \
  "${SEGMENTS}" \
  "${RANKED_EDGES}" \
  "${GREEDY_ORDER}" \
  "${AUTO_QC_SCORES}" \
  "${AUTO_QC_FLAGGED}" \
  "${AUTO_QC_SUMMARY}"; do
  cp "${extra}" "${STAGING}/"
done

case "${AUTO_QC_DECISION}" in
  auto_pass)
    ;;
  manual_review_required)
    for manual_artifact in \
      "${AUTO_QC_APPROVAL}" \
      "${WORK_DIR}/review/qc_roll_flagged_joins.mp4" \
      "${WORK_DIR}/review/qc_roll_flagged_joins.captions.csv"; do
      hv_require_file "${manual_artifact}" \
        "Flagged join QC is missing a manual-review audit artifact."
      cp "${manual_artifact}" "${STAGING}/"
    done
    ;;
esac

cat >"${STAGING}/README.md" <<EOF
# ${KEY}

Resequenced hive video produced by \`hive_video/src/resequence\`.

- \`CURRENT_ARTIFACTS.json\` is the authoritative current file set. This bucket
  sync is deliberately non-deleting; any unlisted object is superseded.
- Source archive: doi:10.17617/3.LLWRWR (Edmond), file \`${KEY}\`
- ${CUT_REVIEW_LINE}
- Segment ordering used the established trajectory-10 greedy procedure.
- ${JOIN_QC_LINE}

Contents:

- \`reseq_${KEY}.mp4\` - the reassembled video
- \`reseq_${KEY}.frame_mapping.csv\` - output-to-source frame mapping
- \`reseq_${KEY}.metadata.json\` - resolved render settings and completion status
- \`${CUTS_NAME}\` - the source cuts used
- \`segments.csv\` - source segment boundaries
- \`ranked_edges.csv\` - candidate joins with scores
- \`greedy_order.csv\` - the automatic ordering rendered
- \`auto_qc.join_scores.csv\` - direct-boundary score for every selected join
- \`auto_qc.flagged_joins.csv\` - joins that required review, if any
- \`auto_qc.summary.json\` - thresholds and video-level QC decision
- \`detector_metadata.json\` - detector scale and median/MAD normalization input
- \`auto_qc.manual_approval.json\` - report-bound approval when review was required
- \`qc_roll_flagged_joins.mp4\` and captions - reviewed evidence when manual QC was required
- \`auto_qc.complete\`, \`stage1a.complete\`, and \`reassemble.complete\` - bound completion manifests
EOF

rm -rf "${MANIFEST_COMMIT_DIR}"
mkdir -p "${MANIFEST_COMMIT_DIR}"
uv run --no-sync python src/utils/write_current_artifacts_manifest.py \
  --staging-dir "${STAGING}" \
  --key "${KEY}" \
  --auto-qc-summary "${STAGING}/auto_qc.summary.json" \
  --reassembly-completion "${STAGING}/reassemble.complete" \
  --hash-threshold-bytes "${UPLOAD_MANIFEST_HASH_MAX_BYTES:-1073741824}"
mv "${STAGING}/CURRENT_ARTIFACTS.json" "${CURRENT_MANIFEST}"

echo "Uploading payload ${STAGING} -> ${REMOTE}"
du -sh "${STAGING}"

# Preserve older objects for audit/history. The current manifest is withheld
# until the entire payload has been uploaded and remotely verified.
HF_CMD=(
  uv run --no-sync hf sync
  "${STAGING}"
  "${REMOTE}"
  --no-delete
  --exclude "**/.DS_Store"
)
if [ "${DRY_RUN:-0}" = "1" ]; then
  HF_CMD+=(--dry-run)
fi

printf ' %q' "${HF_CMD[@]}"
printf '\n'

hv_time_step "hf_sync" "${HF_CMD[@]}"

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "Dry run complete; nothing was uploaded."
  exit 0
fi

echo "Listing remote destination for byte-size verification"
uv run --no-sync hf buckets list "${REMOTE}" --recursive --format json \
  >"${REMOTE_LISTING}.partial"
mv "${REMOTE_LISTING}.partial" "${REMOTE_LISTING}"

uv run --no-sync python src/utils/verify_bucket_listing.py \
  --local-dir "${STAGING}" \
  --listing "${REMOTE_LISTING}" \
  --remote-prefix "${REMOTE_PREFIX}"

echo "Publishing CURRENT_ARTIFACTS.json as the final commit marker"
uv run --no-sync hf buckets cp \
  "${CURRENT_MANIFEST}" \
  "${REMOTE}/CURRENT_ARTIFACTS.json"

uv run --no-sync hf buckets list "${REMOTE}" --recursive --format json \
  >"${REMOTE_LISTING}.partial"
mv "${REMOTE_LISTING}.partial" "${REMOTE_LISTING}"
uv run --no-sync python src/utils/verify_bucket_listing.py \
  --local-dir "${MANIFEST_COMMIT_DIR}" \
  --listing "${REMOTE_LISTING}" \
  --remote-prefix "${REMOTE_PREFIX}"

echo "Backed up and remotely verified ${KEY} at ${REMOTE}"
