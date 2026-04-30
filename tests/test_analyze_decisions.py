import json
import tempfile
import unittest
from pathlib import Path

from src.analyze_decisions import analyze, discover_logs, is_candidate


class AnalyzeDecisionsTest(unittest.TestCase):
    def test_filters_synthetic_context(self):
        ok, reason = is_candidate(
            "user",
            "This session is being continued from a previous conversation. Summary: use SQLite.",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "synthetic_context")

    def test_detects_operator_explicit_decision(self):
        ok, reason = is_candidate(
            "user",
            "Decision: close all tasks that can be closed but return per-task results.",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "user_correction_or_explicit_choice")

    def test_downgrades_assistant_progress_noise(self):
        ok, reason = is_candidate("assistant", "Now I'll open the file and read it.")
        self.assertFalse(ok)
        self.assertEqual(reason, "assistant_progress_noise")

    def test_excludes_subagents_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            top = root / "project" / "a.jsonl"
            sub = root / "project" / "session" / "subagents" / "agent.jsonl"
            top.parent.mkdir(parents=True)
            sub.parent.mkdir(parents=True)
            top.write_text("")
            sub.write_text("")

            logs = discover_logs(root, limit=10, include_subagents=False)

            self.assertEqual(logs, [top])

    def test_analyzes_string_and_array_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "project" / "session.jsonl"
            log.parent.mkdir(parents=True)
            rows = [
                {
                    "type": "user",
                    "sessionId": "s",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "uuid": "u1",
                    "message": {"content": "I want SQLite as the backend."},
                },
                {
                    "type": "assistant",
                    "sessionId": "s",
                    "timestamp": "2026-01-01T00:00:01Z",
                    "uuid": "a1",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "I recommend an API endpoint because it crosses service boundaries.",
                            }
                        ]
                    },
                },
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "content": "Decision: this should not count from tool output.",
                            }
                        ]
                    },
                },
            ]
            log.write_text("\n".join(json.dumps(row) for row in rows))

            candidates = analyze([log])

            self.assertEqual(len(candidates), 2)
            self.assertEqual(candidates[0].origin, "operator")
            self.assertEqual(candidates[1].origin, "agent")


if __name__ == "__main__":
    unittest.main()
