# Methods decisions

This file records consequential analysis choices used by the video pipeline.
Each entry is intended to make the implemented rule, its evidence, and its
revision triggers auditable.

## HV-R001: Automatic QC for resequenced segment joins

**Status:** provisional production screen, 2026-07-26

**Decision.** Score each join in the proposed complete segment order before
rendering captions or recompressing the video. The score compares the exact
last source frame that the renderer will emit for segment A with the first
source frame of segment B. It uses the same downsampled grayscale mean absolute
pixel difference as `detect_video_discontinuities.py` and normalizes that
distance with the Stage 1 whole-video median and scaled median absolute
deviation:

$$
z_j = \frac{d_j - \operatorname{median}(d)}
{1.4826\,\operatorname{MAD}(d)}.
$$

The direct one-frame feature is deliberately distinct from the 10-frame,
96-pixel trajectory feature used to choose the greedy order. For every selected
successor, the QC tool also scores every still-unused segment start that was
available to the greedy algorithm at that ordering step.

A video is automatically cleared only when every selected join:

1. is the lowest-distance successor under the direct one-frame score;
2. has runner-up distance divided by selected distance at least $2.0$; and
3. has $z_j \leq 15.0$.

Any failed or unscorable join makes the video-level decision
`manual_review_required`. Missing endpoint frames, an incomplete order, and a
zero or invalid detector MAD must never produce an automatic pass. A manual
review decision is a valid QC outcome rather than a software failure.

Before reassembly, the gate revalidates the report's source-video identity and
the content hashes of the segment table, order, and detector metadata. When
manual review is required, the approval records hashes of the report, flagged
table, green-flash MP4, and caption manifest; changing any one makes the
approval stale.

**Initial calibration evidence.** Three green-flash QC rolls were reviewed by
the operator and all their transitions were judged clean:

- `start04_20190609_175013_side1_top`
- `start47_20190731_184423_side0_top`
- `start47_20190731_184423_side1_top`

Saved endpoint JPEGs allowed an approximate retrospective check of 414 joins.
Every approved successor ranked first. The smallest runner-up/approved distance
ratio was $2.146$, the largest approved direct distance was $7.871$, and the
smallest retained alternative distance was $13.170$. The original detector
cutoff of $z=12$ would flag one approved Start 04 join, so the initial join-QC
screen uses $z=15$ together with the independent rank and margin requirements.
These measurements are JPEG-derived approximations; the production tool scores
raw decoded frames and records its exact results.

**Interpretation.** This procedure certifies that the reconstructed boundaries
are visually smooth and unambiguous under the detector feature. It does not
prove absolute chronology: a visually similar but chronologically wrong join
can pass. Ordering remains the trajectory-based reconstruction, and auto-QC is
a conservative shock/ambiguity screen over that result.

**Alternatives considered.**

- Reusing only the ordering cost was rejected because it would validate an
  order with the same feature that selected it.
- Reusing the detector's $z=12$ cutoff without calibration was rejected because
  it flags a known-clean join.
- Scoring the captioned final MP4 was rejected because changing caption text,
  resizing, and H.264 artifacts contaminate the boundary measurement.
- Treating the empirical score as a calibrated probability was rejected because
  the current labeled set contains clean videos but no naturally failed videos.

**Revisit when.** Re-estimate the thresholds at the video level after raw-frame
scores exist for these three controls and after naturally failed joins have
been labeled. Track both the fraction of videos sent to review and all observed
false automatic passes. A higher manual-review rate is acceptable; evidence of
a false automatic pass requires tightening or replacing the rule.
