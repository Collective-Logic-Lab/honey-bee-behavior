#!/bin/bash
# Resequencing stage 1a: order inspected segments and run automatic join QC.
#
#   sbatch src/pipeline/slurm/resequence/resequence_stage1a_review_array.sh
#
# Run this after inspecting stage 1's proposed cut table. It uses that proposed
# table directly when no edits are needed, or qc/cut_review.verified.csv when
# edits were saved. It builds source segments, applies the established
# trajectory/10-frame greedy order, and scores every selected join with the
# independent one-frame detector feature. Clean, unambiguous videos pass
# automatically. A compact green-flash roll containing only flagged joins is
# rendered when manual review is required. It does not render the full archival
# video or upload anything.

#SBATCH --job-name=bees-reseq1a
#SBATCH --array=0-2
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB
#SBATCH -t 12:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.reseq1a.%A_%a.out
#SBATCH -e slurm.reseq1a.%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

# Slurm executes a copy of this script from /var/spool/slurmd, so $0 does not
# identify the checkout. The documented submission command runs from the
# hive_video root, which Slurm records in SLURM_SUBMIT_DIR.
export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

LOCATORS=${LOCATORS:-"start4_side1_top start47_side0_top start47_side1_top"}

hv_sync_env
hv_require_ffmpeg

LOCATOR="$(hv_locator_for_task "${LOCATORS}" "${SLURM_ARRAY_TASK_ID:-0}")"
hv_resolve "${LOCATOR}"

PROPOSED_CUTS="${HV_QC_DIR}/cut_review.proposed.csv"
VERIFIED_CUTS="${HV_QC_DIR}/cut_review.verified.csv"
DETECT_METADATA="${HV_QC_DIR}/metadata.json"
SEGMENTS="${HV_SEG_DIR}/segments.csv"
RANKED_EDGES="${HV_ORDER_DIR}/ranked_edges.csv"
GREEDY_ORDER="${HV_ORDER_DIR}/greedy_order.csv"
AUTO_QC_SCORES="${HV_REVIEW_DIR}/auto_qc.join_scores.csv"
AUTO_QC_FLAGGED="${HV_REVIEW_DIR}/auto_qc.flagged_joins.csv"
AUTO_QC_SUMMARY="${HV_REVIEW_DIR}/auto_qc.summary.json"
AUTO_QC_APPROVAL="${HV_REVIEW_DIR}/auto_qc.manual_approval.json"
AUTO_QC_DONE="${HV_REVIEW_DIR}/.auto_qc.complete"
FLAGGED_QC_ROLL="${HV_REVIEW_DIR}/qc_roll_flagged_joins.mp4"
ALL_QC_ROLL="${HV_REVIEW_DIR}/qc_roll_greedy_order.mp4"
SEGMENTS_DONE="${HV_SEG_DIR}/.build_segments.complete"
ORDER_DONE="${HV_ORDER_DIR}/.order_segments.complete"
REVIEW_DONE="${HV_REVIEW_DIR}/.join_review.complete"
STAGE1A_DONE="${HV_REVIEW_DIR}/.stage1a.complete"

auto_qc_output_signature() {
  printf 'outputs=%s' "$(hv_file_bundle_fingerprint \
    "${AUTO_QC_SCORES}" "${AUTO_QC_FLAGGED}" "${AUTO_QC_SUMMARY}")"
}

hv_require_file "${RESEQ_PATH}" "The raw video is gone; re-run download_raw_array.sh."
hv_require_file "${PROPOSED_CUTS}" "Stage 1 cut proposal is missing; rerun resequence_stage1_array.sh."
hv_require_file "${DETECT_METADATA}" "Stage 1 detector metadata is missing; rerun resequence_stage1_array.sh."
if [ -f "${VERIFIED_CUTS}" ]; then
  CUTS="${VERIFIED_CUTS}"
  RESOLVED_CUT_REVIEW_STATUS="edited_verified"
  echo "Using edited cut review: ${CUTS}"
else
  CUTS="${PROPOSED_CUTS}"
  case "${CUT_REVIEW_STATUS:-inspected}" in
    inspected)
      RESOLVED_CUT_REVIEW_STATUS="inspected"
      echo "Using manually inspected cut proposal without edits: ${CUTS}"
      ;;
    unreviewed_pilot)
      RESOLVED_CUT_REVIEW_STATUS="unreviewed_pilot"
      echo "Using unreviewed Stage 1 proposal for a bounded pipeline pilot: ${CUTS}"
      ;;
    *)
      echo "CUT_REVIEW_STATUS must be inspected or unreviewed_pilot; got" \
        "${CUT_REVIEW_STATUS}" >&2
      exit 2
      ;;
  esac
fi

mkdir -p "${HV_SEG_DIR}" "${HV_ORDER_DIR}" "${HV_REVIEW_DIR}"

CUTS_FINGERPRINT="$(hv_file_fingerprint "${CUTS}")"
SEGMENTS_SIGNATURE="v3|cuts=${CUTS_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/build_segments_from_jumps.py)|frame_count=${FRAME_COUNT:-auto}"
SEGMENTS_SIGNATURE="${SEGMENTS_SIGNATURE}|count_frames=${COUNT_FRAMES:-0}"

if hv_step_needed "${SEGMENTS_DONE}" "${SEGMENTS_SIGNATURE}" "${SEGMENTS}"; then
  rm -f \
    "${SEGMENTS_DONE}" "${ORDER_DONE}" "${AUTO_QC_DONE}" "${REVIEW_DONE}" "${STAGE1A_DONE}"
  BUILD_SEGMENTS=(
    uv run --no-sync python src/resequence/build_segments_from_jumps.py
    "${RESEQ_PATH}"
    --jumps "${CUTS}"
    --input-kind cut-review
    --out "${SEGMENTS}"
  )
  if [ -n "${FRAME_COUNT:-}" ]; then BUILD_SEGMENTS+=(--frame-count "${FRAME_COUNT}"); fi
  if [ "${COUNT_FRAMES:-0}" = "1" ]; then BUILD_SEGMENTS+=(--count-frames); fi
  hv_time_step "build_segments" "${BUILD_SEGMENTS[@]}"
  hv_require_file "${SEGMENTS}" "Segment construction completed without segments.csv."
  hv_mark_complete "${SEGMENTS_DONE}" "${SEGMENTS_SIGNATURE}"
fi

hv_require_file "${SEGMENTS}" "Segment definitions are missing; rerun stage 1a with FORCE=1."
SEGMENTS_FINGERPRINT="$(hv_file_fingerprint "${SEGMENTS}")"
ORDER_SIGNATURE="v3|segments=${SEGMENTS_FINGERPRINT}|tool=$(hv_file_fingerprint \
  src/resequence/order_video_segments.py)|window=${WINDOW_FRAMES:-10}"
ORDER_SIGNATURE="${ORDER_SIGNATURE}|signature=${SIGNATURE:-trajectory}|top_k=${TOP_K:-10}"
ORDER_SIGNATURE="${ORDER_SIGNATURE}|sample_width=${ORDER_SAMPLE_WIDTH:-default}"

if hv_step_needed \
    "${ORDER_DONE}" "${ORDER_SIGNATURE}" "${RANKED_EDGES}" "${GREEDY_ORDER}"; then
  rm -f "${ORDER_DONE}" "${AUTO_QC_DONE}" "${REVIEW_DONE}" "${STAGE1A_DONE}"
  ORDER=(
    uv run --no-sync python src/resequence/order_video_segments.py
    --segments "${SEGMENTS}"
    --out "${HV_ORDER_DIR}"
    --window-frames "${WINDOW_FRAMES:-10}"
    --signature "${SIGNATURE:-trajectory}"
    --top-k "${TOP_K:-10}"
  )
  if [ -n "${ORDER_SAMPLE_WIDTH:-}" ]; then ORDER+=(--sample-width "${ORDER_SAMPLE_WIDTH}"); fi
  hv_time_step "order_segments" "${ORDER[@]}"
  hv_require_file "${RANKED_EDGES}" "Ordering completed without ranked_edges.csv."
  hv_require_file "${GREEDY_ORDER}" "Ordering completed without greedy_order.csv."
  hv_mark_complete "${ORDER_DONE}" "${ORDER_SIGNATURE}"
fi

hv_require_file "${RANKED_EDGES}" "Ranked edges are missing; rerun stage 1a with FORCE=1."
hv_require_file "${GREEDY_ORDER}" "Greedy order is missing; rerun stage 1a with FORCE=1."
ORDER_FINGERPRINT="$(hv_file_fingerprint "${GREEDY_ORDER}")"
DETECT_FINGERPRINT="$(hv_file_fingerprint "${DETECT_METADATA}")"
RAW_FINGERPRINT="$(hv_file_stat_fingerprint "${RESEQ_PATH}")"
AUTO_QC_INPUT_SIGNATURE="v2|raw=${RAW_FINGERPRINT}|archive_md5=${RESEQ_MD5:-unknown}"
AUTO_QC_INPUT_SIGNATURE="${AUTO_QC_INPUT_SIGNATURE}|segments=${SEGMENTS_FINGERPRINT}"
AUTO_QC_INPUT_SIGNATURE="${AUTO_QC_INPUT_SIGNATURE}|order=${ORDER_FINGERPRINT}"
AUTO_QC_INPUT_SIGNATURE="${AUTO_QC_INPUT_SIGNATURE}|detector=${DETECT_FINGERPRINT}"
AUTO_QC_INPUT_SIGNATURE="${AUTO_QC_INPUT_SIGNATURE}|tool=$(hv_file_fingerprint \
  src/resequence/diagnostics/auto_qc_segment_joins.py)"
AUTO_QC_INPUT_SIGNATURE="${AUTO_QC_INPUT_SIGNATURE}|max_z=${AUTO_QC_MAX_ROBUST_Z:-15.0}"
AUTO_QC_INPUT_SIGNATURE="${AUTO_QC_INPUT_SIGNATURE}|min_margin=${AUTO_QC_MIN_MARGIN_RATIO:-2.0}"
if [ -s "${AUTO_QC_SCORES}" ] && \
    [ -s "${AUTO_QC_FLAGGED}" ] && \
    [ -s "${AUTO_QC_SUMMARY}" ]; then
  AUTO_QC_SIGNATURE="${AUTO_QC_INPUT_SIGNATURE}|$(auto_qc_output_signature)"
else
  AUTO_QC_SIGNATURE="${AUTO_QC_INPUT_SIGNATURE}|outputs=missing"
fi

if hv_step_needed \
    "${AUTO_QC_DONE}" "${AUTO_QC_SIGNATURE}" \
    "${AUTO_QC_SCORES}" "${AUTO_QC_FLAGGED}" "${AUTO_QC_SUMMARY}"; then
  rm -f "${AUTO_QC_DONE}" "${REVIEW_DONE}" "${STAGE1A_DONE}"
  AUTO_QC=(
    uv run --no-sync python src/resequence/diagnostics/auto_qc_segment_joins.py
    "${RESEQ_PATH}"
    --segments "${SEGMENTS}"
    --order-csv "${GREEDY_ORDER}"
    --detector-metadata "${DETECT_METADATA}"
    --out-dir "${HV_REVIEW_DIR}"
    --max-robust-z "${AUTO_QC_MAX_ROBUST_Z:-15.0}"
    --min-margin-ratio "${AUTO_QC_MIN_MARGIN_RATIO:-2.0}"
    --progress-every-seconds "${AUTO_QC_PROGRESS_EVERY_SECONDS:-300}"
  )
  hv_time_step "auto_qc_segment_joins" "${AUTO_QC[@]}"
  hv_require_file "${AUTO_QC_SCORES}" "Auto-QC completed without join scores."
  hv_require_file "${AUTO_QC_FLAGGED}" "Auto-QC completed without the flagged-join table."
  hv_require_file "${AUTO_QC_SUMMARY}" "Auto-QC completed without its summary."
  AUTO_QC_SIGNATURE="${AUTO_QC_INPUT_SIGNATURE}|$(auto_qc_output_signature)"
  hv_mark_complete "${AUTO_QC_DONE}" "${AUTO_QC_SIGNATURE}"
fi

AUTO_QC_DECISION="$(uv run --no-sync python -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["decision"])' \
  "${AUTO_QC_SUMMARY}")"
case "${AUTO_QC_DECISION}" in
  auto_pass|manual_review_required) ;;
  *)
    echo "Unexpected auto-QC decision: ${AUTO_QC_DECISION}" >&2
    exit 4
    ;;
esac

REVIEW_SIGNATURE="not_required"
QC_ROLL=""
QC_ROLL_CAPTIONS=""
if [ "${AUTO_QC_DECISION}" = "manual_review_required" ]; then
  QC_ROLL="${FLAGGED_QC_ROLL}"
  QC_ROLL_CAPTIONS="${FLAGGED_QC_ROLL%.mp4}.captions.csv"
  REVIEW_FILTER="${AUTO_QC_FLAGGED}"
  # A production approval must cover every flagged join.
  REVIEW_LIMIT=""
elif [ "${WRITE_ALL_QC_ROLLS:-0}" = "1" ]; then
  QC_ROLL="${ALL_QC_ROLL}"
  QC_ROLL_CAPTIONS="${ALL_QC_ROLL%.mp4}.captions.csv"
  REVIEW_FILTER=""
  REVIEW_LIMIT="${JOIN_REVIEW_LIMIT:-}"
fi

if [ -n "${QC_ROLL}" ]; then
  RANKED_FINGERPRINT="$(hv_file_fingerprint "${RANKED_EDGES}")"
  REVIEW_SIGNATURE="v4|segments=${SEGMENTS_FINGERPRINT}|ranked=${RANKED_FINGERPRINT}"
  REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|order=${ORDER_FINGERPRINT}|tool=$(hv_file_fingerprint \
    src/resequence/diagnostics/make_join_review_video.py)"
  REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|auto_qc=$(hv_file_fingerprint "${AUTO_QC_SUMMARY}")"
  if [ -n "${REVIEW_FILTER}" ]; then
    REVIEW_FILTER_FINGERPRINT="$(hv_file_fingerprint "${REVIEW_FILTER}")"
  else
    REVIEW_FILTER_FINGERPRINT="all"
  fi
  REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|filter=${REVIEW_FILTER_FINGERPRINT}"
  REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|limit=${REVIEW_LIMIT:-all}"
  REVIEW_SIGNATURE="${REVIEW_SIGNATURE}|seconds=${JOIN_REVIEW_SECONDS:-default}"

  if hv_step_needed \
      "${REVIEW_DONE}" "${REVIEW_SIGNATURE}" "${QC_ROLL}" "${QC_ROLL_CAPTIONS}"; then
    rm -f "${REVIEW_DONE}" "${STAGE1A_DONE}"
    REVIEW=(
      uv run --no-sync python src/resequence/diagnostics/make_join_review_video.py
      "${RESEQ_PATH}"
      --ranked-edges "${RANKED_EDGES}"
      --segments "${SEGMENTS}"
      --order-csv "${GREEDY_ORDER}"
      --out "${QC_ROLL}"
    )
    if [ -n "${REVIEW_FILTER}" ]; then
      REVIEW+=(--join-filter-csv "${REVIEW_FILTER}")
    fi
    if [ -n "${REVIEW_LIMIT}" ]; then REVIEW+=(--limit "${REVIEW_LIMIT}"); fi
    if [ -n "${JOIN_REVIEW_SECONDS:-}" ]; then
      REVIEW+=(--seconds-each-side "${JOIN_REVIEW_SECONDS}")
    fi
    hv_time_step "join_review_video" "${REVIEW[@]}"
    hv_require_file "${QC_ROLL}" "QC-roll rendering completed without an output video."
    hv_require_file "${QC_ROLL_CAPTIONS}" "QC-roll rendering completed without captions."
    hv_mark_complete "${REVIEW_DONE}" "${REVIEW_SIGNATURE}"
  fi
else
  echo "--- all joins passed automatic QC; no manual-review roll required"
fi

AUTO_QC_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_SUMMARY}")"
AUTO_QC_BUNDLE_FINGERPRINT="$(hv_file_fingerprint "${AUTO_QC_DONE}")"
STAGE1A_GIT_REVISION="$(git rev-parse HEAD)"
STAGE1A_SIGNATURE="v3|cuts_file=$(basename "${CUTS}")|cuts=${CUTS_FINGERPRINT}"
STAGE1A_SIGNATURE="${STAGE1A_SIGNATURE}|cut_review_status=${RESOLVED_CUT_REVIEW_STATUS}"
STAGE1A_SIGNATURE="${STAGE1A_SIGNATURE}|git_revision=${STAGE1A_GIT_REVISION}"
STAGE1A_SIGNATURE="${STAGE1A_SIGNATURE}|segments=${SEGMENTS_SIGNATURE}"
STAGE1A_SIGNATURE="${STAGE1A_SIGNATURE}|order=${ORDER_SIGNATURE}"
STAGE1A_SIGNATURE="${STAGE1A_SIGNATURE}|auto_qc_report=${AUTO_QC_FINGERPRINT}"
STAGE1A_SIGNATURE="${STAGE1A_SIGNATURE}|auto_qc_bundle=${AUTO_QC_BUNDLE_FINGERPRINT}"
STAGE1A_SIGNATURE="${STAGE1A_SIGNATURE}|review=${REVIEW_SIGNATURE}"
hv_mark_complete "${STAGE1A_DONE}" "${STAGE1A_SIGNATURE}"

cat <<EOF

Stage 1a complete for ${RESEQ_KEY}.

  segments         : ${SEGMENTS}
  greedy order     : ${GREEDY_ORDER}
  cut review       : ${RESOLVED_CUT_REVIEW_STATUS}
  auto-QC scores   : ${AUTO_QC_SCORES}
  auto-QC summary  : ${AUTO_QC_SUMMARY}
  auto-QC decision : ${AUTO_QC_DECISION}
EOF

if [ "${AUTO_QC_DECISION}" = "auto_pass" ]; then
  echo
  echo "Every selected join passed the automatic smoothness and ambiguity checks."
  echo "No manual join review is required before Stage 2."
else
  cat <<EOF

Manual review is required for the flagged joins:

  green-flash QC roll: ${QC_ROLL}
  captions           : ${QC_ROLL_CAPTIONS}
  flagged joins      : ${AUTO_QC_FLAGGED}

After inspecting that roll, bind an approval to this exact report and roll:

  uv run --no-sync python src/resequence/diagnostics/approve_manual_join_qc.py create \\
    --summary "${AUTO_QC_SUMMARY}" \\
    --out "${AUTO_QC_APPROVAL}"

Stage 2 will reject a missing or stale approval.
EOF
fi
