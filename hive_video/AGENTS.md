# AGENTS_scientific.md

## Purpose

This is a reusable working contract for scientific-programming repositories.
Adapt it to the project, place the resulting contract at the repository root as
`AGENTS.md`, and keep project-specific scientific decisions in `METHODS.md`.

The objective is not production-software sophistication. The objective is a
scientific procedure that another person can read, inspect, run, and criticize.
Prefer direct code, explicit state, reproducible launches, informative
failures, and auditable artifacts.

Use one root `AGENTS.md` wherever possible. Do not create parallel instruction
files, hidden agent directories, or repository-local agent caches merely to
support a particular editor or coding agent.

## Order of Work

Before proposing or making changes:

1. Read the root `AGENTS.md` completely. Do not begin by searching hidden
   agent-specific directories.
2. Inspect the repository status, current branch, and existing uncommitted
   changes. Treat changes not made for the current task as belonging to the
   researcher.
3. Read the project overview, `METHODS.md`, relevant tracked configurations and
   launch scripts, then the source and tests governing the path in question.
4. Inspect existing plans, manifests, and representative results when the
   request depends on prior experimental behavior.
5. Separate established method, observed evidence, interpretation, and an
   unresolved scientific choice.
6. Give a consequential unresolved choice a stable decision entry in
   `METHODS.md` before implementing it.
7. Implement the smallest complete and readable path, verify it in proportion
   to its scientific risk, and report exactly what was and was not run.

A tracked nested `AGENTS.md` is justified only when a subtree has genuinely
different requirements that cannot be stated clearly in the root contract.
Apply instructions from the root toward the target, with the nearest tracked
file taking precedence. Do not use `.agents/`, `.agent/`, `.codex/`,
`.claude/`, editor settings, or caches as a second source of project policy.

## Scientific Code

- Prefer clear, conventional scientific programming and generally accepted
  packages. Use NumPy, SciPy, pandas, scikit-learn, or another established
  package when its method is appropriate and can be stated plainly in a
  Methods section or appendix.
- Do not reimplement a standard estimator merely to avoid a dependency.
  Conversely, do not add a large dependency to replace a short, transparent
  calculation.
- Keep a small readable reference implementation of scientifically important
  operations. Check every optimized, vectorized, parallel, accelerator, or
  approximate implementation against it on deterministic fixtures before
  trusting results.
- Prefer a few direct functions and plain data structures. Use a standard
  abstraction such as a scikit-learn `Pipeline` when it makes the method more
  explicit. Avoid custom frameworks, registries, factories, plugin systems,
  inheritance trees, and generalized backends without a concrete second use.
- A little visible duplication is better than an abstraction that conceals the
  scientific procedure.
- Align code names with mathematical notation when the correspondence is real
  and documented, such as `x_t`, `x_next`, `delta_v`, `mu`, or
  `period_lambda`. Prefer descriptive names such as `neighbor_count`,
  `sample_count`, and `output_dir` when shorthand would be opaque.
- Document array shapes, dtypes, units, indexing and bit ordering, coordinate
  conventions, missing-data semantics, and the correspondence between symbols
  and code names.
- Comments should explain scientific meaning, assumptions, provenance, or
  invariants. Do not narrate obvious syntax.
- Make randomness explicit. Record the generator, seed, sampling procedure,
  and the point at which independent streams are derived.
- Treat numerical warnings and convergence failures as errors unless their
  handling has been reviewed and recorded in `METHODS.md`.

## Growing and Refactoring Pipelines

Build complicated systems gradually enough that the whole procedure remains
comprehensible:

1. Start with one direct, end-to-end reference path on a tiny deterministic
   fixture.
2. Characterize the current behavior with focused tests and an inspectable
   artifact before changing structure.
3. Introduce one coherent seam at a time—for example, simulation, validation,
   serialization, scheduling, or transfer—and keep the data crossing that seam
   explicit.
4. Compare the old and new paths on the same inputs. Require exact equivalence
   where the method permits it; otherwise define the tolerance and rationale in
   advance.
5. Profile before optimizing. Preserve separate measurements for
   initialization, steady-state compute, validation, serialization, storage,
   and transfer.
6. Add multiprocessing, cluster scheduling, or acceleration only after the
   single-process reference path is correct and measured.
7. Remove superseded code only after the replacement is verified. Do not leave
   two ambiguous production paths or a permanent compatibility framework.

Keep scientific logic, artifact I/O, and operational orchestration visibly
separable, but do not turn that separation into a framework. A reader should be
able to follow a sample from explicit input, through each transformation, to
validated output without consulting a registry or reconstructing hidden state.

Prefer inspectable intermediate artifacts when they mark scientifically useful
boundaries. Name their schema and provenance, validate them on write and read,
and checksum material outputs. Do not add intermediates merely because an
orchestration layer makes them convenient.

## Explicit Inputs and Outputs

- Do not provide implicit defaults for experimental or scientifically
  consequential parameters, random seeds, datasets, output locations, run IDs,
  artifact prefixes, overwrite behavior, or backup requirements.
- Require consequential settings in a tracked configuration. Scheduled
  experiments and calibrations use the zero-argument launch contract below.
- Defaults are acceptable for inconsequential interface settings when they
  improve usability. Preserve every resolved setting in the run manifest.
- For third-party estimators, record the package version and the complete
  resolved parameter set; do not assume library defaults remain stable.
- Validate the complete configuration before compute begins. Materialize the
  resolved configuration and planned outputs without silently substituting a
  path, implementation, device, dataset, or parameter.
- Refuse to write into a completed or unexpected nonempty output directory.
  Overwrite and restart-from-scratch are distinct, explicit operations.
- Never emit placeholder, empty, synthetic, or default scientific results in
  response to missing input or failed computation.

## Errors and Failure Semantics

- Fail loudly and near the source. Error text should identify the failed
  condition, expected value, observed value, and relevant run, unit, sample, or
  path.
- Use ordinary exceptions such as `ValueError`, `FileNotFoundError`, and
  `RuntimeError`. Do not create a custom exception hierarchy without a
  demonstrated need.
- Do not use `assert` for configuration, input, or data validation; assertions
  can be disabled.
- Do not silently catch exceptions, drop records, skip inputs, replace invalid
  values, retry operations, or fall back to another implementation or device.
- A top-level handler may record failure context and preserve validated partial
  artifacts, but it must retain the original nonzero outcome.
- Scientific terminal states such as extinction, recurrence, censoring, or an
  operator stop are explicit data statuses. Software failures remain failures.
- A failed unit may preserve an error manifest and validated partial output,
  but it is not complete. Aggregation must verify expected coverage, schemas,
  and checksums and refuse incomplete inputs.
- If a retry is scientifically and operationally justified, make it an
  explicit method decision. Give each attempt its own record and retain failed
  attempts.

## Method and Reproduction Record

`METHODS.md` is the living scientific and reproduction decision record. Before
implementing a consequential ambiguous choice, give it a stable decision ID and
record:

- the question and decision;
- its status and date;
- the rationale and evidence;
- plausible alternatives;
- likely sensitivity;
- affected configurations and runs; and
- the condition under which the decision should be revisited.

Supersede decisions explicitly after runs depend on them. Do not silently edit
history into apparent certainty.

Every run must preserve its resolved configuration, seeds, code revision,
dependency versions and lockfile identity, environment, hardware, thread
settings, data selection, timestamps, and local and remote artifact locations.
Keep raw results auditable and derive summaries or training views from
identified run-level artifacts.

Predefine reproduction criteria before expensive sweeps. Comparable results
require comparable data, axes, metrics, termination rules, and regimes—not
merely similar plots.

## MacBook, Sol, and Hugging Face

Treat the three surfaces as having distinct roles.

### MacBook: source, review, and analysis

- Use the MacBook checkout for readable development, documentation, focused
  tests, tiny deterministic runs, plan construction, review, and analysis.
- Git is the authority for code, configurations, launchers, tests, and method
  records. Commit dependency locks and small deterministic fixtures.
- Keep generated corpora, checkpoints, and bulk metrics outside the source
  checkout. Do not make an untracked local result the only record of a
  scientific run.
- Review the exact revision and immutable plan before sending work to Sol.

### Sol (`sol.asu.edu`): scheduled compute

- Keep a clean clone of the reviewed revision on Sol. Do not develop divergent,
  untracked scientific code directly on the cluster.
- Use login nodes for synchronization, planning, submission, monitoring, and
  light inspection only. Run substantive compute through Slurm.
- Prepare and pin the environment before the sweep, for example with
  `uv sync --frozen`. Concurrent jobs must not install packages or mutate a
  shared checkout or environment.
- Use cluster scratch for per-run staging and compute output. Give concurrent
  units disjoint directories and treat scratch as working storage, never the
  sole durable copy.
- Record the actual Slurm job IDs, nodes, environment, and observed resources
  as run outputs.
- For this researcher's account, monitor the full job surface with
  `squeue -u pdressla --iterate=10`, then use `sacct` for completed-job resource
  and outcome records.

### Private Hugging Face storage: durable large artifacts

- Use an explicitly approved private Hugging Face Bucket or repository for
  finalized corpora, checkpoints, bulk metrics, run exports, and backup
  verification records.
- Every project launcher must name the exact private destination and a
  run-specific immutable prefix in the `peterdresslar` namespace.
- Prepare and pin the `hf` client before scheduled work. Preflight its version,
  authenticated identity, destination privacy, and target-prefix state.
- Credentials are never committed, printed, embedded in launch commands, or
  written to manifests and logs.
- Construct and inspect an allowlisted upload plan. Sync only finalized
  artifacts, do not use routine remote deletion, and do not silently retry.
- Record the remote listing or version after upload. Download into a fresh
  verification directory and compare the expected manifest and checksums before
  declaring backup complete.
- Hugging Face storage is the authority for large run artifacts, not for source
  code. Git remains the authority for the program and method.

The ordinary flow is:

```text
MacBook reviewed code and plan
    -> Git revision
    -> clean Sol checkout and Slurm compute
    -> finalized scratch export
    -> private Hugging Face destination
    -> fresh checksum verification
    -> selective retrieval to the MacBook for analysis
```

An ad hoc `scp` copy can help with diagnosis, but it is not a substitute for
the named, verified artifact path.

## Reproducible Scheduled Launches

- Every scheduled experiment or calibration has one tracked, versioned parent
  launch script with a zero-argument invocation, such as
  `bash generations/submit_example_v1.sh`.
- Do not permit invocation-time positional arguments, flags, environment
  assignments, or shell prefixes to select consequential settings.
- Make the parent script the visible source of every operational input:
  configuration, run and plan IDs, revision, interpreter, account, partition,
  QoS, nodes, tasks, CPUs, GPUs, memory, wall time, concurrency, thread limits,
  scratch, logs, output and control paths, restart policy, and backup mode and
  destination.
- A parent may derive its repository root from its tracked location and pass
  resolved values internally to `sbatch` or a worker. Reject inherited
  `SBATCH_*` variables and analogous environment overrides.
- A worker that bypasses the parent must fail rather than launch with partial
  settings.
- Changing a launch setting requires a reviewed tracked edit. Once a plan is
  launched, any revision receives a new script or configuration version, plan
  ID, and run ID. Do not use `sbatch` command-line overrides to revise a
  recorded experiment.
- Scheduler-assigned identifiers and observed node metadata are outputs, not
  launch inputs.
- Credentials are the only exception to embedding resolved values. The parent
  must still name and preflight the authentication mechanism and destination.

## Staged Experiment Operations

Scale through explicit stages:

1. plan-only validation;
2. minimal local and scheduled smoke tests;
3. wall-time, memory, and storage calibration;
4. forced-failure and restart or finalization test;
5. bounded pilot;
6. authorized production run or sweep.

A plan-only stage validates and writes the complete immutable plan, including
stable unit IDs, seeds, configurations, array bounds, and expected outputs. It
does not allocate expensive hardware, construct the full dataset, or transfer
bulk artifacts.

Treat calibration as data. Measure initialization and warm-up separately from
steady-state compute, validation or recurrence overhead, serialization,
checkpointing, backup, peak memory, and storage. Use measured results—not
intuition alone—to choose resources, wall time, checkpoint cadence, and
concurrency.

Use the same direct experiment entry point locally and under Slurm. Bound
processes and numerical-library threads to the requested allocation, and cap
array concurrency for responsible fair-share use.

## State, Finalization, and Transfer

- Give each unit a disjoint staging directory. Avoid shared mutable state by
  construction.
- Persist validated unit results as they finish. Write manifests, state, and
  completion markers through a temporary path followed by atomic replacement.
- Resume only from validated checkpoints. Skip only units whose exact expected
  outputs and checksums are complete.
- Long units emit a timestamped heartbeat at an explicit interval with the unit
  ID, completed and planned work, throughput, and latest checkpoint state.
- Use one visible file-based operator control with a small vocabulary recorded
  in `METHODS.md`. Keep a requested action sticky and check it at a declared
  scientifically atomic boundary.
- Use one straightforward finalization path for success, censoring, operator
  stop, failure, and scheduler termination. Preserve the latest valid state and
  the original outcome.
- Record computation, export, upload, and verification as separate outcomes.
  Backup success must never convert failed science into a successful run.

For long production runs, prefer separate compute and transfer allocations.
Let compute use its scientific wall-time budget, then invoke a dependent
finalizer or transfer job with resources appropriate to checksum, compression,
network transfer, and fresh verification. The transfer job must run after both
successful and failed compute so that it can preserve valid state, while
retaining the compute outcome independently.

## Git, Local State, and Worktrees

- Keep GitHub focused on code, small fixtures, tracked configurations, tests,
  manifests, and documentation. Store bulk generated artifacts in the approved
  private artifact store.
- Preserve unrelated dirty changes. Never discard, overwrite, stage, or commit
  another person's work merely to obtain a clean tree.
- Prefer the existing checkout and an ordinary reviewed branch.
- Treat worktrees as a last resort. Use one only for genuinely simultaneous or
  incompatible branch work that cannot be handled safely in the current
  checkout—not to evade a dirty tree or avoid understanding existing changes.
- Before creating a worktree, inspect existing worktrees, branches, ownership,
  and target paths. Keep it outside the repository's source tree and document
  why it is needed.
- Do not remove a worktree or branch, or delete its unmerged contents, without
  explicit approval.
- Scheduled runs still require a clean, immutable checkout at the reviewed
  revision; a worktree does not weaken that rule.
- Do not commit local editor metadata, agent state, caches, credentials, or
  machine-specific paths. Use the single root `AGENTS.md` as the shared agent
  contract and keep tool-specific state outside the repository when possible.
- Do not ignore dependency lockfiles. They are scientific provenance.

## Verification

- Add focused tests for scientific invariants, explicit failures, and the
  changed path. Prefer small deterministic fixtures whose expected states can
  be inspected directly.
- Check optimized implementations against the reference implementation on
  supported shapes and boundary cases.
- Test missing parameters, unexpected shapes, nonempty outputs, corrupted
  checkpoints, forced interruption, incomplete aggregation, and failed backup
  verification when those paths are relevant.
- Test the direct entry point before its wrapper, and test the wrapper before a
  scheduled launch.
- Do not launch costly compute, training, uploads, or large downloads without
  explicit authorization.
- Report the commands run, their outcomes, and important checks not run.

## Writing and Communication

- Lead with findings, decisions, and concrete evidence. Distinguish reproduced
  results from interpretation.
- Surface uncertainty, failed assumptions, warnings, and source discrepancies.
  Do not smooth them into confident prose.
- Preserve harmless authorial idiosyncrasies. Change them only when they harm
  factual accuracy, clarity, or reproducibility.
- Questions, placeholders, contrasts, and rejected alternatives in internal
  discussion should guide reasoning; finished prose should normally state the
  resolved fact directly.
- Use dollar-delimited LaTeX: `$...$` inline and `$$...$$` for display math.
- Keep edits narrow and leave unrelated prose, code, formatting, and metadata
  alone.
- Ask before destructive operations, broad refactors, substantial compute or
  transfer expenditure, publication, or changes to scientific scope.

## Publication and Security

- Do not publish data, checkpoints, results, or external artifacts without
  explicit approval.
- Never commit secrets. Treat `.gitignore` as noise control, not as a security
  boundary.
- Record private artifact locations without recording credentials.
- Before any public release, review the intended files, manifests, licensing,
  privacy, and scientific claims as a separate authorized step.
