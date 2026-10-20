#!/usr/bin/env python3
"""Unit tests for format.py — Markdown to WeChat HTML conversion."""
import importlib.util
import json
import tempfile
import sys
import unittest
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass

FORMAT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "format.py"
SPEC = importlib.util.spec_from_file_location("format", FORMAT_PATH)
fmt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fmt)


class RenderInlineTest(unittest.TestCase):
    def test_bold(self):
        result = fmt.render_inline("前面 **加粗** 后面")
        self.assertIn("<strong>加粗</strong>", result)

    def test_italic(self):
        result = fmt.render_inline("前面 *斜体* 后面")
        self.assertIn("<em>斜体</em>", result)

    def test_wiki_link(self):
        result = fmt.render_inline("参考 [[文章标题]] 内容")
        self.assertIn("文章标题", result)
        self.assertNotIn("[[", result)


class ParseGoldQuotesTest(unittest.TestCase):
    def test_parse_table(self):
        prod = """## 金句提炼

| # | 原文 | 打磨后 | 手法 | 用途 |
|---|------|--------|------|------|
| 1 | 原句一 | 打磨句一 | 关联词法 | 转发语 |
| 2 | 原句二 | 打磨句二 | 修辞法 | 正文替换 |
"""
        quotes = fmt.parse_gold_quotes(prod)
        self.assertEqual(len(quotes), 2)
        self.assertEqual(quotes[0], ("原句一", "打磨句一"))
        self.assertEqual(quotes[1], ("原句二", "打磨句二"))

    def test_no_table(self):
        self.assertEqual(fmt.parse_gold_quotes("没有金句表格"), [])

    def test_stops_at_next_section(self):
        prod = """## 金句提炼

| # | 原文 | 打磨后 | 手法 | 用途 |
|---|------|--------|------|------|
| 1 | 金句 | 金句 | - | - |

---

## 包装
"""
        quotes = fmt.parse_gold_quotes(prod)
        self.assertEqual(len(quotes), 1)


class ParseLayoutCardTest(unittest.TestCase):
    def test_empty(self):
        card = fmt.parse_layout_card("没有排版设计卡")
        self.assertEqual(card, {"strong_breaks": [], "opening_quote": False})

    def test_strong_breaks(self):
        prod = """## 排版设计卡

### 强视觉停顿

| 编号 | 位置 | 理由 |
|------|------|------|
| 1 | A和B之间 | 转折 |
| 3 | C和D之间 | 切换 |
"""
        card = fmt.parse_layout_card(prod)
        self.assertEqual(card["strong_breaks"], [1, 3])
        self.assertFalse(card["opening_quote"])

    def test_opening_quote(self):
        prod = """## 排版设计卡

### 开头引语

| 段落 | 处理 |
|------|------|
| 第 1 段 blockquote | 居中浅灰题记 |
"""
        card = fmt.parse_layout_card(prod)
        self.assertTrue(card["opening_quote"])


class MarkdownToHTMLTest(unittest.TestCase):
    """End-to-end rendering tests."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)

    def _run(self, md, gold_quotes=None, layout_card=None):
        return fmt.markdown_to_html(md, gold_quotes or [], layout_card or {})

    def test_single_paragraph(self):
        html = self._run("这是一段比较长的正文内容用来测试标准段落渲染效果。")
        self.assertIn("这是一段比较长的正文内容用来测试标准段落渲染效果", html)
        self.assertIn("line-height:1.75", html)
        self.assertIn("padding-bottom:6px", html)

    def test_multiple_paragraphs(self):
        html = self._run("第一段。\n\n第二段。\n\n第三段。")
        self.assertEqual(html.count("<p "), 3)

    def test_h2_heading(self):
        html = self._run("## 子标题\n\n正文。")
        self.assertIn("子标题", html)
        self.assertIn("color:#FF6B35", html)
        self.assertIn("font-weight:bold", html)
        self.assertIn("font-size:17px", html)

    def test_h3_heading(self):
        html = self._run("### 小标题\n\n正文。")
        self.assertIn("小标题", html)
        self.assertIn("color:#333333", html)
        self.assertIn("font-size:15px", html)

    def test_regular_divider(self):
        html = self._run("段落一。\n\n---\n\n段落二。")
        self.assertIn("border-top:1px solid #dddddd", html)

    def test_strong_divider(self):
        html = self._run(
            "段落一。\n\n---\n\n段落二。",
            layout_card={"strong_breaks": [1], "opening_quote": False}
        )
        self.assertIn("border-top:1px solid #FF6B35", html)

    def test_gold_quote_coloring(self):
        html = self._run(
            "前面。\n\n这就是那句金句。\n\n后面。",
            gold_quotes=[("原版", "这就是那句金句。")]
        )
        self.assertIn("font-weight:bold", html)
        self.assertIn("这就是那句金句", html)

    def test_gold_quote_fallback_to_original(self):
        html = self._run(
            "金句原文在这里。",
            gold_quotes=[("金句原文在这里。", "打磨版不同")]
        )
        self.assertIn("font-weight:bold", html)

    def test_short_paragraph_extra_spacing(self):
        html = self._run("短句。")
        self.assertIn("padding-bottom:6px", html)

    def test_blockquote(self):
        html = self._run("> 一段引用。")
        self.assertIn("一段引用", html)

    def test_related_reading(self):
        html = self._run("> 相关阅读: [[旧文]]")
        self.assertIn("border-left:2px solid #FF6B35", html)
        self.assertIn("旧文", html)
        self.assertNotIn("[[", html)

    def test_image(self):
        html = self._run("![描述|400](img/test.jpg)")
        self.assertIn("<img", html)
        self.assertIn("描述", html)
        self.assertIn("img/test.jpg", html)
        self.assertIn("padding:15px 0", html)

    def test_bold_inline(self):
        html = self._run("前面 **加粗** 后面。")
        self.assertIn("<strong>加粗</strong>", html)

    def test_wiki_link_stripped(self):
        html = self._run("参考 [[20260601_文章]] 内容。")
        self.assertIn("20260601_文章", html)
        self.assertNotIn("[[", html)

    def test_bio_footer(self):
        html = self._run("正文。\n\n---\n\n**编码人生.lab**\n\n星辰的个人实验开源平台。")
        self.assertIn("color:#888888", html)

    def test_bio_header(self):
        """Bio header (personal intro) should render in lighter gray."""
        html = self._run(
            "大家好！我是星辰，一名用教练方法和技术思维重构人生的实验者。"
            "用微习惯编码行为，正念维护内核，验证像迭代产品一样迭代人生。\n\n"
            "这是正文。"
        )
        # Bio header paragraph should have light gray color
        self.assertIn("color:#888888", html)
        body_paragraphs = html.count("line-height:1.75; padding-bottom:6px;")
        self.assertGreater(body_paragraphs, 0, "Body paragraph should exist after bio header")

    def test_draft_metadata_stripped(self):
        """Draft header (# Title + metadata blockquote + ---) should be removed."""
        html = self._run(
            "# 02_Draft：测试文章\n\n"
            "> 主笔: 冰清 | 版本: v1 | 日期: 2026-06-16 | 写作模式: 原生\n\n"
            "---\n\n"
            "这是真正的正文。"
        )
        self.assertNotIn("02_Draft", html)
        self.assertNotIn("主笔:", html)
        self.assertNotIn("版本:", html)
        self.assertIn("这是真正的正文", html)

    def test_yaml_frontmatter_stripped(self):
        """Published format YAML frontmatter (--- ... ---) should be removed."""
        html = self._run(
            "---\n"
            "title: \"测试标题\"\n"
            "date: \"2026-06-16\"\n"
            "slug: \"test-slug\"\n"
            "status: published\n"
            "---\n"
            "这是真正的正文。"
        )
        self.assertNotIn("测试标题", html)
        self.assertNotIn("test-slug", html)
        self.assertNotIn("status:", html)
        self.assertIn("这是真正的正文", html)

    def test_fuzzy_gold_quote_match(self):
        """Gold quote with slight text variations should still match via fuzzy matching."""
        html = self._run(
            "当所有外在的声音，领导的期待，组织的目标，都变成噪音之后，剩下的那个声音才是你自己的。",
            gold_quotes=[("当所有外在的声音都变成噪音之后，剩下的那个声音才是你自己的。", "")]
        )
        self.assertIn("font-weight:bold", html)

    def test_opening_quote(self):
        html = self._run(
            "> 题记内容。\n\n正文。",
            layout_card={"strong_breaks": [], "opening_quote": True}
        )
        self.assertIn("color:#888888", html)
        self.assertIn("text-align:center", html)

    def test_empty_gold_quotes(self):
        html = self._run("正文。", gold_quotes=[])
        self.assertIn("正文", html)

    def test_gold_quote_multiple_occurrences(self):
        html = self._run(
            "重复金句。\n\n中间。\n\n重复金句。",
            gold_quotes=[("重复金句。", "重复金句。")]
        )
        self.assertEqual(html.count("font-weight:bold"), 2)

    def test_gold_marker_section_skipped(self):
        """[金句标记] section should NOT be detected as gold quotes."""
        html = self._run(
            "前面正文。\n\n## [金句标记]\n\n1. 金句一\n2. 金句二",
            gold_quotes=[("金句一", "金句一")]
        )
        self.assertIn("[金句标记]", html)
        # The heading itself has font-weight:bold (it's h2), but the gold
        # quote list paragraph should NOT be bolded. Count: only 1 from h2.
        self.assertEqual(html.count("font-weight:bold"), 1)

    def test_bookquote_basic(self):
        html = self._run(">> 做人就像是一家客栈。\n>> 每个早晨，一位新的客人。")
        self.assertIn("border-left:3px solid #C8A96E", html)
        self.assertIn("background:#F5EFE6", html)
        self.assertIn("做人就像是一家客栈", html)
        self.assertIn("每个早晨", html)

    def test_bookquote_preserves_linebreaks(self):
        html = self._run(">> 第一行\n>> 第二行\n>> 第三行")
        self.assertIn("<br>", html)

    def test_bookquote_with_empty_continuation(self):
        html = self._run(">> 第一段\n>>\n>> 第二段")
        self.assertIn("第一段", html)
        self.assertIn("第二段", html)

    def test_blockquote_empty_continuation(self):
        """Bare > without space should be treated as blockquote continuation."""
        html = self._run("> 第一段引用。\n>\n> 第二段引用。")
        self.assertIn("第一段引用", html)
        self.assertIn("第二段引用", html)
        self.assertNotIn("&gt;", html)  # No literal > in output

class MainCLITest(unittest.TestCase):
    """End-to-end CLI tests."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)

        self.draft = self.tmp / "02_Draft.md"
        self.draft.write_text("测试正文。\n\n## 标题\n\n内容。", encoding="utf-8")

        self.prod = self.tmp / "03_Production.md"
        self.prod.write_text(
            "## 金句提炼\n\n"
            "| # | 原文 | 打磨后 | 手法 | 用途 |\n"
            "|---|------|--------|------|------|\n"
            "| 1 | 测试正文。 | 测试正文。 | - | - |\n",
            encoding="utf-8"
        )

        self.json_input = self.tmp / "_temp_format.json"
        self.output = self.tmp / "output.html"

    def test_full_pipeline(self):
        data = {
            "draft_file": str(self.draft),
            "production_file": str(self.prod),
            "output_path": str(self.output)
        }
        self.json_input.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

        import io
        saved_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            fmt.process_format(data)
        finally:
            sys.stdout = saved_stdout

        self.assertTrue(self.output.exists())
        html = self.output.read_text(encoding="utf-8")
        self.assertIn("测试正文", html)
        self.assertIn("font-weight:bold", html)

    def test_missing_production_file(self):
        data = {
            "draft_file": str(self.draft),
            "production_file": str(self.tmp / "nonexistent.md"),
            "output_path": str(self.output)
        }
        fmt.process_format(data)
        self.assertTrue(self.output.exists())


if __name__ == "__main__":
    unittest.main()
