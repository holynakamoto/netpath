# PostHog Self-driving setup report

**Project:** netpath (id: 525573)  
**Date:** 2026-07-23  
**Inbox:** https://us.posthog.com/project/525573/inbox

## Summary

PostHog Self-driving has been configured for netpath. Signal sources for error tracking, session replay, support, and health checks are now active, and a scout troop of 4 agents is scheduled to scan the project daily. Findings will start appearing in the [Self-driving inbox](https://us.posthog.com/project/525573/inbox) within ~30 minutes.

## AI data processing

**Approved.** Organization-level AI data processing consent was granted before this run.

## GitHub

**Already connected** (integration id: 189475, account: `holynakamoto`, connected 2026-07-23). No action needed.

## Products enabled

The `products-enable` MCP tool was unavailable in this version of the server. Products were not flipped via the API.

| Product | Status | Notes |
|---|---|---|
| Session Replay | enabled but inert | netpath is a pure CLI/backend tool — no `posthog-js` reads the server config. Recording requires SDK-level opt-in in client code. |
| Error Tracking | enabled but inert | Same reason: Python SDK exception capture must be configured in code. |
| Support (Conversations) | enabled but inert | Tickets only arrive once an inbound channel (email / inbox / Slack) is connected in PostHog. |

**Follow-up:** If the products-enable toggle is needed, enable Session Replay, Error Tracking, and Conversations from [Project Settings → Products](https://us.posthog.com/project/525573/settings). The server flip is independent of SDK instrumentation.

## Signal sources

| source\_product | source\_type | Action | Notes |
|---|---|---|---|
| `signals_scout` | `cross_source_issue` | **on by default** | Scout gate — scout findings reach the inbox with no config row needed. |
| `health_checks` | `health_issue` | **enabled** (id: 019f9082-57c3-71da-914b-3d0614152cb4) | Always-on: instrumentation issues, proxy gaps, outdated SDKs. |
| `error_tracking` | `issue_created` | **enabled** (id: 019f9082-5ce3-72de-9212-81dbeac862fa) | |
| `error_tracking` | `issue_reopened` | **enabled** (id: 019f9082-6074-7c87-ae0c-a278ad246a41) | |
| `error_tracking` | `issue_spiking` | **enabled** (id: 019f9082-640d-70be-8f7d-0c6064aee28a) | |
| `session_replay` | `session_analysis_cluster` | **enabled** (id: 019f9082-67c0-7611-8128-297567d7e19b) | Default sample rate 10%. Idle until recordings exist. |
| `conversations` | `ticket` | **enabled** (id: 019f9082-6b5b-753b-906b-da7bc298d34e) | Idle until an inbound channel is connected. |

## Connected tools

No external tools were selected. All connected-tool sources skipped.

## Scout troop

**Run budget:** 24 runs/day (early-access default). 0 runs used today, 24 remaining.  
**Banner:** *"Scouts are in early access so daily runs are limited to 24 by default for now, please reach out to team-self-driving@posthog.com if you would like more runs."*

**Active (4):**

| Scout | Reason enabled |
|---|---|
| `signals-scout-general` | Always on — cross-product correlations and surfaces no specialist covers. |
| `signals-scout-product-analytics` | Primary product surface: `diagnostic_run` analytics events. |
| `signals-scout-health-checks` | New/growing integration — catches PostHog setup health issues early. |
| `signals-scout-diagnostic-failures` | Custom scout (see below). |

**Disabled (24):**

| Scout | Reason |
|---|---|
| `signals-scout-error-tracking` | Covered by the native error tracking source (step 4). |
| `signals-scout-session-replay` | Covered by the native session replay source (step 4). |
| `signals-scout-ai-observability` | No `$ai_*` events or LLM SDK in this project. |
| `signals-scout-anomaly-detection` | No dashboards/insights yet to watch for anomalies. |
| `signals-scout-apm` | No OpenTelemetry spans. |
| `signals-scout-conversations` | No active Conversations data yet. |
| `signals-scout-csp-violations` | CLI tool — no browser, no CSP. |
| `signals-scout-customer-analytics` | No group/accounts analytics. |
| `signals-scout-data-pipelines` | No CDP destinations or batch exports. |
| `signals-scout-data-warehouse` | No warehouse sources connected. |
| `signals-scout-experiments` | No active A/B experiments. |
| `signals-scout-feature-flags` | No feature flags in use. |
| `signals-scout-inbox-validation` | Fresh setup — no resolved reports to validate yet. |
| `signals-scout-ingestion-warnings` | No data yet to generate warnings. |
| `signals-scout-insight-alerts` | No insight alerts configured. |
| `signals-scout-logs` | PostHog logs product not in use. |
| `signals-scout-mcp-tool-calls` | No `$mcp_tool_call` events. |
| `signals-scout-observability-gaps` | No event volume yet to find gaps in. |
| `signals-scout-replay-vision` | No Replay Vision scanners. |
| `signals-scout-revenue-analytics` | No payment SDK or revenue data. |
| `signals-scout-skills-store` | Low priority for this project at this time. |
| `signals-scout-surveys` | No surveys — CLI tool. |
| `signals-scout-web-analytics` | CLI tool — no web traffic. |
| `signals-scout-web-vitals` | CLI tool — no browser, no Core Web Vitals. |

Re-enable follow-ups for any of these if you add that surface later.

## Custom scouts

### `signals-scout-diagnostic-failures` — created

**Surface:** `diagnostic_run` events (properties: `check_type` ∈ {"host", "dns"}, `result` ∈ {"success", "failure"}).

**What it watches:** Per-check-type failure rate regressions. Runs daily. Speaks up when one check type's 48-hour failure rate exceeds 2× its 7-day prior baseline AND is above 30% absolute, with at least 10 events in the window.

**Discriminator:** Failure rate per `check_type` in the past 48 h vs the prior 7-day rolling average. Multi-check-type spikes are treated as noise (network/sampling); only isolated single-check-type spikes are reported.

**Why no built-in covers it:** `signals-scout-product-analytics` watches saved funnels — none exist yet. `signals-scout-general` watches cross-product correlations, not per-property event failure rates. Neither tracks the `result` dimension of the diagnostic event stream.

**Noise escape hatch:** Set `emit: false` on this scout's config in PostHog to switch it to dry-run (it runs and logs but writes nothing to the inbox).

**Surfaces considered and ruled out:**

| Surface | Filter that ruled it out |
|---|---|
| Session replay / error tracking | Covered by native sources (step 4) — custom scout would duplicate. |
| Web analytics, CSP, web vitals | Not applicable — CLI tool with no browser frontend. |
| AI/LLM observability | No `$ai_*` events or LLM SDK. |
| Revenue analytics | No payment SDK. |
| Surveys | Not applicable — CLI tool. |
| Telemetry adoption rate | Requires knowing total install base; PostHog can't count users who haven't opted in. |

## Follow-ups

- [ ] **Enable products manually:** Visit [Project Settings](https://us.posthog.com/project/525573/settings) to enable Session Replay, Error Tracking, and Conversations (Support) if the API toggle is available to you — the `products-enable` tool was unavailable in this MCP version.
- [ ] **Connect a Conversations channel:** Conversations tickets only reach the inbox once an inbound channel (email / inbox / Slack) is connected in PostHog. Connect one at [Integrations Settings](https://us.posthog.com/project/525573/settings/environment-integrations).
- [ ] **Enable Python exception capture:** The error tracking source is now active, but the Python PostHog SDK must be configured to capture exceptions in code before any issues flow in. See the PostHog Python SDK docs.
- [ ] **Enable session replay in SDK:** Session replay is a browser feature — not applicable to netpath's CLI. If you add a web frontend or Electron wrapper, configure session recording there.
- [ ] **Re-enable scouts for new surfaces:** If you add feature flags, A/B experiments, surveys, LLM features, or revenue data, re-enable the matching specialist scout in [PostHog → Inbox → Scout settings](https://us.posthog.com/project/525573/inbox).

## What happens next

The scout coordinator picks up fresh configs within ~30 minutes. Each of the 4 enabled scouts runs once per day (4 runs/day total, well within the 24/day budget). Findings cluster into reports in the [Self-driving inbox](https://us.posthog.com/project/525573/inbox). Immediately-actionable reports can kick off coding tasks automatically once a GitHub connection is confirmed (it is — `holynakamoto`).

The `signals-scout-diagnostic-failures` custom scout will close out empty until `diagnostic_run` telemetry starts flowing. To start generating events, run `netpath telemetry on` and set `NETPATH_TELEMETRY_KEY` to your PostHog project token (`phc_vEkygRpsYegjnezAi7rKfoYrs28sDPE7GMFQhViMxj9i`).
