# Decision Risk Profile From Claude Conversations

## Summary

Build a thin analyzer plus audit report for recent top-level `~/.claude/projects/**/*.jsonl` conversations, excluding subagent logs in v1. The goal is to measure how many explicit decisions are made by the operator versus the coding agent, then classify which decisions carry meaningful software risk.

Research basis:
- SEI ATAM treats important software risk as decisions affecting quality attributes, tradeoffs, sensitivity points, and business goals: https://www.sei.cmu.edu/library/architecture-tradeoff-analysis-method-collection/
- ADR practice defines a decision as a justified design choice with rationale, tradeoffs, and consequences: https://adr.github.io/
- Empirical work shows architecture decisions often appear as solution proposals and information-giving, not only as explicit "I decide" statements: https://arxiv.org/abs/2212.13866
- Architecture decision-making is typically collaborative, so attribution should allow operator, agent, and mixed decision origins: https://arxiv.org/abs/1707.00107

## Decision Model

Use "all explicit choices" as the first-pass unit, then classify importance afterward.

A candidate decision is a conversational span where the speaker:
- Chooses, rejects, recommends, proposes, changes, scopes, prioritizes, diagnoses, or commits to an approach.
- Uses explicit cues such as `decide`, `choice`, `instead`, `recommend`, `should`, `plan`, `approach`, `we will`, `I'll`, `fix`, `root cause`, `tradeoff`, `risk`, `test`, `design`, or `architecture`.
- Gives corrective direction that constrains implementation, e.g. "use glow instead," "it should return bulk results," "that means X, correct?"

Classify each candidate into:
- `architecture`: architecture, framework, service boundary, storage, deployment, integration.
- `interface`: API, CLI, schema, data contract, config, protocol.
- `product_scope`: feature behavior, user value, requirements, acceptance boundaries.
- `ux_design`: layout, interaction, copy, accessibility, visual behavior.
- `testing_verification`: test strategy, validation, acceptance checks, production verification.
- `implementation_local`: file structure, local algorithm, refactor, code organization.
- `diagnosis_remediation`: root cause and chosen fix for a bug or incident.
- `process_autonomy`: delegation, subagents, workflow, permission, review/feedback behavior.

Risk score each decision by impact dimensions:
- `user_proximity`: low/high.
- `state`: low/high for persistent state/data changes.
- `isolation`: low/high for crossing module/service/tool boundaries.
- `reversibility`: easy/hard.
- `confidence`: high/medium/low based on whether rationale and evidence are present.

## Analyzer Plan

Create a read-only script that scans recent top-level JSONL logs.

Implementation behavior:
- Discover recent top-level `.jsonl` files under `~/.claude/projects`, excluding paths containing `/subagents/`.
- Parse `type=user` and `type=assistant` messages, handling both string content and structured content arrays.
- Extract text-only content and retain metadata: project path, session id, timestamp if present, speaker, message uuid, parent uuid.
- Detect candidate decisions using explicit lexical cues plus short imperative/correction patterns from user messages.
- Group adjacent same-speaker decision-bearing messages into one candidate span when they are part of the same conversational turn.
- Attribute origin as `operator`, `agent`, or `mixed` when a user correction directly modifies an agent proposal.
- Emit JSONL/CSV summary with counts by project, speaker, category, risk band, and confidence.
- Include representative snippets, but truncate to avoid dumping huge tool outputs or embedded images.

Important guardrails:
- Ignore tool results and local command caveats as decision sources unless the human explicitly comments on them.
- Treat agent progress narration like "Now I'll read files" as low-value implementation/process noise unless it commits to a consequential approach.
- Treat user corrections as high-signal decisions because they often encode operator control over risk.
- Keep v1 heuristic and auditable; do not pretend it is a perfect classifier.

## Audit Report

Produce a written report from the analyzer plus manual spot-checking.

Report sections:
- `Method`: data scope, sampling window, exclusion of subagents, candidate decision definition.
- `Findings`: operator-vs-agent decision counts, risk-bearing categories, high-risk decisions made by agent without operator confirmation, user correction patterns.
- `Reliability`: false positives, false negatives, ambiguity cases, and whether the decision unit is consistent enough to use as a guidestone.
- `Examples`: 10-20 short examples across projects showing operator decision, agent decision, mixed decision, and non-decision noise.
- `Recommendation`: whether the project needs stronger decision capture, e.g. explicit decision checkpoints, lightweight ADR prompts, or "ask before high-risk choice" rules.

## Test Plan

Validate the analyzer against a manually labeled sample.

Test cases:
- Parses string and array `message.content` formats.
- Excludes `/subagents/` logs unless explicitly enabled.
- Does not count `tool_result` blobs, screenshots, or file dumps as decisions.
- Detects explicit user decisions like "Decision: close all tasks..."
- Detects operator corrections like "use glow instead" as decisions.
- Downgrades agent narration like "Now I'll open the file" as low-risk process noise.
- Correctly attributes agent proposals later overridden by the user as `mixed`.
- Produces stable counts on at least 20 recent top-level sessions.

## Assumptions

- First audit scope is recent top-level conversations across all Claude projects.
- First version counts all explicit choices, then classifies importance afterward.
- Output should include both a thin analyzer prototype plan and an audit report.
- Subagent logs are excluded in v1 because they inflate agent decision counts and need separate attribution semantics.
