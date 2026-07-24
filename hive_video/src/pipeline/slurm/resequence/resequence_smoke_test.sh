#!/bin/bash
# Timing probe for the resequencing pipeline.
#
#   sbatch src/pipeline/slurm/resequence/resequence_smoke_test.sh
#
# Runs the full pipeline over a bounded slice of one real video and reports
# separate detection, ordering, review, and reassembly timings. The cut review
# uses the single-jump proposal automatically for timing only; it is not a
# substitute for the manual production gate.
#
# Nothing here writes into the real work directory; everything lands under
# <work dir>/smoke so it cannot be mistaken for a production artifact.
#
#   SMOKE_FRAMES   frames to decode before stopping (default 20000)
#   SMOKE_LOCATOR  which video to probe (default start4_side1_top)

#SBATCH --job-name=bees-reseq-smoke
#SBATCH --cpus-per-task=8
#SBATCH --mem=32GB
#SBATCH -t 02:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.reseq-smoke.%j.out
#SBATCH -e slurm.reseq-smoke.%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

# Slurm executes a copy of this script from /var/spool/slurmd, so $0 does not
# identify the checkout. The documented submission command runs from the
# hive_video root, which Slurm records in SLURM_SUBMIT_DIR.
export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

SMOKE_FRAMES=${SMOKE_FRAMES:-20000}
SMOKE_LOCATOR=${SMOKE_LOCATOR:-start4_side1_top}

hv_sync_env
hv_resolve "${SMOKE_LOCATOR}"

hv_require_file "${RESEQ_PATH}" \
  "Run download_raw_array.sh for ${SMOKE_LOCATOR} before smoke testing."

SMOKE_DIR="${HV_WORK_DIR}/smoke"
rm -rf "${SMOKE_DIR}"
mkdir -p "${SMOKE_DIR}"
export HV_TIMING_LOG="${SMOKE_DIR}/timings.tsv"
: >"${HV_TIMING_LOG}"

echo "=================================================="
echo "node          : $(hostname)"
echo "cpus per task : ${SLURM_CPUS_PER_TASK:-unknown}"
echo "video         : ${RESEQ_PATH}"
echo "size          : $(du -h "${RESEQ_PATH}" | cut -f1)"
echo "ffmpeg        : $(command -v ffmpeg || echo MISSING)"
echo "ffprobe       : $(command -v ffprobe || echo MISSING)"
echo "=================================================="

# Estimate the total frame count without a full -count_frames scan.
PROBE=$(ffprobe -v error -select_streams v:0 \
  -show_entries stream=avg_frame_rate,nb_frames,duration \
  -of default=noprint_wrappers=1 "${RESEQ_PATH}")
echo "${PROBE}"

TOTAL_FRAMES=$(printf '%s\n' "${PROBE}" | awk -F= '
  $1 == "duration" { duration = $2 }
  $1 == "nb_frames" && $2 ~ /^[0-9]+$/ && $2 > 0 { frames = $2 }
  $1 == "avg_frame_rate" { split($2, r, "/"); if (r[2] > 0) fps = r[1] / r[2] }
  END {
    if (frames > 0) { printf "%d", frames }
    else if (duration > 0 && fps > 0) { printf "%d", duration * fps }
    else { printf "0" }
  }')
echo "estimated total frames: ${TOTAL_FRAMES}"
echo

hv_time_step "detect_${SMOKE_FRAMES}_frames" \
  uv run --no-sync python src/resequence/detect_video_discontinuities.py \
    "${RESEQ_PATH}" \
    --out "${SMOKE_DIR}/qc" \
    --max-frames "${SMOKE_FRAMES}" \
    --top-n "${TOP_N:-400}" \
    --progress-every-seconds "${PROGRESS_EVERY_SECONDS:-60}"

hv_time_step "summarize_jump_events" \
  uv run --no-sync python src/resequence/summarize_jump_events.py \
    --candidates "${SMOKE_DIR}/qc/candidates.csv" \
    --out "${SMOKE_DIR}/qc/jump_events.csv"

hv_time_step "prepare_cut_review" \
  uv run --no-sync python src/resequence/prepare_cut_review.py \
    --events "${SMOKE_DIR}/qc/jump_events.csv" \
    --out "${SMOKE_DIR}/qc/cut_review.smoke.csv"

hv_time_step "build_segments" \
  uv run --no-sync python src/resequence/build_segments_from_jumps.py \
    "${RESEQ_PATH}" \
    --jumps "${SMOKE_DIR}/qc/cut_review.smoke.csv" \
    --input-kind cut-review \
    --frame-count "${SMOKE_FRAMES}" \
    --out "${SMOKE_DIR}/segments/segments.csv"

hv_time_step "order_segments" \
  uv run --no-sync python src/resequence/order_video_segments.py \
    --segments "${SMOKE_DIR}/segments/segments.csv" \
    --out "${SMOKE_DIR}/order" \
    --window-frames 10 \
    --signature trajectory \
    --top-k 10

hv_time_step "join_review_video" \
  uv run --no-sync python src/resequence/diagnostics/make_join_review_video.py \
    "${RESEQ_PATH}" \
    --ranked-edges "${SMOKE_DIR}/order/ranked_edges.csv" \
    --segments "${SMOKE_DIR}/segments/segments.csv" \
    --order-csv "${SMOKE_DIR}/order/greedy_order.csv" \
    --out "${SMOKE_DIR}/review/join_review_greedy_order.mp4" \
    --seconds-each-side 0.5

hv_time_step "reassemble_${SMOKE_FRAMES}_frames" \
  uv run --no-sync python src/resequence/reassemble_video_from_segments.py \
    --segments "${SMOKE_DIR}/segments/segments.csv" \
    --ranked-edges "${SMOKE_DIR}/order/ranked_edges.csv" \
    --order-csv "${SMOKE_DIR}/order/greedy_order.csv" \
    --require-complete-order \
    --out "${SMOKE_DIR}/output/reseq_smoke.mp4" \
    --safeword-file "${SMOKE_DIR}/.safeword" \
    --segment-chunk-size 2

DETECT_SECONDS=$(awk -F'\t' '$1 ~ /^detect_/ { print $2 }' "${HV_TIMING_LOG}")
REASSEMBLE_SECONDS=$(awk -F'\t' '$1 ~ /^reassemble_/ { print $2 }' "${HV_TIMING_LOG}")

echo
echo "=================================================="
echo "Smoke test results for ${RESEQ_KEY}"
echo "=================================================="
column -t -s "$(printf '\t')" "${HV_TIMING_LOG}" 2>/dev/null || cat "${HV_TIMING_LOG}"
echo

awk -v secs="${DETECT_SECONDS:-0}" -v frames="${SMOKE_FRAMES}" -v total="${TOTAL_FRAMES}" '
BEGIN {
  if (secs <= 0 || total <= 0) {
    print "Not enough information to project a full run.";
    exit
  }
  rate = frames / secs;
  projected = total / rate;
  printf "detection rate        : %.1f frames/s\n", rate;
  printf "projected full detect : %.1f hours (%d frames)\n", projected / 3600.0, total;
  printf "\n";
  printf "Suggested stage 1 wall clock: %.0f hours\n", (projected / 3600.0) * 2.0 + 1;
  printf "  (2x the detection projection plus an hour.)\n";
}'

awk -v secs="${REASSEMBLE_SECONDS:-0}" -v frames="${SMOKE_FRAMES}" -v total="${TOTAL_FRAMES}" '
BEGIN {
  if (secs <= 0 || total <= 0) {
    print "Not enough information to project reassembly.";
    exit
  }
  rate = frames / secs;
  projected = total / rate;
  printf "reassembly rate        : %.1f frames/s\n", rate;
  printf "projected reassembly   : %.1f hours (%d frames)\n", projected / 3600.0, total;
  printf "Suggested stage 2 floor: %.0f hours\n", (projected / 3600.0) * 2.0 + 2;
  printf "  (2x reassembly plus two hours; add the observed ordering and review times.)\n";
}'

echo
echo "Report these numbers back before launching the full arrays."
echo "Smoke artifacts: ${SMOKE_DIR}"
