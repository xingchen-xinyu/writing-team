#!/usr/bin/env python3
"""Tests for archive_daily.py v2.0.0."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "archive_daily.py"
SPEC = importlib.util.spec_from_file_location("wechat_daily_archive_daily", SCRIPT_PATH)
archive_daily = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive_daily)


class SanitizeTest(unittest.TestCase):
    def test_sanitize_filename_strips_ascii_specials(self):
        self.assertEqual(archive_daily.sanitize_filename('a:b"c'), "abc")

    def test_sanitize_filename_keeps_fullwidth_colon(self):
        self.assertEqual(
            archive_daily.sanitize_filename("生活中的美好：帮邻居收快递"),
            "生活中的美好：帮邻居收快递",
        )


class CopyImagesTest(unittest.TestCase):
    def test_copies_supported_image_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "workspace"
            src = Path(tmp) / "src_img"
            src.mkdir(parents=True)
            (src / "a.jpg").write_bytes(b"fake")
            (src / "notes.txt").write_text("ignore me", encoding="utf-8")

            result = archive_daily.copy_images(str(src), workspace_root)

            dest = workspace_root / "published" / "img" / "a.jpg"
            self.assertTrue(dest.exists())
            self.assertIsNotNone(result)
            self.assertFalse(
                (workspace_root / "published" / "img" / "notes.txt").exists()
            )

    def test_skips_when_no_img_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "workspace"
            result = archive_daily.copy_images("", workspace_root)
            self.assertIsNone(result)

    def test_skips_existing_file_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "workspace"
            dest_dir = workspace_root / "published" / "img"
            dest_dir.mkdir(parents=True)
            (dest_dir / "a.jpg").write_bytes(b"old")

            src = Path(tmp) / "src_img"
            src.mkdir(parents=True)
            (src / "a.jpg").write_bytes(b"new")

            archive_daily.copy_images(str(src), workspace_root)

            self.assertEqual((dest_dir / "a.jpg").read_bytes(), b"old")


class UpdateDailyIndexTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.skill_root = Path(self._tmpdir.name) / "wechat-daily"
        (self.skill_root / "knowledge").mkdir(parents=True)

    def test_creates_index_when_missing(self):
        with mock.patch.object(archive_daily, "get_skill_root", return_value=self.skill_root):
            archive_daily.update_daily_index(
                "20260718_测试", "生活中的美好：测试", ["日行一善"], "摘要"
            )
        index_path = self.skill_root / "knowledge" / "daily_article_index.md"
        content = index_path.read_text(encoding="utf-8")
        self.assertIn("[[20260718_测试]]", content)
        self.assertIn("日行一善", content)
        self.assertIn("2026-07-18", content)

    def test_appends_without_duplicating(self):
        with mock.patch.object(archive_daily, "get_skill_root", return_value=self.skill_root):
            archive_daily.update_daily_index("20260718_测试", "T", [], "")
            archive_daily.update_daily_index("20260718_测试", "T", [], "")
        index_path = self.skill_root / "knowledge" / "daily_article_index.md"
        content = index_path.read_text(encoding="utf-8")
        self.assertEqual(content.count("[[20260718_测试]]"), 1)


class ProcessDailyIntegrationTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.workspace = Path(self._tmpdir.name) / "workspace"
        self.workspace.mkdir(parents=True)
        self.skill_root = Path(self._tmpdir.name) / "wechat-daily"
        (self.skill_root / "knowledge").mkdir(parents=True)
        self.json_dir = Path(self._tmpdir.name) / "project"
        self.json_dir.mkdir(parents=True)

    def test_process_daily_writes_markdown_and_index(self):
        data = {
            "title": "生活中的美好：帮邻居收快递",
            "date": "2026-07-18",
            "body_markdown": "早上帮邻居把快递收进屋。",
            "excerpt": "顺手的事，心里暖了一下午。",
            "tags": ["日行一善"],
        }
        with mock.patch.object(archive_daily, "get_skill_root", return_value=self.skill_root):
            with mock.patch.object(archive_daily, "load_bio_header", return_value=None):
                with mock.patch.object(archive_daily, "load_bio_footer", return_value=None):
                    archive_daily.process_daily(data, self.json_dir, self.workspace,
                                                no_move=True, skip_html=True)

        published_md = self.workspace / "published" / "20260718_生活中的美好：帮邻居收快递.md"
        self.assertTrue(published_md.exists())

        content = published_md.read_text(encoding="utf-8")
        self.assertIn("早上帮邻居把快递收进屋。", content)
        self.assertIn('title: "生活中的美好：帮邻居收快递"', content)

        index_content = (self.skill_root / "knowledge" / "daily_article_index.md").read_text(encoding="utf-8")
        self.assertIn("[[20260718_生活中的美好：帮邻居收快递]]", index_content)

    def test_process_daily_requires_title(self):
        data = {"title": "", "body_markdown": "x"}
        with mock.patch.object(archive_daily, "get_skill_root", return_value=self.skill_root):
            with mock.patch.object(archive_daily, "load_bio_footer", return_value=None):
                with self.assertRaises(SystemExit):
                    archive_daily.process_daily(data, self.json_dir, self.workspace,
                                                no_move=True, skip_html=True)

    def test_process_daily_requires_body(self):
        data = {"title": "生活中的美好：空", "body_markdown": ""}
        with mock.patch.object(archive_daily, "get_skill_root", return_value=self.skill_root):
            with mock.patch.object(archive_daily, "load_bio_footer", return_value=None):
                with self.assertRaises(SystemExit):
                    archive_daily.process_daily(data, self.json_dir, self.workspace,
                                                no_move=True, skip_html=True)

    def test_process_daily_appends_bio_footer(self):
        data = {
            "title": "生活中的美好：测试",
            "body_markdown": "今天很好。",
            "date": "2026-07-19",
        }
        with mock.patch.object(archive_daily, "get_skill_root", return_value=self.skill_root):
            with mock.patch.object(archive_daily, "load_bio_header", return_value=None):
                with mock.patch.object(archive_daily, "load_bio_footer", return_value="---\n我是星辰。\n编码人生.lab"):
                    archive_daily.process_daily(data, self.json_dir, self.workspace,
                                                no_move=True, skip_html=True)

        published_md = self.workspace / "published" / "20260719_生活中的美好：测试.md"
        content = published_md.read_text(encoding="utf-8")
        self.assertIn("我是星辰", content)
        self.assertIn("编码人生.lab", content)

    def test_process_daily_handles_name_collision(self):
        data = {
            "title": "生活中的美好：同一天",
            "body_markdown": "第二篇。",
            "date": "2026-07-19",
        }
        # Pre-create a file with the same name
        existing = self.workspace / "published" / "20260719_生活中的美好：同一天.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("old", encoding="utf-8")

        with mock.patch.object(archive_daily, "get_skill_root", return_value=self.skill_root):
            with mock.patch.object(archive_daily, "load_bio_header", return_value=None):
                with mock.patch.object(archive_daily, "load_bio_footer", return_value=None):
                    archive_daily.process_daily(data, self.json_dir, self.workspace,
                                                no_move=True, skip_html=True)

        # Should create with _2 suffix
        new_file = self.workspace / "published" / "20260719_生活中的美好：同一天_2.md"
        self.assertTrue(new_file.exists())


class MigrateProjectTest(unittest.TestCase):
    def test_migrate_project_to_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            project = Path(tmp) / "source" / "Project_Daily_测试标题"
            project.mkdir(parents=True)
            (project / "Draft.md").write_text("# 测试", encoding="utf-8")
            (project / "_temp_daily.json").write_text("{}", encoding="utf-8")

            archive_daily.migrate_project(project, workspace)

            archive_dir = workspace / "conductor" / "archive"
            self.assertTrue(archive_dir.exists())
            archived = list(archive_dir.glob("*_Daily_测试标题"))
            self.assertEqual(len(archived), 1)
            self.assertTrue((archived[0] / "Draft.md").exists())
            self.assertFalse(project.exists())  # Source removed

    def test_skips_non_daily_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            project = Path(tmp) / "source" / "Project_NotDaily_标题"
            project.mkdir(parents=True)
            (project / "Draft.md").write_text("# 测试", encoding="utf-8")

            archive_daily.migrate_project(project, workspace)

            # Should not archive
            archive_dir = workspace / "conductor" / "archive"
            self.assertFalse(archive_dir.exists())
            self.assertTrue(project.exists())


class CleanupHistoryTest(unittest.TestCase):
    def test_moves_old_published_files_to_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            pub = workspace / "published"
            pub.mkdir()
            (pub / "20260101_old_article.md").write_text("old", encoding="utf-8")
            (pub / "20260101_old_article.html").write_text("<html>", encoding="utf-8")

            import datetime
            future = datetime.datetime(2026, 12, 31)
            archive_daily.cleanup_history(workspace, today=future)

            history = pub / "history" / "2026-01"
            self.assertTrue(history.exists())
            self.assertTrue((history / "20260101_old_article.md").exists())
            self.assertFalse((pub / "20260101_old_article.md").exists())

    def test_keeps_today_files_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            pub = workspace / "published"
            pub.mkdir()
            (pub / "20260719_today.md").write_text("today", encoding="utf-8")

            import datetime
            today = datetime.datetime(2026, 7, 19)
            archive_daily.cleanup_history(workspace, today=today)

            self.assertTrue((pub / "20260719_today.md").exists())
            self.assertFalse((pub / "history").exists())

    def test_cleans_diary_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            diary = workspace / "diary"
            diary.mkdir()
            (diary / "2026-07-01.md").write_text("old diary", encoding="utf-8")

            import datetime
            future = datetime.datetime(2026, 12, 31)
            archive_daily.cleanup_history(workspace, today=future)

            history = diary / "history" / "2026-07"
            self.assertTrue(history.exists())
            self.assertTrue((history / "2026-07-01.md").exists())
            self.assertFalse((diary / "2026-07-01.md").exists())

    def test_keeps_img_dir_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            pub = workspace / "published"
            pub.mkdir()
            img = pub / "img"
            img.mkdir()

            import datetime
            future = datetime.datetime(2026, 12, 31)
            archive_daily.cleanup_history(workspace, today=future)

            self.assertTrue(img.exists())


class PickCoverImageTest(unittest.TestCase):
    def test_picks_cover_combined_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_dir = Path(tmp)
            (img_dir / "cover-main.jpg").write_bytes(b"main")
            (img_dir / "cover-combined.jpg").write_bytes(b"combined")

            result = archive_daily.pick_cover_image(img_dir)
            self.assertEqual(result.name, "cover-combined.jpg")

    def test_falls_back_to_cover_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_dir = Path(tmp)
            (img_dir / "cover-main.jpg").write_bytes(b"main")

            result = archive_daily.pick_cover_image(img_dir)
            self.assertIsNotNone(result)
            self.assertEqual(result.name, "cover-main.jpg")

    def test_returns_none_for_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_dir = Path(tmp)
            result = archive_daily.pick_cover_image(img_dir)
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
