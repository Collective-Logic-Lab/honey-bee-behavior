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

Saved endpoint JPEGs first allowed an approximate retrospective check of 414
joins. Every approved successor ranked first. The smallest
runner-up/approved distance ratio was $2.146$, the largest approved direct
distance was $7.871$, and the smallest retained alternative distance was
$13.170$. The original detector cutoff of $z=12$ would flag one approved
Start 04 join, so the initial join-QC screen uses $z=15$ together with the
independent rank and margin requirements.

The subsequent production raw-frame pass scored 420 joins across the same
three videos: 142, 141, and 137 respectively. All 420 selected successors
ranked first and all three videos received `auto_pass`. The smallest exact
runner-up margin was $2.155743$, the largest selected direct distance was
$8.013889$, and the largest exact robust score was $z=12.961261$. Thus the
screen agrees with the human clean labels on these controls, but the controls
still contain no known failed joins.

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

**Revisit when.** Re-estimate the thresholds at the video level after naturally
failed joins have been labeled. Track both the fraction of videos sent to
review and all observed false automatic passes. A higher manual-review rate is
acceptable; evidence of a false automatic pass requires tightening or
replacing the rule.

## HV-R002: Start 01 / Start 02 unattended pipeline pilot

**Status:** v1 failed before media transfer, 2026-07-27

**Decision.** Run one fixed end-to-end pilot on the top panel of side 0 for
Start 01 and Start 02:

- `start01__20190606_190340_side0_top.mp4`, 32,148,912,998 bytes,
  MD5 `40f206a5c1cfb4367d0391038c4013e9`;
- `start02__20190607_184457_side0_top.mp4`, 32,129,316,234 bytes,
  MD5 `1f0c65e5ff5e4a4a91a3c053881e7fb7`.

This pilot intentionally lets Stage 1a consume the unchanged Stage 1 proposal
without human source-cut inspection. That condition is recorded as
`cut_review_status=unreviewed_pilot`; neither logs nor published metadata may
describe those cuts as inspected. Because join QC cannot detect a source cut
that Stage 1 missed inside a segment, an automatic pass remains a pilot result
and not a human-validated inventory result.

Every Stage 1a outcome is published under the isolated prefix
`resequenced/pilots/start01_start02_side0_top_v1/`. A
`manual_review_required` video publishes its compact reports and flagged-join
roll, then stops successfully without booking Stage 2. An `auto_pass` video
continues through archival reassembly and verified upload, followed by the
selected maximum-compression `low` derivative (H.264 CRF 28). Stage 2 tasks run
one at a time because each requests 192 GB and performs heavy scratch I/O.
Local work is likewise isolated under
`artifacts/resequence_pilots/start01_start02_side0_top_v1/`; a bound root marker
prevents a later generic compression or upload command from treating these
unreviewed outputs as ordinary validated work.

**Interpretation.** The two-video run is an integration and yield probe, not a
threshold estimate. The operator's prior expectation is that the present
pipeline will clear more than half but fewer than 80 percent of the inventory
without intervention; this pilot can reveal failure modes but is too small to
estimate that rate.

**Revisit when.** Inspect both filed Stage 1a outcomes and every produced final
video. Promote nothing from the pilot prefix into validated inventory until
the source-cut limitation and any naturally flagged joins have been reviewed.

**Observed v1 outcome.** Revision
`86cad78be24f81590ed47cd639c71ed76551a0f0` launched download array
`59712692`. The cached manifest resolved both requested files, but the first
actual media request failed TLS certificate verification because the tracked
launcher did not carry the Sol CA-bundle setting used by the earlier successful
downloads. The recorded `aftercorr` / `--kill-on-invalid-dep=yes` chain makes
corresponding dependent tasks invalid rather than advancing them. The v1
scratch root, submission record, and empty-or-partial remote prefix remain the
failed-attempt record and must not be deleted or reused.

## HV-R003: Verified archive TLS and Start 01 / Start 02 pilot v2

**Status:** tracked bounded retry prepared, not yet launched, 2026-07-27

**Decision.** Retry the unchanged Start 01 / Start 02 scientific plan as
`start01_start02_side0_top_v2` from a new reviewed Git revision. The v2 parent
pins Sol's readable `/etc/pki/tls/certs/ca-bundle.crt`, and the downloader
builds one verified TLS context containing Python defaults, certifi roots,
available system roots, and any explicitly configured CA bundle. Hostname and
certificate verification remain mandatory.

Before submitting Slurm jobs, v2 refreshes the Edmond manifest and performs a
one-byte ranged GET for each selected media file. Each probe must follow the
same HTTPS redirect path as a download, return HTTP 206 with a
`Content-Range` total equal to the manifest size, and remain HTTPS. This tests
both the manifest and large-media trust paths without downloading the videos
on the login node.

v2 has disjoint local and remote roots:

- `artifacts/resequence_pilots/start01_start02_side0_top_v2/`;
- `resequenced/pilots/start01_start02_side0_top_v2/`.

Only `/scratch/pdressla/honey-bee/downloads/` remains shared. A valid `.part`
file may resume there because the downloader verifies the final byte count and
whole-file archive MD5 before Stage 1 can consume it. The v2 submission record
binds the failed v1 job, prior revision and submission-record hash, TLS trust
file, and retry reason. The validated v1 marker and full submission record are
copied into v2's private `pilot_run/` prefix as retained prior-attempt
evidence. v2 refuses to start while any v1 job ID is still active in `squeue`.
Before each allocation is added to the dependency chain, the parent validates
its numeric Slurm ID and publishes the next append-only
`submission.step00.tsv` through `submission.step04.tsv` snapshot under the
private v2 prefix. After all four IDs are recorded, it publishes and byte-size
verifies the final
`pilot_run/submission.tsv`, so scheduler provenance does not live only on
scratch even if a later stage fails. The download array is submitted held and
released only after that durable record is verified; if filing fails, no pilot
compute advances under an incompletely recorded plan.

**Alternatives considered.** Disabling certificate verification was rejected.
Requeuing v1 with an ad hoc environment override was rejected because it would
change a launched plan without a new attempt record. Deleting v1's submission
record or reusing its artifact prefixes was rejected because it would erase
the distinction between failed and corrected attempts.

**Revisit when.** Revisit the CA selection only if Sol changes its system trust
path or the verified media probe fails. Revisit the scientific plan under the
same conditions recorded in HV-R002 after v2 produces filed outcomes.
