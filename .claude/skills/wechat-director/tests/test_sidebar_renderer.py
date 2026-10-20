#!/usr/bin/env python3
"""测试 sidebar_renderer.py — 侧边栏本地渲染器。"""

import sys
from pathlib import Path

import pytest

# 确保可以导入项目模块
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SKILL_DIR / "scripts"))

from sidebar_renderer import (
    parse_sidebar_prompt,
    render_sidebar_locally,
    calculate_font_size,
    calculate_stroke_width,
    DECORATION_KEYWORDS,
    DECORATION_REGISTRY,
    FONT_PATH,
    CANVAS_SIZE,
    _validate_text,
)


# ── 标准 prompt 模板 ──

def _make_prompt(bg_color="#D4A854", line1="念头", line2="来了",
                 decoration_line="无任何装饰元素。"):
    """构造标准 sidebar prompt。"""
    return f"""1:1 正方形构图。扁平矢量插画，贴纸风格。

纯色琥珀金背景（{bg_color}）。

画面中心，四个白色描边中文字——毛笔书法体，有机手绘笔触，不冰冷的排版字。文字分两行排布：

第一行：{line1}
第二行：{line2}

字体颜色为白色描边 + 与背景同色填充（镂空/阴刻效果），文字靠白色边界界定。每个汉字的字宽约占画面宽度的 16-18%——无论总共几个字，每个字的大小保持一致。总字数不同时，字块整体宽度自然不同，不要为了填满空间而放大字体，也不要为了挤进画面而缩小字体。两行之间有舒适的呼吸间距。{decoration_line}

无英文，无拼音，无数字。极简构图。
--ar 1:1"""


# ═══════════════════════════════════════════════
# parse_sidebar_prompt 测试
# ═══════════════════════════════════════════════

class TestParsePrompt:
    """标准 prompt 解析测试。"""

    def test_extracts_basic_fields(self):
        prompt = _make_prompt(line1="念头", line2="来了")
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['bg_color'] == '#D4A854'
        assert result['line1'] == '念头'
        assert result['line2'] == '来了'
        assert result['decoration'] is None

    def test_writer_color(self):
        prompt = _make_prompt(bg_color="#CC7A5A", line1="找准", line2="定位")
        result = parse_sidebar_prompt(prompt)
        assert result['bg_color'] == '#CC7A5A'

    def test_five_char_total(self):
        prompt = _make_prompt(line1="觉察到", line2="放下")
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['line1'] == '觉察到'
        assert result['line2'] == '放下'

    def test_six_char_total(self):
        prompt = _make_prompt(line1="觉察到", line2="就放下")
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['line1'] == '觉察到'
        assert result['line2'] == '就放下'


class TestParsePromptDecorations:
    """装饰检测测试。"""

    def test_no_decoration(self):
        prompt = _make_prompt(decoration_line="无任何装饰元素。")
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['decoration'] is None

    def test_line_decoration(self):
        prompt = _make_prompt(
            decoration_line="文字下方，一条纤细的白色横线，像地平线稳稳托住上面的字。"
        )
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['decoration'] == {'type': 'line'}

    def test_dot_decoration(self):
        prompt = _make_prompt(
            decoration_line="文字下方，一个白色小圆点。"
        )
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['decoration'] == {'type': 'dot'}

    def test_spark_decoration(self):
        prompt = _make_prompt(
            decoration_line="文字周围散落几点微光。"
        )
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['decoration'] == {'type': 'spark'}

    def test_unknown_decoration_returns_none(self):
        prompt = _make_prompt(
            decoration_line="文字下方，一片旋转的羽毛轻轻飘落。"
        )
        result = parse_sidebar_prompt(prompt)
        assert result is None  # 未知装饰 → AI 回退

    def test_mountain_decoration(self):
        prompt = _make_prompt(
            decoration_line="文字下方，三座远山的剪影。"
        )
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['decoration'] == {'type': 'mountain'}

    def test_wave_decoration(self):
        prompt = _make_prompt(
            decoration_line="文字下方，一条细细的波纹。"
        )
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['decoration'] == {'type': 'wave'}

    def test_water_drop_decoration(self):
        prompt = _make_prompt(
            decoration_line="文字下方，一滴墨点。"
        )
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['decoration'] == {'type': 'water_drop'}

    def test_seed_decoration(self):
        prompt = _make_prompt(
            decoration_line="文字下方，一颗种子。"
        )
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['decoration'] == {'type': 'seed'}

    def test_circle_ring_decoration(self):
        prompt = _make_prompt(
            decoration_line="文字下方，一个白色圆环。"
        )
        result = parse_sidebar_prompt(prompt)
        assert result is not None
        assert result['decoration'] == {'type': 'circle_ring'}


class TestParsePromptEdgeCases:
    """边界条件测试。"""

    def test_empty_prompt_returns_none(self):
        assert parse_sidebar_prompt("") is None

    def test_short_prompt_returns_none(self):
        assert parse_sidebar_prompt("hello") is None

    def test_missing_color_returns_none(self):
        prompt = """1:1 正方形构图。
第一行：念头
第二行：来了
无任何装饰元素。"""
        result = parse_sidebar_prompt(prompt)
        assert result is None

    def test_missing_line1_returns_none(self):
        prompt = """1:1 正方形构图。纯色背景（#D4A854）。
第二行：来了
无任何装饰元素。"""
        result = parse_sidebar_prompt(prompt)
        assert result is None

    def test_missing_line2_returns_none(self):
        prompt = """1:1 正方形构图。纯色背景（#D4A854）。
第一行：念头
无任何装饰元素。"""
        result = parse_sidebar_prompt(prompt)
        assert result is None

    def test_line_too_long_returns_none(self):
        prompt = _make_prompt(line1="五个字太多了")
        result = parse_sidebar_prompt(prompt)
        assert result is None

    def test_total_too_many_returns_none(self):
        prompt = _make_prompt(line1="四个字啊", line2="三个字呢")
        result = parse_sidebar_prompt(prompt)
        assert result is None

    def test_english_text_returns_none(self):
        prompt = _make_prompt(line1="Hello", line2="World")
        result = parse_sidebar_prompt(prompt)
        assert result is None


# ═══════════════════════════════════════════════
# 动态字号测试
# ═══════════════════════════════════════════════

class TestFontSize:
    def test_two_chars_max_font(self):
        size = calculate_font_size("念头", "来了")
        assert size == 360  # 2 chars → max

    def test_three_chars_mid_font(self):
        size = calculate_font_size("觉察到", "放下")
        assert size == 245  # 3 chars → int(1024*0.72/3) = int(245.76) = 245

    def test_four_chars_min_font(self):
        size = calculate_font_size("一小步", "也是进步")
        assert size == 184  # 4 chars → int(1024*0.72/4) = int(184.32) = 184

    def test_stroke_scales_with_font(self):
        assert calculate_stroke_width(300) > calculate_stroke_width(150)


# ═══════════════════════════════════════════════
# 渲染测试
# ═══════════════════════════════════════════════

class TestRender:
    def test_renders_1024x1024(self):
        img = render_sidebar_locally('#D4A854', '念头', '来了')
        assert img.size == (1024, 1024)
        assert img.mode == 'RGB'

    def test_renders_rgb_mode(self):
        img = render_sidebar_locally('#D4A854', '念头', '来了')
        assert img.mode == 'RGB'

    def test_renders_with_decoration_no_error(self):
        for dec_type in DECORATION_REGISTRY:
            img = render_sidebar_locally(
                '#D4A854', '看见', '放下',
                decoration={'type': dec_type}
            )
            assert img.size == (1024, 1024)

    def test_all_eight_decorations_render(self):
        for dec_type in ['line', 'dot', 'spark', 'circle_ring',
                         'mountain', 'wave', 'water_drop', 'seed']:
            img = render_sidebar_locally(
                '#CC7A5A', '找准', '定位',
                decoration={'type': dec_type}
            )
            assert img is not None
            assert img.size == (1024, 1024)

    def test_missing_font_raises(self):
        with pytest.raises(FileNotFoundError):
            render_sidebar_locally(
                '#D4A854', '念头', '来了',
                font_path='/nonexistent/font.otf'
            )

    @pytest.mark.skipif(not FONT_PATH.exists(),
                        reason="字体文件未安装")
    def test_font_file_exists(self):
        assert FONT_PATH.exists()


# ═══════════════════════════════════════════════
# 装饰注册表测试
# ═══════════════════════════════════════════════

class TestDecorationRegistry:
    def test_all_eight_registered(self):
        expected = {'line', 'dot', 'spark', 'circle_ring',
                    'mountain', 'wave', 'water_drop', 'seed'}
        assert set(DECORATION_REGISTRY.keys()) == expected

    def test_all_have_keywords(self):
        for dec_type in DECORATION_REGISTRY:
            assert dec_type in DECORATION_KEYWORDS
            assert len(DECORATION_KEYWORDS[dec_type]) >= 2


# ═══════════════════════════════════════════════
# 真实 prompt 回归测试
# ═══════════════════════════════════════════════

REAL_DAILY_PROMPT = """1:1 正方形构图。扁平矢量插画，贴纸风格。

纯色琥珀金背景（#D4A854）。

画面中心，四个白色描边中文字——毛笔书法体，有机手绘笔触，不冰冷的排版字。文字分两行排布：

第一行：念头
第二行：来了

字体颜色为白色描边 + 与背景同色填充（镂空/阴刻效果），文字靠白色边界界定。每个汉字的字宽约占画面宽度的 16-18%——无论总共几个字，每个字的大小保持一致。总字数不同时，字块整体宽度自然不同，不要为了填满空间而放大字体，也不要为了挤进画面而缩小字体。两行之间有舒适的呼吸间距。无任何装饰元素。

无英文，无拼音，无数字。极简构图。
--ar 1:1"""


class TestRealPrompts:
    def test_daily_prompt_parses(self):
        result = parse_sidebar_prompt(REAL_DAILY_PROMPT)
        assert result is not None
        assert result['bg_color'] == '#D4A854'
        assert result['line1'] == '念头'
        assert result['line2'] == '来了'
        assert result['decoration'] is None

    def test_daily_prompt_renders(self):
        result = parse_sidebar_prompt(REAL_DAILY_PROMPT)
        assert result is not None
        img = render_sidebar_locally(**result)
        assert img.size == (1024, 1024)


# ═══════════════════════════════════════════════
# 文字验证测试
# ═══════════════════════════════════════════════

class TestTextValidation:
    def test_valid_two_plus_two(self):
        assert _validate_text('看见', '放下') is True

    def test_valid_three_plus_two(self):
        assert _validate_text('觉察到', '放下') is True

    def test_valid_three_plus_three(self):
        assert _validate_text('觉察到', '就放下') is True

    def test_single_char_rejected(self):
        assert _validate_text('看见', '看') is False  # line2 only 1 char

    def test_too_many_chars_rejected(self):
        assert _validate_text('五个字太多', '来') is False  # line1 too long

    def test_empty_rejected(self):
        assert _validate_text('', '') is False
