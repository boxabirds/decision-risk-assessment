# Decision Risk Audit Report Example

This is a sanitized example report. It preserves aggregate shape and decision-risk interpretation, but removes private project names, source paths, raw snippets, customer context, code, and operational details.

## Method

- Source: local Claude project JSONL logs.
- Scope: 50 most-recent top-level Claude sessions; subagent logs excluded.
- Unit: all explicit conversational choices, then classified by risk-bearing category.
- Attribution: `operator` for user-origin choices, `agent` for assistant-origin choices, `mixed` when a user correction modifies a recent agent proposal.
- Limitation: this is a heuristic candidate extractor; counts are useful for profile direction, not exact ground truth.

## Findings

- Candidate decisions found: 2,397.
- Agent-origin decisions: 2,041 (85.1%).
- Operator-origin decisions: 224 (9.3%).
- Mixed/correction decisions: 132 (5.5%).
- High-risk agent decisions: 112.
- High-risk operator or mixed decisions: 12.

Most common categories:

- `implementation_local`: 636
- `testing_verification`: 613
- `interface`: 292
- `ux_design`: 287
- `diagnosis_remediation`: 262
- `product_scope`: 150
- `process_autonomy`: 102
- `architecture`: 55

## Sanitized Example Patterns

Agent high-risk decisions:

- `agent` `high` `interface`: proposed a repository/file-handling rule that affects how generated assets are stored.
- `agent` `high` `testing_verification`: marked a story complete and summarized tests as sufficient.
- `agent` `high` `product_scope`: assessed whether implemented behavior matched written acceptance criteria.

Operator or mixed high-risk decisions:

- `operator` `high` `architecture`: instructed the agent to categorize customer feedback across UX, prompt, and code changes while using read-only production context.
- `mixed` `high` `interface`: corrected an agent proposal and redirected the implementation toward a simpler manually editable workflow.
- `mixed` `high` `architecture`: paused an agent assumption about where canonical data should live and requested consolidation before implementation.

## Reliability

- The JSONL structure is reliable enough to separate user and assistant messages, ignore tool results, retain message UUIDs, and link decisions back to sessions.
- The useful decision unit is not every line of code. The stable unit is an explicit conversational commitment or constraint that changes approach, behavior, verification, interface, architecture, or remediation.
- Main false positives: assistant progress updates with words like `plan`, `fix`, or `test`; generic summaries of completed work; low-level implementation narration.
- Main false negatives: implicit decisions encoded only in code edits or tool calls; decisions hidden in long file dumps; unspoken defaults accepted by lack of user correction.
- Operator corrections are especially high-signal because they reveal where the agent had made an unacceptable choice and the human reasserted control.

## Recommendation

- Use this analyzer as a triage layer, then manually review high-risk `agent` decisions.
- Add explicit decision checkpoints for architecture, persistent state, public interfaces, production deployment, auth, user-facing UX, and test strategy.
- Track `mixed` decisions as positive control events: they show human involvement, but also identify where the agent initially chose poorly.
- Treat subagent analysis as a separate mode because delegated agent chatter changes attribution semantics.
