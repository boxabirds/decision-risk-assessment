# Decision Risk Assessment

Decision Risk Assessment is a small, auditable analyzer for Claude Code project logs. It estimates where software-creation decisions are being made in AI coding sessions: by the human operator, by the coding agent, or by a mixed correction loop.

The goal is not to treat every line of code as a decision. The analyzer looks for explicit conversational choices, constraints, recommendations, corrections, and commitments, then classifies them by software-risk category and rough impact.

## What It Does

- Reads Claude JSONL conversation logs from `~/.claude/projects`.
- Excludes subagent logs by default to avoid inflating agent decision counts.
- Ignores tool-result blobs, local command caveats, continuation summaries, skill injections, and task-notification context.
- Detects candidate decisions in user and assistant turns using transparent heuristics.
- Attributes each candidate as `operator`, `agent`, or `mixed`.
- Classifies each candidate into categories such as architecture, interface, UX design, testing, product scope, and remediation.
- Emits local JSONL, CSV, summary, and audit-report outputs.

Raw outputs are written to `out/`, which is intentionally gitignored because real analysis runs may contain private conversation snippets. The `examples/` directory contains sanitized report examples only.

## Usage

This project uses `uv`; do not install dependencies with `pip`.

```sh
uv run python src/analyze_decisions.py --limit 50 --out-dir out
```

Useful options:

```sh
uv run python src/analyze_decisions.py --root ~/.claude/projects --limit 100 --out-dir out
uv run python src/analyze_decisions.py --include-subagents --limit 50 --out-dir out-with-subagents
```

Run tests:

```sh
uv run python -m unittest discover -s tests
```

## Output Files

- `out/decision-candidates.jsonl`: one candidate decision per line.
- `out/decision-candidates.csv`: spreadsheet-friendly candidate export.
- `out/summary.md`: aggregate counts by origin, speaker, risk band, category, and project.
- `out/audit-report.md`: written audit with representative examples and reliability notes.

## Risk Model

The analyzer treats a useful decision unit as an explicit conversational commitment or constraint that changes approach, behavior, verification, interface, architecture, remediation, or autonomy.

Risk is estimated from:

- User proximity: whether the choice affects visible user or customer behavior.
- State: whether persistent data, storage, migrations, or destructive operations are involved.
- Isolation: whether the choice crosses service, tool, API, deployment, or integration boundaries.
- Reversibility: whether mistakes are easy or hard to reverse.
- Confidence: whether the text includes rationale, evidence, verification, or only an assertion.

This is a triage signal, not ground truth. High-risk agent decisions should be manually reviewed.

## Research Basis

- SEI ATAM: architecture risk often appears around quality attributes, tradeoffs, sensitivity points, and business goals.
- Architecture Decision Records: consequential decisions should record context, choice, rationale, and consequences.
- Empirical architecture-decision research: important decisions are often expressed as solution proposals and information-giving, not only explicit "I decide" statements.

## Privacy

Do not commit raw `out/` files from real runs. They may include private project names, user messages, or code snippets. If you need committed fixtures, create sanitized examples with invented project labels and redacted snippets.

