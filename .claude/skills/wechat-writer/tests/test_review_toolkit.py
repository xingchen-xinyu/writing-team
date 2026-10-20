#!/usr/bin/env python3
"""Unit tests for review_toolkit.py — critique / directive / feedback modes."""
import importlib.util
import json
import tempfile
import sys
import unittest
from pathlib import Path

# Fix Windows GBK encoding for emoji output
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass

REVIEW_PATH = Path(__file__).resolve().parents[1] / "scripts" / "review_toolkit.py"
SPEC = importlib.util.spec_from_file_location("review_toolkit", REVIEW_PATH)
rt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rt)


class RenderCritiqueTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.out = Path(self._tmpdir.name) / "out"

    def _render(self, data):
        rt.render_critique(data, self.out)
        return self.out.read_text(encoding="utf-8")

    def test_pass_verdict(self):
        text = self._render({
            "source_file": "test.md",
            "meta": {"score": 88, "verdict": "Pass"},
            "critic_persona": "罗永浩",
            "critique_points": {},
            "overall_comment": "很好",
        })
        self.assertIn("🟢", text)
        self.assertIn("Pass", text)
        self.assertIn("88/100", text)

    def test_fail_verdict(self):
        text = self._render({
            "source_file": "test.md",
            "meta": {"score": 45, "verdict": "Fail"},
            "critic_persona": "罗永浩",
            "critique_points": {},
            "overall_comment": "不行",
        })
        self.assertIn("🔴", text)
        self.assertIn("Fail", text)

    def test_needs_work_verdict(self):
        text = self._render({
            "source_file": "test.md",
            "meta": {"score": 65, "verdict": "Needs Work"},
            "critic_persona": "罗永浩",
            "critique_points": {},
            "overall_comment": "还行",
        })
        self.assertIn("🟡", text)
        self.assertIn("Needs Work", text)

    def test_logic_flaws_rendered(self):
        text = self._render({
            "source_file": "test.md",
            "meta": {"score": 50, "verdict": "Needs Work"},
            "critic_persona": "罗永浩",
            "critique_points": {
                "logic_flaws": [
                    {"severity": "High", "point": "P1矛盾"},
                    {"severity": "Medium", "point": "P2跳跃"},
                    {"severity": "Low", "point": "P3微瑕"},
                ]
            },
            "overall_comment": "修",
        })
        self.assertIn("🔥🔥🔥", text)
        self.assertIn("P1矛盾", text)
        self.assertIn("🔥🔥", text)
        self.assertIn("🔥", text)

    def test_ai_smell_rendered(self):
        text = self._render({
            "source_file": "test.md",
            "meta": {"score": 60, "verdict": "Needs Work"},
            "critic_persona": "罗永浩",
            "critique_points": {
                "ai_smell": {"score": 3, "evidence": ["太书面", "转折词过多"]}
            },
            "overall_comment": "去AI味",
        })
        self.assertIn("自然度评分", text)
        self.assertIn("太书面", text)


class RenderDirectiveTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.out = Path(self._tmpdir.name) / "out"

    def _render(self, data):
        rt.render_directive(data, self.out)
        return self.out.read_text(encoding="utf-8")

    def test_directive_without_conflict(self):
        text = self._render({
            "title": "Test",
            "status": "PENDING",
            "conflict_resolution": {"has_conflict": False},
            "critique_summary": [
                {"source": "L3", "point": "缺数据", "action": "补数据"}
            ],
            "editorial_suggestions": [
                {"original": "A", "suggestion": "B"}
            ],
        })
        self.assertIn("综合反馈", text)
        self.assertIn("主编建议", text)
        self.assertIn("缺数据", text)

    def test_directive_with_conflict(self):
        text = self._render({
            "title": "Test",
            "status": "PENDING",
            "conflict_resolution": {"has_conflict": True, "details": "L3和L4冲突"},
            "critique_summary": [],
            "editorial_suggestions": [],
        })
        self.assertIn("冲突待决", text)
        self.assertIn("请星辰裁决", text)


class RenderFeedbackTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.out = Path(self._tmpdir.name) / "out"

    def _render(self, data):
        rt.render_feedback(data, self.out)
        return self.out.read_text(encoding="utf-8")

    def test_feedback_pass(self):
        text = self._render({
            "overall_verdict": "Pass",
            "tests": {
                "click_test": {"decision": "会点", "reason": "标题好奇"},
                "finish_test": {"decision": "会看完", "drop_point": None},
            },
            "best_quote": "金句",
        })
        self.assertIn("🟢", text)
        self.assertIn("会点", text)

    def test_feedback_with_drop_point(self):
        text = self._render({
            "overall_verdict": "Fail",
            "tests": {
                "click_test": {"decision": "不会点", "reason": "没兴趣"},
                "finish_test": {"decision": "流失", "drop_point": "第三段"},
            },
            "best_quote": "",
        })
        self.assertIn("流失点", text)
        self.assertIn("第三段", text)


class OutputNamingTest(unittest.TestCase):
    """Verify output file naming convention from main() logic."""

    def test_critique_output_name(self):
        path = Path("/tmp/_temp_critique.json")
        stem = path.stem
        for p in ['_temp_', 'temp_', 'critique_', 'directive_', 'feedback_']:
            if stem.startswith(p):
                stem = stem[len(p):]
                break
        self.assertEqual(f"[Critique_Report]{stem}.md", "[Critique_Report]critique.md")

    def test_directive_output_name(self):
        path = Path("/tmp/_temp_directive.json")
        stem = path.stem
        for p in ['_temp_', 'temp_', 'critique_', 'directive_', 'feedback_']:
            if stem.startswith(p):
                stem = stem[len(p):]
                break
        self.assertEqual(f"Directive_{stem}.md", "Directive_directive.md")

    def test_feedback_output_name(self):
        path = Path("/tmp/_temp_feedback.json")
        stem = path.stem
        for p in ['_temp_', 'temp_', 'critique_', 'directive_', 'feedback_']:
            if stem.startswith(p):
                stem = stem[len(p):]
                break
        self.assertEqual(f"[User_Feedback]{stem}.md", "[User_Feedback]feedback.md")


if __name__ == "__main__":
    unittest.main()
