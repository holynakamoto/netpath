# netpath product direction

## The product

Netpath is a diagnosis-first network incident investigator for people working
from a shell.

Its core promise is:

> Determine whether the problem is local, on the route, or at the destination;
> identify the likely owner; and preserve the evidence for the next action.

This is deliberately narrower and more useful than being a collection of
networking commands or a prettier traceroute.

## The user and job

The primary user is an SRE, platform engineer, network operator, or support
engineer responding to a live symptom. Their job is not to admire telemetry.
They need to answer:

1. Is there a measurable problem?
2. Where does it begin?
3. Which team or network likely owns it?
4. How confident is that conclusion?
5. What evidence and next action can be handed off?

The expert CLI remains valuable for scripted and protocol-specific work. The
TUI should instead organize those capabilities around an investigation.

## What was wrong with the old TUI

The previous interface behaved as a 12-command launcher:

- only city and ASN path modes had structured native views;
- most workflows streamed colorless CLI output into a generic log;
- a flat selector mixed diagnosis, monitoring, exploration, privileged packet
  capture, probe inventory, and server setup;
- the permanent map and candidate tables displaced verdict, confidence,
  evidence, and recommended action that the engine already produced;
- minimum pane widths required 110 columns, so normal 80-column terminals
  clipped the right pane and hid important data;
- single-letter shortcuts were consumed by focused inputs;
- long-running subprocesses had no owned process handle or Stop action;
- stale field values were silently reinterpreted when changing modes;
- a one-run measurement was called a baseline even though it was a snapshot.

These were product-model problems, not primarily color or spacing problems.

## Information architecture

The workbench has three visible areas.

### Investigate

- **Diagnose**: target-first investigation of the current condition
- **Compare snapshot**: measure now and explain route/performance changes
- **DNS propagation**: group resolver answers and identify divergence

### Explore

- sampled city paths
- sampled ASN paths
- ASN test
- country scan

These views must identify their actual target and vantage. “Best” means the best
sample that entered the destination ASN, not proof that the exact endpoint was
reachable or an authoritative optimal Internet route.

### Tools

- save snapshot
- privacy-bounded local capture
- target discovery
- remote probe coverage
- iperf3 setup

Mutating or privileged tools stay visually separate from read-only diagnosis.

## The investigation model

Every structured run normalizes into one case-shaped result:

- target and mode
- verdict and severity
- confidence
- likely owner or fault domain
- plain-language detail
- strongest evidence
- recommended next action
- path observations
- snapshot deltas
- key metrics
- raw source payload

The interface renders this in the following order:

1. verdict, owner, and confidence;
2. what happened and why netpath believes it;
3. recommended next action;
4. path and measurement details;
5. raw output.

Raw instrumentation remains accessible without becoming the product's opening
answer.

## Measurement planning

A standard endpoint diagnosis is a bounded plan:

1. resolve the target;
2. measure application-edge setup;
3. observe the local path;
4. seek independent remote corroboration;
5. apply deterministic diagnostic rules;
6. produce an evidence-linked verdict.

Future model-guided planning should select conditional follow-ups from the
reported symptom, such as IPv6 comparison, trace fusion, PMTU checks, or a
reviewable capture plan. The model may plan and explain; deterministic probes,
structured evidence, privacy limits, and explicit confirmation remain the
source of truth.

## Incident artifact

`F6` exports a redacted Markdown and JSON bundle containing the normalized
case. This is a core product capability rather than an export afterthought: a
diagnosis becomes useful when it can be reviewed, reproduced, pasted into an
incident, or sent to the suspected owner.

Credential-like keys, bearer values, assignments, and query tokens are
redacted recursively from content and filenames.

## Interaction principles

- Use target-first language and real field labels.
- Reserve green, amber, and red for severity; use cyan for focus and structure.
- Show a reviewable plan before sensitive or elevated work.
- Keep Stop visible while work is active and own spawned process lifecycles.
- Preserve form values per workspace; never reinterpret stale values.
- Use modifier shortcuts so typing in an input never triggers navigation.
- Fit an 80×24 terminal without off-screen panes or hidden controls.
- Prefer topology, ownership, time, and deltas over decorative geography.
- Surface partial failures as evidence instead of discarding the run.

## Product boundary

Netpath should not try to become:

- a full packet analyzer;
- a generic NMS or hosted observability platform;
- a clone of telemetry-first traceroute TUIs;
- an ungrounded AI chat pane;
- a server-management product.

The durable wedge is a local, open, no-agent incident investigator with a
defensible handoff artifact.

## Roadmap

### Shipped in this redesign

- diagnosis-first default launch and grouped navigation
- structured native endpoint, snapshot comparison, DNS, city, and ASN-path
  results
- verdict/owner/confidence/evidence/action hierarchy
- responsive 80-column layout without fixed map panes
- typed DNS record and snapshot selectors
- per-workspace form state
- subprocess ownership and Stop action
- asynchronous capture planning
- Globalping token discovery on the default launch
- redacted Markdown + JSON incident bundles
- sampled-path provenance and snapshot terminology

### Next

- extract remaining CLI orchestration into reusable typed services
- stream real stage events and partial results into the workbench
- make ASN/country/monitor/target/coverage fully native
- add recent and pinned investigations
- render baseline history and route changes as a timeline
- add retry for a failed stage and contextual follow-up probes
- add a compact topology ladder that marks the suspected fault segment

### Later

- symptom-to-plan selection with explicit budgets and stopping conditions
- local case search and replay
- opt-in encrypted team sharing and scheduled watches
- integrations that publish the redacted artifact to incident systems

## Success measures

- time from launch to an actionable fault-domain hypothesis
- percentage of investigations producing a high/medium-confidence owner
- percentage of warning/critical runs exported or copied into a handoff
- retry rate caused by unclear inputs or dependency failures
- successful completion rate at 80×24 over SSH
- false-positive rate for escalations, measured against confirmed incident owner
