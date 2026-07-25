#!/bin/bash
# Compare the three share-quality profiles on one short resequenced-video clip.
#
#   sbatch src/pipeline/slurm/resequence/compress_resequenced_smoke_test.sh
#
# The smoke test never touches the archival MP4 or uploads anything. It writes
# high, medium, and low H.264 samples under the video's work directory so they
# can be compared before choosing a single profile for full production runs.

#SBATCH --job-name=bees-compress-smoke
#SBATCH --cpus-per-task=8
#SBATCH --mem=8GB
#SBATCH -t 02:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -o slurm.compress-smoke.%j.out
#SBATCH -e slurm.compress-smoke.%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user="pdressla@asu.edu"

set -eu

export HIVE_VIDEO_ROOT=${HIVE_VIDEO_ROOT:-${SLURM_SUBMIT_DIR:-${PWD}}}
SCRIPT_DIR="${HIVE_VIDEO_ROOT}/src/pipeline/slurm/resequence"
source "${SCRIPT_DIR}/common.sh"

# This is deliberately a bounded, visible comparison rather than a production
# run. Edit these settings in the tracked script if a different window is more
# representative of the behavior the collaborator needs to inspect.
SMOKE_LOCATOR=${SMOKE_LOCATOR:-start4_side1_top}
SMOKE_START_SECONDS=${SMOKE_START_SECONDS:-0}
SMOKE_DURATION_SECONDS=${SMOKE_DURATION_SECONDS:-180}
SMOKE_QUALITIES=${SMOKE_QUALITIES:-"high medium low"}
COMPRESS_PRESET=${COMPRESS_PRESET:-medium}

hv_sync_env
hv_require_ffmpeg
hv_resolve "${SMOKE_LOCATOR}"

FINAL_VIDEO="${HV_OUT_DIR}/reseq_${RESEQ_KEY}.mp4"
hv_require_file "${FINAL_VIDEO}" \
  "Stage 2 must finish before compression can be sampled."

SMOKE_DIR="${HV_WORK_DIR}/compression_smoke"
mkdir -p "${SMOKE_DIR}"

for quality in ${SMOKE_QUALITIES}; do
  case "${quality}" in
    high|medium|low) ;;
    *)
      echo "Unknown smoke quality ${quality}; use high, medium, or low." >&2
      exit 2
      ;;
  esac
  OUTPUT="${SMOKE_DIR}/reseq_${RESEQ_KEY}.${quality}.smoke.mp4"
  METADATA="${SMOKE_DIR}/reseq_${RESEQ_KEY}.${quality}.smoke.compression.json"
  hv_time_step "compress_${quality}_smoke" \
    uv run --no-sync python src/resequence/compress_resequenced.py \
      "${FINAL_VIDEO}" \
      --out "${OUTPUT}" \
      --metadata-out "${METADATA}" \
      --quality "${quality}" \
      --preset "${COMPRESS_PRESET}" \
      --start-seconds "${SMOKE_START_SECONDS}" \
      --duration-seconds "${SMOKE_DURATION_SECONDS}" \
      --threads "${SLURM_CPUS_PER_TASK:-8}"
done

echo
echo "Compression smoke test complete for ${RESEQ_KEY}."
echo "Compare the high/medium/low MP4s in: ${SMOKE_DIR}"
echo "The archival resequenced video was not modified or uploaded."
