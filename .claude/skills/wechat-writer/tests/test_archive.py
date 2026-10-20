#!/usr/bin/env python3
import importlib.util
import re
import shutil
import tempfile
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

# Fix Windows GBK encoding for emoji output
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass


ARCHIVE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "archive.py"
SPEC = importlib.util.spec_from_file_location("wechat_writer_archive", ARCHIVE_PATH)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


class ArchiveScriptTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.workspace = Path(self._tmpdir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "To-be-used").mkdir(parents=True, exist_ok=True)
        (self.workspace / "published").mkdir(parents=True, exist_ok=True)
        (self.workspace / "conductor" / "archive").mkdir(parents=True, exist_ok=True)
        self._date_prefix = datetime.now().strftime('%Y%m%d')

    def _create_project(self, project_name="Project_Test", draft_name="02_Draft.md"):
        project_dir = self.workspace / "To-be-used" / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        source = project_dir / draft_name
        source.write_text("正文第一段\n\n正文第二段\n", encoding="utf-8")
        return project_dir, source

    def _published_file(self, title="Article"):
        """Resolve the date-prefixed published file path."""
        safe = archive.sanitize_filename(title)
        return self.workspace / "published" / f"{self._date_prefix}_{safe}.md"

    def _run_archive(self, source_file, frontmatter, patch_move=None):
        data = {"source_file": str(source_file), "frontmatter": frontmatter}
        patchers = [
            mock.patch.object(archive._obs, "get_workspace_root", return_value=self.workspace),
            mock.patch.object(archive, "update_index", return_value=None),
        ]
        if patch_move is not None:
            patchers.append(mock.patch.object(archive.shutil, "move", side_effect=patch_move))

        with patchers[0], patchers[1]:
            if len(patchers) == 3:
                with patchers[2]:
                    archive.process_archive(data)
            else:
                archive.process_archive(data)

    @staticmethod
    def _extract_frontmatter_value(markdown_text, key):
        match = re.search(rf'^{key}:\s*"(.*)"$', markdown_text, re.MULTILINE)
        if not match:
            return None
        return match.group(1)

    def test_pick_cover_image_prioritizes_combined(self):
        _, source = self._create_project()
        img_dir = source.parent / "img"
        img_dir.mkdir()
        (img_dir / "cover-main.jpg").write_bytes(b"main")
        (img_dir / "cover-combined.jpg").write_bytes(b"combined")
        (img_dir / "cover-sidebar.jpg").write_bytes(b"sidebar")

        selected = archive.pick_cover_image(img_dir)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "cover-combined.jpg")

    def test_process_archive_auto_cover_uses_combined(self):
        _, source = self._create_project()
        img_dir = source.parent / "img"
        img_dir.mkdir()
        (img_dir / "cover-main.jpg").write_bytes(b"main")
        (img_dir / "cover-combined.jpg").write_bytes(b"combined")
        (img_dir / "cover-sidebar.jpg").write_bytes(b"sidebar")

        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": "summary",
            "tags": ["t1"],
        }
        self._run_archive(source, fm)

        output = self._published_file("Article").read_text(encoding="utf-8")
        self.assertEqual(
            self._extract_frontmatter_value(output, "cover"),
            "published/img/cover-combined.jpg",
        )

    def test_process_archive_keeps_explicit_cover(self):
        _, source = self._create_project()
        img_dir = source.parent / "img"
        img_dir.mkdir()
        (img_dir / "cover-main.jpg").write_bytes(b"main")
        (img_dir / "cover-combined.jpg").write_bytes(b"combined")

        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": "summary",
            "cover": "published/custom/my-cover.jpg",
            "tags": [],
        }
        self._run_archive(source, fm)

        output = self._published_file("Article").read_text(encoding="utf-8")
        self.assertEqual(
            self._extract_frontmatter_value(output, "cover"),
            "published/custom/my-cover.jpg",
        )

    def test_process_archive_leaves_cover_empty_when_no_valid_cover(self):
        _, source = self._create_project()
        img_dir = source.parent / "img"
        img_dir.mkdir()
        (img_dir / "cover-sidebar.jpg").write_bytes(b"sidebar")

        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": "summary",
            "tags": [],
        }
        self._run_archive(source, fm)

        output = self._published_file("Article").read_text(encoding="utf-8")
        self.assertEqual(self._extract_frontmatter_value(output, "cover"), "")

    def test_process_archive_falls_back_to_cover_main(self):
        _, source = self._create_project()
        img_dir = source.parent / "img"
        img_dir.mkdir()
        (img_dir / "cover-main.jpg").write_bytes(b"main")
        (img_dir / "cover-sidebar.jpg").write_bytes(b"sidebar")

        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": "summary",
            "tags": [],
        }
        self._run_archive(source, fm)

        output = self._published_file("Article").read_text(encoding="utf-8")
        self.assertEqual(
            self._extract_frontmatter_value(output, "cover"),
            "published/img/cover-main.jpg",
        )

    def test_process_archive_continues_when_img_move_fails(self):
        _, source = self._create_project()
        img_dir = source.parent / "img"
        img_dir.mkdir()
        (img_dir / "cover-combined.jpg").write_bytes(b"combined")

        real_copytree = shutil.copytree

        def flaky_copytree(src, dst, *args, **kwargs):
            if Path(src).name == "img":
                raise OSError("simulated copytree error")
            return real_copytree(src, dst, *args, **kwargs)

        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": "summary",
            "tags": [],
        }
        with mock.patch.object(archive.shutil, "copytree", side_effect=flaky_copytree):
            self._run_archive(source, fm)

        output_file = self._published_file("Article")
        self.assertTrue(output_file.exists())
        output = output_file.read_text(encoding="utf-8")
        self.assertEqual(self._extract_frontmatter_value(output, "cover"), "")

    def test_process_archive_keeps_explicit_cover_when_move_fails(self):
        _, source = self._create_project()
        img_dir = source.parent / "img"
        img_dir.mkdir()
        (img_dir / "cover-combined.jpg").write_bytes(b"combined")

        real_move = shutil.move

        def flaky_move(src, dst, *args, **kwargs):
            if Path(src).name == "img":
                raise OSError("simulated move error")
            return real_move(src, dst, *args, **kwargs)

        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": "summary",
            "cover": "published/custom/my-cover.jpg",
            "tags": [],
        }
        self._run_archive(source, fm, patch_move=flaky_move)

        output = self._published_file("Article").read_text(encoding="utf-8")
        self.assertEqual(
            self._extract_frontmatter_value(output, "cover"),
            "published/custom/my-cover.jpg",
        )

    def test_process_archive_escapes_frontmatter_values(self):
        _, source = self._create_project()
        title = 'Title "Q" \\ Path'
        excerpt = 'Say "Hi" in C:\\tmp'
        slug = 'slug-"quoted"-\\'

        fm = {
            "title": title,
            "slug": slug,
            "excerpt": excerpt,
            "tags": [],
        }
        self._run_archive(source, fm)

        safe_title = archive.sanitize_filename(title)
        output = (self.workspace / "published" / f"{self._date_prefix}_{safe_title}.md").read_text(encoding="utf-8")
        self.assertEqual(
            self._extract_frontmatter_value(output, "title"),
            archive.yaml_escape(title),
        )
        self.assertEqual(
            self._extract_frontmatter_value(output, "slug"),
            archive.yaml_escape(slug),
        )
        self.assertEqual(
            self._extract_frontmatter_value(output, "excerpt"),
            archive.yaml_escape(excerpt),
        )

    def test_process_archive_does_not_clamp_excerpt(self):
        _, source = self._create_project()
        long_excerpt = "a" * 140

        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": long_excerpt,
            "tags": [],
        }
        self._run_archive(source, fm)

        output = self._published_file("Article").read_text(encoding="utf-8")
        excerpt = self._extract_frontmatter_value(output, "excerpt")
        self.assertEqual(len(excerpt), 140)
        self.assertEqual(excerpt, "a" * 140)

    def test_process_archive_warns_when_excerpt_exceeds_120(self):
        _, source = self._create_project()
        long_excerpt = "a" * 140
        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": long_excerpt,
            "tags": [],
        }

        with mock.patch("builtins.print") as mock_print:
            self._run_archive(source, fm)

        warning = "⚠️ Excerpt length is 140 (>120). Please shorten it in Stage 3."
        self.assertTrue(
            any(args and args[0] == warning for args, _ in mock_print.call_args_list)
        )

    def test_process_archive_replaces_published_img_with_backup(self):
        _, source = self._create_project()
        old_img = self.workspace / "published" / "img"
        old_img.mkdir()
        (old_img / "cover-main.jpg").write_bytes(b"old")

        img_dir = source.parent / "img"
        img_dir.mkdir()
        (img_dir / "cover-main.jpg").write_bytes(b"new")

        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": "summary",
            "tags": [],
        }
        self._run_archive(source, fm)

        new_cover = self.workspace / "published" / "img" / "cover-main.jpg"
        self.assertTrue(new_cover.exists())

        # Backup is moved to history/ by _cleanup_history
        backups = list((self.workspace / "published" / "history").glob("*/img_prev_*"))
        self.assertTrue(backups, "Backup should exist in history/")
        self.assertTrue((backups[0] / "cover-main.jpg").exists())

    def test_process_archive_continues_when_backup_move_fails(self):
        _, source = self._create_project()
        old_img = self.workspace / "published" / "img"
        old_img.mkdir()
        (old_img / "cover-main.jpg").write_bytes(b"old")

        img_dir = source.parent / "img"
        img_dir.mkdir()
        (img_dir / "cover-main.jpg").write_bytes(b"new")

        real_move = shutil.move

        def flaky_move(src, dst, *args, **kwargs):
            src_path = Path(src)
            if src_path.name == "img" and src_path.parent.name == "published":
                raise OSError("simulated backup move error")
            return real_move(src, dst, *args, **kwargs)

        fm = {
            "title": "Article",
            "slug": "article",
            "excerpt": "summary",
            "tags": [],
        }
        self._run_archive(source, fm, patch_move=flaky_move)

        output_file = self._published_file("Article")
        self.assertTrue(output_file.exists())
        output = output_file.read_text(encoding="utf-8")
        self.assertEqual(self._extract_frontmatter_value(output, "cover"), "")
        self.assertTrue((self.workspace / "published" / "img" / "cover-main.jpg").exists())

    def test_strip_frontmatter(self):
        result = archive.strip_frontmatter("---\ntitle: X\n---\n\nbody")
        self.assertEqual(result, "body")

    def test_strip_frontmatter_no_fm(self):
        result = archive.strip_frontmatter("just body")
        self.assertEqual(result, "just body")

    def test_strip_h1_title(self):
        result = archive.strip_h1_title("# Title\n\nbody")
        self.assertEqual(result, "body")

    def test_strip_draft_metadata_block(self):
        result = archive.strip_draft_metadata(
            "> **版本**: v2\n> **主笔**: 冰清\n\n---\n\nbody"
        )
        self.assertEqual(result, "body")

    def test_strip_draft_metadata_no_match(self):
        result = archive.strip_draft_metadata("> A quote block\n\nbody")
        self.assertEqual(result, "> A quote block\n\nbody")

    def test_sanitize_filename(self):
        self.assertEqual(archive.sanitize_filename('test:file?"'), "testfile")

    def test_to_vault_path(self):
        result = archive.to_vault_path("published/img/x.jpg", "repo")
        self.assertEqual(result, "published/img/x.jpg")

    def test_to_vault_path_skip_url(self):
        result = archive.to_vault_path("https://cdn.example.com/x.jpg", "repo")
        self.assertEqual(result, "https://cdn.example.com/x.jpg")

    def test_security_rejects_path_outside_tobeused(self):
        project = self.workspace / "evil" / "Project_Bad"
        project.mkdir(parents=True)
        source = project / "02_Draft.md"
        source.write_text("bad", encoding="utf-8")
        fm = {"title": "Bad", "slug": "bad", "excerpt": "", "tags": []}
        data = {"source_file": str(source), "frontmatter": fm}
        with mock.patch.object(archive._obs, "get_workspace_root", return_value=self.workspace), \
             mock.patch.object(archive, "update_index", return_value=None):
            archive.process_archive(data)
        # Date-prefixed file should not exist since security rejected it
        bad_path = self.workspace / "published" / f"{self._date_prefix}_Bad.md"
        self.assertFalse(bad_path.exists())

    def test_yaml_escape_handles_none(self):
        self.assertEqual(archive.yaml_escape(None), "")

    def test_yaml_escape_backslash(self):
        self.assertEqual(archive.yaml_escape('a\\b'), "a\\\\b")


class ArticleCardTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.workspace = Path(self._tmpdir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        cards_dir = self.workspace / "knowledge" / "article_cards"
        cards_dir.mkdir(parents=True)
        index_path = self.workspace / "knowledge" / "published_article_index.md"
        index_path.write_text(
            "## 2026-06\n\n"
            "| 日期 | 标题 | 系列 | 写作模式 | 类型 | 标签 | 摘要 | 卡片 |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- |\n",
            encoding="utf-8"
        )

    def test_generate_card_creates_file(self):
        card_data = {
            "title": "Test Title", "date": "2026-06-24", "slug": "test-slug",
            "tags": ["t1", "t2"], "excerpt": "Test summary.",
            "series": "测试系列", "writing_mode": "原生",
            "article_type": "个人体感",
            "core_insight": "核心洞察内容",
            "key_scenes": ["场景1", "场景2"],
            "metaphor_system": "种子→花园",
            "characters": ["爸爸"],
            "framework": "三步法",
            "title_design": {
                "selected": {"path": "场景代入", "title": "选定标题", "c": 5, "e": 5, "v": 2},
                "alternative_paths": ["路径B"]
            },
            "golden_quotes": ["金句一"],
            "image_plan": [{"seq": 1, "theme": "朝阳", "position": "文首", "has_ip": True, "ip_style": "剪影"}]
        }
        cards_dir = self.workspace / "knowledge" / "article_cards"
        with mock.patch.object(archive, "get_knowledge_dir", return_value=self.workspace / "knowledge"):
            archive.generate_article_card(card_data, "20260624_Test_Title")

        card_file = cards_dir / "Card_20260624_Test_Title.md"
        self.assertTrue(card_file.exists())
        content = card_file.read_text(encoding="utf-8")
        self.assertIn("核心洞察内容", content)
        self.assertIn("场景1", content)
        self.assertIn("种子→花园", content)
        self.assertIn("金句一", content)

    def test_generate_card_skips_when_none(self):
        with mock.patch.object(archive, "get_knowledge_dir", return_value=self.workspace / "knowledge"):
            archive.generate_article_card(None, "20260624_None")
        # Should not raise, should not create any file

    def test_generate_card_handles_empty_fields(self):
        card_data = {
            "title": "", "date": "", "slug": "", "tags": [], "excerpt": "",
            "series": "", "writing_mode": "", "article_type": "",
            "core_insight": "", "key_scenes": [], "metaphor_system": "",
            "characters": [], "framework": "",
            "title_design": {}, "golden_quotes": [], "image_plan": []
        }
        cards_dir = self.workspace / "knowledge" / "article_cards"
        with mock.patch.object(archive, "get_knowledge_dir", return_value=self.workspace / "knowledge"):
            archive.generate_article_card(card_data, "20260624_Empty")
        self.assertTrue((cards_dir / "Card_20260624_Empty.md").exists())


if __name__ == "__main__":
    unittest.main()
