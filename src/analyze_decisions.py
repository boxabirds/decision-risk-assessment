#!/usr/bin/env python3
"""Analyze explicit decision risk in Claude JSONL project logs.

This is intentionally heuristic and auditable. It reads conversation logs, emits
candidate decisions, and summarizes operator-vs-agent decision distribution.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DECISION_RE = re.compile(
    r"\b("
    r"decid(?:e|ed|ing|es|ion|ions)?|"
    r"choose|chosen|choice|"
    r"instead|rather than|"
    r"recommend|suggest|proposal|propose|"
    r"should|must|need(?:s)? to|have to|"
    r"approach|strategy|plan|"
    r"we(?:'| wi)ll|i(?:'| wi)ll|i(?:'| a)m going to|"
    r"fix(?:ing)?|change(?:d|s)?|switch(?:ed)?|"
    r"root cause|diagnosis|diagnose|"
    r"trade-?off|risk|"
    r"test(?:ing)?|verify|validation|"
    r"design|architecture|schema|api|interface|"
    r"scope|requirement|acceptance|"
    r"reject|avoid|prefer"
    r")\b",
    re.IGNORECASE,
)

USER_CORRECTION_RE = re.compile(
    r"(?:\b("
    r"not .{0,40} but|"
    r"should (?:be|show|return|use|include)|"
    r"use .{0,60} instead|"
    r"i want|"
    r"don't|do not|"
    r"that's wrong|"
    r"you missed|"
    r"fix this|"
    r"change (?:it|this|that)"
    r")\b|decision:)",
    re.IGNORECASE,
)

PROGRESS_NOISE_RE = re.compile(
    r"^(?:"
    r"now i(?:'| wi)ll|"
    r"let me|"
    r"i(?:'| wi)ll (?:read|inspect|open|check|look|run|search|list)|"
    r"next i(?:'| wi)ll|"
    r"refresh\.|"
    r"done\."
    r")",
    re.IGNORECASE,
)

LOCAL_COMMAND_CAVEAT_RE = re.compile(
    r"<local-command-caveat>|<command-name>|<local-command-stdout>",
    re.IGNORECASE,
)

SYNTHETIC_CONTEXT_RE = re.compile(
    r"^(?:"
    r"this session is being continued from a previous conversation|"
    r"base directory for this skill:|"
    r"<task-notification>|"
    r"<system-reminder>|"
    r"<command-name>|"
    r"<local-command-stdout>|"
    r"<local-command-caveat>"
    r")",
    re.IGNORECASE,
)

CATEGORIES = {
    "architecture": re.compile(
        r"\b(architecture|framework|service|worker|database|db|storage|queue|deployment|deploy|infra|integration|oauth|auth|hosting|cloudflare|wrangler)\b",
        re.IGNORECASE,
    ),
    "interface": re.compile(
        r"\b(api|cli|schema|contract|config|protocol|endpoint|action|argument|parameter|json|jsonl|csv|input|output|return)\b",
        re.IGNORECASE,
    ),
    "product_scope": re.compile(
        r"\b(feature|brief|requirement|scope|user story|customer|user value|acceptance|behavior|behaviour|product|story)\b",
        re.IGNORECASE,
    ),
    "ux_design": re.compile(
        r"\b(ux|ui|layout|interaction|copy|accessibility|mobile|desktop|visual|screen|click|scroll|label|color|glow|arc|text)\b",
        re.IGNORECASE,
    ),
    "testing_verification": re.compile(
        r"\b(test|testing|verify|verification|validate|validation|coverage|e2e|unit|integration|qa|check|assert|production)\b",
        re.IGNORECASE,
    ),
    "diagnosis_remediation": re.compile(
        r"\b(root cause|diagnosis|diagnose|bug|fix|issue|broken|failure|error|malformed|404|remediation|regression)\b",
        re.IGNORECASE,
    ),
    "process_autonomy": re.compile(
        r"\b(agent|subagent|delegate|delegation|permission|review|workflow|operator|human|autonomy|prompt|feedback|plan mode)\b",
        re.IGNORECASE,
    ),
    "implementation_local": re.compile(
        r"\b(file|function|module|component|refactor|algorithm|css|html|script|class|method|implementation|code)\b",
        re.IGNORECASE,
    ),
}

HIGH_STATE_RE = re.compile(
    r"\b(database|db|d1|kv|storage|persistent|migration|write|delete|archive|trash|state|user data|pii)\b",
    re.IGNORECASE,
)
HIGH_ISOLATION_RE = re.compile(
    r"\b(api|service|worker|queue|database|github|cloudflare|oauth|integration|deployment|subagent|remote|production|wrangler)\b",
    re.IGNORECASE,
)
HIGH_USER_RE = re.compile(
    r"\b(user|customer|public|ui|ux|screen|page|error message|onboarding|feature|app|browser|desktop|mobile)\b",
    re.IGNORECASE,
)
HARD_REVERSIBILITY_RE = re.compile(
    r"\b(migration|schema|api contract|auth|oauth|delete|remove|production|deployment|data|public|breaking|irreversible|legal)\b",
    re.IGNORECASE,
)
RATIONALE_RE = re.compile(r"\b(because|so that|therefore|as a result|trade-?off|risk|means|why|rationale|evidence|confirmed)\b", re.IGNORECASE)


@dataclass
class Candidate:
    project: str
    session_id: str
    path: str
    timestamp: str
    speaker: str
    origin: str
    category: str
    risk_band: str
    confidence: str
    user_proximity: str
    state: str
    isolation: str
    reversibility: str
    uuid: str
    parent_uuid: str
    snippet: str
    reason: str


def parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def discover_logs(root: Path, limit: int, include_subagents: bool) -> list[Path]:
    files = []
    for path in root.rglob("*.jsonl"):
        if not include_subagents and "subagents" in path.parts:
            continue
        try:
            files.append((path.stat().st_mtime, path))
        except OSError:
            continue
    return [path for _, path in sorted(files, reverse=True)[:limit]]


def content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(parts)


def iter_messages(path: Path) -> Iterable[dict[str, str]]:
    with path.open(errors="ignore") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("type") not in {"user", "assistant"}:
                continue
            message = item.get("message") or {}
            text = content_text(message.get("content"))
            if not text.strip():
                continue
            yield {
                "path": str(path),
                "line": str(line_number),
                "project": path.parent.name,
                "session_id": str(item.get("sessionId") or path.stem),
                "timestamp": str(item.get("timestamp") or ""),
                "speaker": str(item.get("type") or ""),
                "uuid": str(item.get("uuid") or ""),
                "parent_uuid": str(item.get("parentUuid") or ""),
                "text": text.strip(),
            }


def is_candidate(speaker: str, text: str) -> tuple[bool, str]:
    compact = " ".join(text.split())
    if SYNTHETIC_CONTEXT_RE.match(compact):
        return False, "synthetic_context"
    if LOCAL_COMMAND_CAVEAT_RE.search(compact):
        return False, "local_command_caveat"
    if speaker == "user" and USER_CORRECTION_RE.search(compact):
        return True, "user_correction_or_explicit_choice"
    if not DECISION_RE.search(compact):
        return False, "no_decision_cue"
    if speaker == "assistant" and PROGRESS_NOISE_RE.match(compact) and not risk_terms(compact):
        return False, "assistant_progress_noise"
    return True, "lexical_decision_cue"


def risk_terms(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in (HIGH_STATE_RE, HIGH_ISOLATION_RE, HIGH_USER_RE, HARD_REVERSIBILITY_RE)
    )


def classify_category(text: str) -> str:
    matches = []
    for category, pattern in CATEGORIES.items():
        count = len(pattern.findall(text))
        if count:
            matches.append((count, category))
    if not matches:
        return "implementation_local"
    return sorted(matches, reverse=True)[0][1]


def risk_profile(text: str, category: str) -> tuple[str, str, str, str, str, str]:
    user = "high" if HIGH_USER_RE.search(text) else "low"
    state = "high" if HIGH_STATE_RE.search(text) else "low"
    isolation = "high" if HIGH_ISOLATION_RE.search(text) else "low"
    reversibility = "hard" if HARD_REVERSIBILITY_RE.search(text) else "easy"

    score = 0
    score += user == "high"
    score += state == "high"
    score += isolation == "high"
    score += reversibility == "hard"
    if category in {"architecture", "interface", "testing_verification", "diagnosis_remediation"}:
        score += 1

    if score >= 4:
        risk_band = "high"
    elif score >= 2:
        risk_band = "medium"
    else:
        risk_band = "low"

    if RATIONALE_RE.search(text):
        confidence = "medium"
        if len(text) > 240 and re.search(r"\b(confirmed|verified|evidence|tested|because)\b", text, re.IGNORECASE):
            confidence = "high"
    else:
        confidence = "low"

    return risk_band, confidence, user, state, isolation, reversibility


def origin_for(index: int, messages: list[dict[str, str]], candidates: set[int]) -> str:
    speaker = messages[index]["speaker"]
    if speaker == "assistant":
        return "agent"
    text = messages[index]["text"]
    if USER_CORRECTION_RE.search(text):
        for previous in range(max(0, index - 4), index):
            if previous in candidates and messages[previous]["speaker"] == "assistant":
                return "mixed"
    return "operator"


def snippet(text: str, limit: int = 280) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "..."


def analyze(paths: list[Path]) -> list[Candidate]:
    all_candidates = []
    for path in paths:
        messages = list(iter_messages(path))
        candidate_indices = set()
        reasons = {}
        for index, message in enumerate(messages):
            ok, reason = is_candidate(message["speaker"], message["text"])
            if ok:
                candidate_indices.add(index)
                reasons[index] = reason

        for index in sorted(candidate_indices):
            message = messages[index]
            text = message["text"]
            category = classify_category(text)
            risk_band, confidence, user, state, isolation, reversibility = risk_profile(text, category)
            all_candidates.append(
                Candidate(
                    project=message["project"],
                    session_id=message["session_id"],
                    path=message["path"],
                    timestamp=message["timestamp"],
                    speaker=message["speaker"],
                    origin=origin_for(index, messages, candidate_indices),
                    category=category,
                    risk_band=risk_band,
                    confidence=confidence,
                    user_proximity=user,
                    state=state,
                    isolation=isolation,
                    reversibility=reversibility,
                    uuid=message["uuid"],
                    parent_uuid=message["parent_uuid"],
                    snippet=snippet(text),
                    reason=reasons[index],
                )
            )
    return all_candidates


def write_jsonl(path: Path, candidates: list[Candidate]) -> None:
    with path.open("w") as handle:
        for candidate in candidates:
            handle.write(json.dumps(asdict(candidate), ensure_ascii=False) + "\n")


def write_csv(path: Path, candidates: list[Candidate]) -> None:
    if not candidates:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(candidates[0]).keys()))
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(asdict(candidate))


def summarize(candidates: list[Candidate], log_count: int) -> str:
    by_origin = Counter(c.origin for c in candidates)
    by_speaker = Counter(c.speaker for c in candidates)
    by_category = Counter(c.category for c in candidates)
    by_risk = Counter(c.risk_band for c in candidates)
    by_project = Counter(c.project for c in candidates)

    operator = by_origin["operator"] + by_origin["mixed"]
    agent = by_origin["agent"]
    total = len(candidates)
    agent_share = (agent / total * 100) if total else 0.0

    lines = [
        "# Decision Risk Analysis Summary",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Logs analyzed: {log_count}",
        f"Candidate decisions: {total}",
        f"Agent-origin decisions: {agent} ({agent_share:.1f}%)",
        f"Operator or mixed decisions: {operator} ({(operator / total * 100) if total else 0:.1f}%)",
        "",
        "## Origin",
        "",
    ]
    for key, value in by_origin.most_common():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Speaker", ""])
    for key, value in by_speaker.most_common():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Risk Band", ""])
    for key, value in by_risk.most_common():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Category", ""])
    for key, value in by_category.most_common():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Top Projects", ""])
    for key, value in by_project.most_common(10):
        lines.append(f"- `{key}`: {value}")
    return "\n".join(lines) + "\n"


def write_audit(path: Path, candidates: list[Candidate], log_count: int, source_root: Path) -> None:
    by_origin = Counter(c.origin for c in candidates)
    by_category = Counter(c.category for c in candidates)
    by_risk_origin = Counter((c.risk_band, c.origin) for c in candidates)
    total = len(candidates)
    agent = by_origin["agent"]
    operator = by_origin["operator"]
    mixed = by_origin["mixed"]

    high_agent = [c for c in candidates if c.origin == "agent" and c.risk_band == "high"]
    high_operator = [c for c in candidates if c.origin in {"operator", "mixed"} and c.risk_band == "high"]
    corrections = [c for c in candidates if c.origin == "mixed" or c.reason == "user_correction_or_explicit_choice"]

    def examples(items: list[Candidate], count: int = 5) -> list[str]:
        lines = []
        for item in items[:count]:
            lines.append(
                f"- `{item.origin}` `{item.risk_band}` `{item.category}` in `{item.project}`: {item.snippet}"
            )
        return lines or ["- No examples found in this sample."]

    content = [
        "# Decision Risk Audit Report",
        "",
        "## Method",
        "",
        f"- Source: `{source_root}`.",
        f"- Scope: {log_count} most-recent top-level Claude JSONL logs; `/subagents/` logs excluded.",
        "- Unit: all explicit conversational choices, then classified by risk-bearing category.",
        "- Attribution: `operator` for user-origin choices, `agent` for assistant-origin choices, `mixed` when a user correction modifies a recent agent proposal.",
        "- Limitation: this is a heuristic candidate extractor; counts are useful for profile direction, not exact ground truth.",
        "",
        "## Findings",
        "",
        f"- Candidate decisions found: {total}.",
        f"- Agent-origin decisions: {agent} ({(agent / total * 100) if total else 0:.1f}%).",
        f"- Operator-origin decisions: {operator} ({(operator / total * 100) if total else 0:.1f}%).",
        f"- Mixed/correction decisions: {mixed} ({(mixed / total * 100) if total else 0:.1f}%).",
        f"- High-risk agent decisions: {len(high_agent)}.",
        f"- High-risk operator or mixed decisions: {len(high_operator)}.",
        "",
        "Most common categories:",
        "",
    ]
    for category, value in by_category.most_common(8):
        content.append(f"- `{category}`: {value}")
    content.extend(
        [
            "",
            "Risk by origin:",
            "",
        ]
    )
    for (risk, origin), value in sorted(by_risk_origin.items()):
        content.append(f"- `{risk}` / `{origin}`: {value}")

    content.extend(
        [
            "",
            "## Representative Examples",
            "",
            "Agent high-risk decisions:",
            "",
            *examples(high_agent, 6),
            "",
            "Operator or mixed high-risk decisions:",
            "",
            *examples(high_operator, 6),
            "",
            "User corrections and explicit operator choices:",
            "",
            *examples(corrections, 8),
            "",
            "## Reliability",
            "",
            "- The JSONL structure is reliable enough to separate user and assistant messages, ignore tool results, retain message UUIDs, and link decisions back to sessions.",
            "- The useful decision unit is not every line of code. The stable unit is an explicit conversational commitment or constraint that changes approach, behavior, verification, interface, architecture, or remediation.",
            "- Main false positives: assistant progress updates with words like `plan`, `fix`, or `test`; generic summaries of completed work; low-level implementation narration.",
            "- Main false negatives: implicit decisions encoded only in code edits or tool calls; decisions hidden in long file dumps; unspoken defaults accepted by lack of user correction.",
            "- Operator corrections are especially high-signal because they reveal where the agent had made an unacceptable choice and the human reasserted control.",
            "",
            "## Recommendation",
            "",
            "- Use this analyzer as a triage layer, then manually review high-risk `agent` decisions.",
            "- Add an explicit decision checkpoint rule for high-risk categories: architecture, persistent state, public interfaces, production deployment, auth, user-facing UX, and test strategy.",
            "- Track `mixed` decisions as positive control events: they show human involvement, but also identify areas where the agent initially chose poorly.",
            "- Treat subagent analysis as v2 with separate attribution semantics; otherwise agent decision counts will be inflated by delegated internal chatter.",
        ]
    )
    path.write_text("\n".join(content) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / ".claude/projects")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--include-subagents", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    logs = discover_logs(args.root, args.limit, args.include_subagents)
    candidates = analyze(logs)

    write_jsonl(args.out_dir / "decision-candidates.jsonl", candidates)
    write_csv(args.out_dir / "decision-candidates.csv", candidates)
    (args.out_dir / "summary.md").write_text(summarize(candidates, len(logs)))
    write_audit(args.out_dir / "audit-report.md", candidates, len(logs), args.root)

    print(summarize(candidates, len(logs)))
    print(f"Wrote {args.out_dir / 'decision-candidates.jsonl'}")
    print(f"Wrote {args.out_dir / 'decision-candidates.csv'}")
    print(f"Wrote {args.out_dir / 'summary.md'}")
    print(f"Wrote {args.out_dir / 'audit-report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
