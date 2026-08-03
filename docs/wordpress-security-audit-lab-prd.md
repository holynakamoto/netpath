# Product Requirements Document: WordPress Security Audit Lab

## 1. Purpose

Build a reproducible, isolated environment for authorized security research against current WordPress Core. The lab must support source review, manual proof-of-concept validation, regression testing, and preparation of private reports for the WordPress HackerOne program.

The initial research goal is to identify a reproducible vulnerability that crosses a real privilege boundary. Remote code execution is a high-value research direction, not a completion requirement and not a reason to overstate theoretical findings.

## 2. Safety and authorization boundary

- Test only the local Docker environment or another system for which the researcher has explicit written authorization.
- Do not scan, probe, modify, or exploit public WordPress installations.
- Prefer source analysis and narrowly scoped local requests over broad automated scanning.
- Do not publish candidate details, exploit code, screenshots, or reports before coordinated disclosure permits it.
- Manually validate all AI-generated hypotheses.
- Disclose AI assistance and its extent in any HackerOne report.
- Preserve an evidence trail containing the exact source revision, configuration, request, response, and reproduction steps.

## 3. Targets and disclosure routes

- Lab foundation: WordPress Core `trunk` from `WordPress/wordpress-develop`.
- Initial research track: the latest eligible release of a locally installable WordPress plugin or theme.
- Secondary research track: WordPress Core after the plugin workflow is proven.
- Record the exact Core commit and plugin/theme archive version before every audit cycle.
- Preferred initial disclosure route: Wordfence Intelligence Bug Bounty Program.
- Parallel eligibility check: Patchstack Bug Bounty Program. Do not submit the same finding to two programs unless both programs explicitly permit it and the ownership/disclosure terms are compatible.
- Core disclosure route: `https://hackerone.com/wordpress`.
- Official guidance: `https://make.wordpress.org/core/handbook/testing/reporting-security-vulnerabilities/`.
- Plugins are excluded unless explicitly listed as in-scope assets by the program.

### 3.1 Current ecosystem eligibility baseline

Verify these rules again immediately before selecting a target and immediately before submission:

- Wordfence high-threat classes such as unauthenticated or Subscriber-level RCE, arbitrary PHP file operations, arbitrary options update, authentication bypass to administrator, and privilege escalation to administrator are broadly eligible from 25 active installations, subject to repository and asset exclusions.
- Wordfence stored XSS and SQL injection are broadly eligible from 500 active installations when exploitable by an unauthenticated or low-level account.
- A new standard Wordfence researcher generally needs at least 50,000 active installations for vulnerability classes outside those special categories.
- Patchstack generally requires at least 1,000 active installations, the latest component release, a publicly obtainable component, and a latest release no older than three years.
- Prefer free WordPress.org components with at least 50,000 active installations for the first audit. This keeps more vulnerability classes eligible and makes the target easy for triage teams to reproduce.
- Exclude any product with its own bounty program until that program's rules have been reviewed and selected as the disclosure route.

## 4. Functional requirements

### 4.1 Source workspace

The lab must:

- Keep WordPress research separate from the existing NetPath application.
- Use `/Users/nickmoore/netpath/.security-research/wordpress-develop` as the WordPress source directory.
- Retain Git metadata for exact revision tracking and duplicate/fix analysis. Research must not rely on private or unauthorized source material.
- Avoid committing generated dependencies, runtime state, credentials, or candidate vulnerability details to the NetPath repository.

### 4.2 Runtime

Use the official WordPress development environment and its supported toolchain:

- Docker Desktop or a compatible container runtime, running locally.
- Node.js 20.x.
- npm 10.x.
- Repository dependencies installed from the lockfile.
- WordPress, PHP, and MySQL supplied by the official Docker environment.
- Local web endpoint: `http://localhost:8889`.
- Default lab administrator credentials: `admin` / `password`; these are local-only test credentials.

### 4.3 Installation workflow

From the WordPress source directory, run:

```bash
npm install
npm run build:dev
npm run env:start
npm run env:install
```

For stricter dependency reproducibility, use `npm ci` when the checked-out lockfile and local environment support it. Do not silently regenerate the lockfile during setup.

### 4.4 Verification

Setup is complete only when all of the following pass:

- Docker reports the WordPress development containers as running and healthy enough to serve requests.
- `http://localhost:8889/` returns a successful WordPress response.
- `http://localhost:8889/wp-json/` returns valid REST API JSON.
- Administrator login works locally.
- `npm run env:cli -- core version` returns the installed WordPress version.
- A small representative PHP test can execute through the official test runner.
- The exact Git commit, Node version, npm version, Docker version, and container configuration are captured in an audit manifest.

### 4.5 Research identities

Create local test users representing realistic trust boundaries:

- Anonymous visitor: no credentials.
- Subscriber: lowest authenticated role.
- Contributor and Author: content creation without administrative control.
- Editor: privileged content manager.
- Administrator: impact target and control account.

Use unique local-only passwords and never reuse personal credentials.

### 4.6 Observability and evidence

The lab must make it possible to capture:

- HTTP request and response pairs without secrets belonging to real users.
- WordPress, PHP, web server, and MySQL container logs.
- Database state before and after a test.
- Minimal regression tests for confirmed behavior.
- A candidate register recording source, sink, attacker prerequisites, expected impact, observed impact, and falsification attempts.

Candidate materials should live outside public Git history, under `.security-research/evidence/`, with restrictive local handling.

## 5. Audit workflow

### Phase A: Attack-surface mapping

Inventory attacker-controlled entry points and their permission callbacks:

- REST API routes, including batch and nested dispatch.
- AJAX actions for authenticated and unauthenticated users.
- XML-RPC methods where a concrete security impact exists.
- Upload, media, archive, image, and filesystem processing.
- Authentication, password reset, application passwords, and session handling.
- Post metadata, options, object cache, cron, and background tasks.
- Serialization/deserialization and dynamic callback behavior.
- SQL query construction and differences between scalar and array handling.
- Multisite-specific privilege boundaries.

### Phase B: Candidate triage

Every candidate must answer:

1. What input can the attacker control?
2. What exact code path carries it to the sensitive operation?
3. What authentication or role is required?
4. Does the default or common configuration expose it?
5. What capability does the attacker gain that they did not already possess?
6. Can it be reproduced twice from a clean state?
7. What benign explanation or existing security control could invalidate it?

Reject scanner-only output, theoretical sinks without reachability, self-XSS, administrator-equivalent behavior, public-data disclosure, low-impact version/path disclosure, denial of service, and other program exclusions.

### Phase C: Local validation

- Reproduce against a clean installation at the recorded commit.
- Use the least privileged attacker account possible.
- Demonstrate only the minimum impact required to prove the boundary crossing.
- Never use persistence, destructive payloads, reverse shells, or data unrelated to the proof.
- Add a focused regression test when feasible.
- Re-test after resetting the environment.

### Phase D: Duplicate and report preparation

- Check public advisories and HackerOne Hacktivity without revealing the candidate.
- Confirm the behavior remains unpatched at the current supported revision.
- Prepare a private report containing summary, severity rationale, affected revision/version, prerequisites, exact reproduction, expected versus actual result, impact, evidence, and remediation direction.
- State that Codex/AI assisted with source analysis or drafting and that the researcher manually reproduced and reviewed the report.
- Submit only after the human account owner reviews and explicitly approves the final report.

## 6. Non-functional requirements

- Reproducible: another authorized researcher can rebuild the lab from this PRD.
- Isolated: services bind only to local interfaces unless intentionally changed and reviewed.
- Recoverable: runtime state can be stopped and recreated using official environment commands.
- Traceable: every finding identifies its exact commit and environment.
- Minimal-impact: validation proves the issue without unnecessary code execution or data access.
- Confidential: unpatched findings remain outside public repositories and public collaboration channels.

## 7. Operational commands

```bash
# Start an existing lab
npm run env:start

# Stop the lab without deleting its data
npm run env:stop

# Run WP-CLI inside the lab
npm run env:cli -- core version

# Run PHP tests
npm run test:php

# Destructively reset lab containers and data
npm run env:reset
```

`env:reset` is destructive and must not be run until evidence and any needed database state have been preserved.

## 8. Deliverables

- Working local WordPress site and REST API.
- Recorded environment/audit manifest.
- Test accounts for each relevant privilege level.
- Attack-surface inventory.
- Candidate register with rejected hypotheses as well as viable candidates.
- Reproduction artifacts and regression test for any confirmed vulnerability.
- Human-reviewed private HackerOne submission draft.

## 9. Acceptance criteria

The lab is ready for research when:

1. All setup and verification checks in section 4 pass.
2. The target is reachable only as an authorized local test system.
3. Test roles are available.
4. Logs and request evidence can be captured.
5. The source revision and environment versions are recorded.
6. The researcher has reviewed the HackerOne scope and agrees not to test public systems.

The research project is ready for submission only when a candidate is reproducible, crosses a real privilege boundary, survives adversarial review, is not obviously excluded or duplicated, and has been reviewed by the human submitter.

## 10. Known constraints

- A finding or bounty is not guaranteed.
- The program currently reports long bounty turnaround times.
- WordPress requires severe, reproducible impact and rejects unverified automated findings.
- RCE may require a multi-bug chain; each link must independently satisfy its stated prerequisites.
- The historical exploit-broker headline is not the expected HackerOne payout.
