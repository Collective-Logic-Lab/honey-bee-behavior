#!/bin/bash
# Timing probe for the resequencing pipeline.
#
#   sbatch src/resequence/slurm/resequence_smoke_test.sh
#
# Runs discontinuity detection over a bounded slice of one real video, times it,
# and projects the full-length cost so the wall clocks in the stage scripts can
# be set from measurement rather than guesswork. The stage script defaults
# (24h for stage 1, 48h for stage 2) are placeholders until this has run.
#
# Nothing here writes into the real work directory; everything lands under
# <work dir>/smoke so it cannot be mistaken for a production artifact.
#
#   SMOKE_FRAMES   frames to decode before stopping (default 20000)
#   SMOKE_LOCATOR  which video to probe (default day4_side1_top)

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

source "$(dirname "$(readlink -f "$0")")/common.sh"

SMOKE_FRAMES=${SMOKE_FRAMES:-20000}
SMOKE_LOCATOR=${SMOKE_LOCATOR:-day4_side1_top}

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
    --progress-every-seconds "${PROGRESS_EVERY_SECONDS:-60}"

if [ -f "${SMOKE_DIR}/qc/candidates.csv" ]; then
  hv_time_step "summarize_jump_events" \
    uv run --no-sync python src/resequence/summarize_jump_events.py \
      --candidates "${SMOKE_DIR}/qc/candidates.csv" \
      --out "${SMOKE_DIR}/qc/jump_events.csv"
fi

DETECT_SECONDS=$(awk -F'\t' '$1 ~ /^detect_/ { print $2 }' "${HV_TIMING_LOG}")

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
  printf "  (2x the detection projection plus an hour; ordering and the join\n";
  printf "   review video are small next to detection, but the segment count\n";
  printf "   drives ordering cost, so re-check after a real run.)\n";
}'

echo
echo "Report these numbers back before launching the full arrays."
echo "Smoke artifacts: ${SMOKE_DIR}"
