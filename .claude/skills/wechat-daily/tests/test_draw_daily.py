#!/usr/bin/env python3
import importlib.util
import sys
import unittest
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "draw_daily.py"
SPEC = importlib.util.spec_from_file_location("wechat_daily_draw_daily", SCRIPT_PATH)
draw_daily = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(draw_daily)


class ResolveDirectorScriptsDirTest(unittest.TestCase):
    def test_points_to_wechat_director_scripts(self):
        result = draw_daily.resolve_director_scripts_dir()
        self.assertEqual(result.name, "scripts")
        self.assertEqual(result.parent.name, "wechat-director")


class GetSidebarColorTest(unittest.TestCase):
    def test_returns_daily_amber(self):
        self.assertEqual(draw_daily.get_sidebar_color(), "#D4A854")


class BuildSimpleModeCommandTest(unittest.TestCase):
    def test_builds_expected_argv(self):
        cmd = draw_daily.build_simple_mode_command(
            cover_path="To-be-used/_daily_scratch/img/cover-main.jpg",
            brief_path="To-be-used/_daily_scratch/Storyboard.md",
        )
        self.assertEqual(cmd[0], "python")
        self.assertIn("visualize.py", cmd[1])
        self.assertIn("--mode", cmd)
        self.assertIn("simple", cmd)
        self.assertIn("--brief", cmd)
        self.assertIn("To-be-used/_daily_scratch/Storyboard.md", cmd)
        self.assertIn("--cover", cmd)
        self.assertIn("To-be-used/_daily_scratch/img/cover-main.jpg", cmd)


if __name__ == "__main__":
    unittest.main()
