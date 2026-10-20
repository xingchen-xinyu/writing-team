#!/usr/bin/env python3
"""
sidebar_renderer.py — 侧边栏本地 Pillow 渲染器 v1.0.0

不依赖 AI 生图模型，直接从 Storyboard prompt 中解析结构化参数，
用 Pillow + 鸿雷行书简体字体精确渲染中文侧边栏。

用法:
    from sidebar_renderer import parse_sidebar_prompt, render_sidebar_locally

    params = parse_sidebar_prompt(prompt_text)
    if params:
        img = render_sidebar_locally(**params)
        img.save("cover-sidebar.jpg", quality=95)
"""

import re
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ── 常量 ──
_SCRIPT_DIR = Path(__file__).resolve().parent
FONT_PATH = _SCRIPT_DIR.parent / "assets" / "hongleixingshu.otf"

CANVAS_SIZE = 1024
TARGET_BLOCK_WIDTH_PCT = 0.72  # 文字块目标占画面宽度比例
FONT_SIZE_MIN = 150            # 4 字/行时的下限
FONT_SIZE_MAX = 360            # 2 字/行时的上限
STROKE_WIDTH_PCT = 0.035       # 描边宽度 = 字号 × 3.5%
LINE_SPACING_PCT = 0.40        # 行间距 = 字号 × 40%

STROKE_COLOR = (255, 255, 255, 255)  # 白色描边


# ── 动态字号计算 ──

def calculate_font_size(line1, line2):
    """根据最长行字数动态计算字号，保证文字块占画面 ~60% 宽度。"""
    max_chars = max(len(line1), len(line2))
    if max_chars < 1:
        max_chars = 1
    size = int(CANVAS_SIZE * TARGET_BLOCK_WIDTH_PCT / max_chars)
    return max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, size))


def calculate_stroke_width(font_size):
    """描边宽度随字号等比缩放，最小 4px。"""
    return max(4, int(font_size * STROKE_WIDTH_PCT))


# ── 颜色工具 ──

def _hex_to_rgba(hex_color):
    """将 '#D4A854' 转为 RGBA 元组。"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    elif len(hex_color) == 3:
        r, g, b = int(hex_color[0]*2, 16), int(hex_color[1]*2, 16), int(hex_color[2]*2, 16)
    else:
        raise ValueError(f"无法解析颜色: #{hex_color}")
    return (r, g, b, 255)


# ── 镂空文字渲染 ──

def _draw_hollow_text(draw, text, position, font, fill_color, stroke_color, stroke_width):
    """镂空/阴刻效果：白色外描边 + 底色同色填充。

    使用 Pillow 原生 stroke_width/stroke_fill 参数（≥8.0.0 支持），
    渲染真正的字形轮廓描边，质量高于手动偏移叠加。
    """
    x, y = position
    draw.text((x, y), text, font=font, fill=fill_color,
              stroke_width=stroke_width, stroke_fill=stroke_color)


# ── 装饰库 ──

DECORATION_KEYWORDS = {
    'line':        ['横线', '细线', '地平线', '水平线', '一条线'],
    'dot':         ['一个点', '圆点', '小点', '一个圆点'],
    'spark':       ['火花', '微光', '星光', '闪光', '一点光'],
    'circle_ring': ['圆圈', '圆环', '光环', '一个环', '光圈'],
    'mountain':    ['山', '山峰', '山峦', '山的剪影', '远山'],
    'wave':        ['波浪', '浪', '波纹', '水波', '波浪线'],
    'water_drop':  ['水滴', '墨点', '泪滴', '一滴', '水珠'],
    'seed':        ['种子', '嫩芽', '芽', '一颗种子'],
}

DECORATION_REGISTRY = {}


def register_decoration(name):
    """装饰注册装饰器。"""
    def wrapper(func):
        DECORATION_REGISTRY[name] = func
        return func
    return wrapper


def _detect_decoration_v2(prompt_text):
    """从 prompt 文本中检测装饰类型（改进版：句级模板清洗 + 最长关键词匹配）。

    Returns:
        (decoration_dict_or_None, is_unknown_bool)
    """
    # 明确声明无装饰
    if re.search(r'无任何装饰|无装饰', prompt_text):
        return None, False

    # 提取第二行之后的区域（装饰描述只可能出现在这里，避免标题文字误匹配）
    after_text = re.split(r'第二行[：:].*?(?:\n|$)', prompt_text, maxsplit=1)
    post_second = after_text[1] if len(after_text) > 1 else ""

    # 扫描关键词 —— 按匹配长度降序，优先匹配更具体的关键词
    all_matches = []
    for dec_type, keywords in DECORATION_KEYWORDS.items():
        for kw in keywords:
            if kw in post_second:
                all_matches.append((len(kw), dec_type, kw))
    if all_matches:
        all_matches.sort(key=lambda x: x[0], reverse=True)
        return {'type': all_matches[0][1]}, False

    # 检查是否有未识别的装饰描述
    if post_second:
        # 按句子拆分，过滤模板套话句子
        sentences = re.split(r'[。\n]', post_second)
        decoration_sentences = []
        boilerplate_keywords = [
            '无英文', '无拼音', '无数字', '极简构图', '--ar',
            '字体颜色为白色描边', '与背景同色填充', '镂空', '阴刻',
            '每个汉字的字宽', '字块整体宽度', '不要为了',
            '两行之间有', '画面中心', '毛笔书法体',
            '扁平矢量插画', '贴纸风格', '纯色', '正方形构图',
            '分两行排布', '文字靠白色边界界定',
            '不论总共', '舒适的呼吸间距',
        ]
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            is_boilerplate = False
            for bp in boilerplate_keywords:
                if bp in sent:
                    is_boilerplate = True
                    break
            if not is_boilerplate:
                decoration_sentences.append(sent)

        remaining = '。'.join(decoration_sentences).strip()
        if remaining and len(remaining) > 5:
            return None, True  # 未知装饰 → AI 回退

    return None, False


# ── Prompt 解析 ──
def parse_sidebar_prompt(prompt_text):
    """从 Storyboard Part B prompt 文本中提取结构化参数。

    Args:
        prompt_text: Storyboard.md Part B 代码块中的原始 prompt 文本

    Returns:
        dict: {'bg_color': '#D4A854', 'line1': '念头', 'line2': '来了',
               'decoration': None | {'type': 'line'}}
        None: 解析失败，应回退 AI 生图
    """
    if not prompt_text or len(prompt_text.strip()) < 20:
        return None

    # 1. 提取十六进制颜色
    color_match = re.search(r'#([A-Fa-f0-9]{6})', prompt_text)
    if not color_match:
        return None
    bg_color = f'#{color_match.group(1)}'

    # 2. 提取第一行文字
    line1_match = re.search(r'第一行[：:]\s*(.+?)(?:\n|$)', prompt_text)
    if not line1_match:
        return None
    line1 = line1_match.group(1).strip()

    # 3. 提取第二行文字
    line2_match = re.search(r'第二行[：:]\s*(.+?)(?:\n|$)', prompt_text)
    if not line2_match:
        return None
    line2 = line2_match.group(1).strip()

    # 4. 验证文字内容
    if not _validate_text(line1, line2):
        return None

    # 5. 检测装饰
    decoration, is_unknown = _detect_decoration_v2(prompt_text)
    if is_unknown:
        return None  # 未知装饰 → AI 回退

    return {
        'bg_color': bg_color,
        'line1': line1,
        'line2': line2,
        'decoration': decoration,
    }


def _validate_text(line1, line2):
    """验证文字内容：每行 2-4 字，总计 4-6 字，主要为中文。"""
    total = len(line1) + len(line2)
    if total < 2 or total > 6:
        return False
    if len(line1) < 2 or len(line1) > 4:
        return False
    if len(line2) < 2 or len(line2) > 4:
        return False

    # 允许中文字符 + 常用中文标点
    combined = line1 + line2
    cjk_count = 0
    for ch in combined:
        cp = ord(ch)
        # CJK Unified Ideographs + CJK Extension A + 中文标点
        if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0x3000 <= cp <= 0x303F or 0xFF00 <= cp <= 0xFFEF):
            cjk_count += 1
    # 至少 80% 为中文字符
    if len(combined) > 0 and cjk_count / len(combined) < 0.8:
        return False

    return True


# ── 渲染入口 ──

def render_sidebar_locally(bg_color, line1, line2, decoration=None,
                           font_path=None, canvas_size=1024):
    """本地渲染侧边栏图片。

    Args:
        bg_color: 背景色（如 '#D4A854'）
        line1: 第一行文字
        line2: 第二行文字
        decoration: 装饰描述 dict（如 {'type': 'line'}）或 None
        font_path: 字体路径，默认使用内置鸿雷行书简体
        canvas_size: 画布尺寸，默认 1024

    Returns:
        PIL.Image.Image: RGB 模式的 1024×1024 图片
    """
    if font_path is None:
        font_path = FONT_PATH

    font_path = Path(font_path)
    if not font_path.exists():
        raise FileNotFoundError(f"字体文件不存在: {font_path}")

    # 动态计算字号
    font_size = calculate_font_size(line1, line2)
    stroke_width = calculate_stroke_width(font_size)

    # 加载字体
    font = ImageFont.truetype(str(font_path), font_size)

    # 创建画布
    bg_rgba = _hex_to_rgba(bg_color)
    img = Image.new('RGBA', (canvas_size, canvas_size), bg_rgba)
    draw = ImageDraw.Draw(img)

    # 测量文字
    bbox1 = draw.textbbox((0, 0), line1, font=font)
    bbox2 = draw.textbbox((0, 0), line2, font=font)
    w1, h1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
    w2, h2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]

    # 计算位置：上下两行居中
    line_spacing = int(font_size * LINE_SPACING_PCT)
    total_h = h1 + line_spacing + h2
    start_y = (canvas_size - total_h) // 2

    x1 = (canvas_size - w1) // 2
    x2 = (canvas_size - w2) // 2
    y1 = start_y
    y2 = start_y + h1 + line_spacing

    # 绘制镂空文字
    _draw_hollow_text(draw, line1, (x1, y1), font, bg_rgba, STROKE_COLOR, stroke_width)
    _draw_hollow_text(draw, line2, (x2, y2), font, bg_rgba, STROKE_COLOR, stroke_width)

    # 绘制装饰
    if decoration and decoration.get('type') in DECORATION_REGISTRY:
        draw_fn = DECORATION_REGISTRY[decoration['type']]
        # 将文字区域信息传给装饰函数
        text_block = {
            'top': y1,
            'bottom': min(y2 + h2, canvas_size - 20),
            'left': min(x1, x2),
            'right': max(x1 + w1, x2 + w2),
        }
        draw_fn(draw, canvas_size, text_block, font_size, decoration.get('params', {}))

    # Composite RGBA onto solid RGB background (preserves semi-transparent decoration fills)
    bg_rgb = Image.new('RGB', (canvas_size, canvas_size), bg_rgba[:3])
    bg_rgb.paste(img, (0, 0), img)
    return bg_rgb


# ═══════════════════════════════════════════════
# 装饰绘制函数
# ═══════════════════════════════════════════════

def _white(fill_alpha=255):
    return (255, 255, 255, fill_alpha)


@register_decoration('line')
def draw_line(draw, canvas_size, text_block, font_size, params):
    """一条细白横线，如地平线托住文字。"""
    y_offset = params.get('y_offset', int(font_size * 0.5))
    line_width_pct = params.get('width_pct', 28)
    thickness = params.get('thickness', max(2, int(font_size * 0.015)))

    y = text_block['bottom'] + y_offset
    line_w = int(canvas_size * line_width_pct / 100)
    x1 = (canvas_size - line_w) // 2
    x2 = x1 + line_w

    draw.line([(x1, y), (x2, y)], fill=_white(), width=thickness)


@register_decoration('dot')
def draw_dot(draw, canvas_size, text_block, font_size, params):
    """一个实心圆点。"""
    y_offset = params.get('y_offset', int(font_size * 0.45))
    radius = params.get('radius', max(4, int(font_size * 0.04)))

    cx = canvas_size // 2
    cy = text_block['bottom'] + y_offset

    draw.ellipse(
        [(cx - radius, cy - radius), (cx + radius, cy + radius)],
        fill=_white()
    )


@register_decoration('spark')
def draw_spark(draw, canvas_size, text_block, font_size, params):
    """几粒微光十字散落。"""
    count = params.get('count', 3)
    y_offset = params.get('y_offset', int(font_size * 0.4))
    spread = params.get('spread', int(font_size * 0.35))
    arm_len = max(3, int(font_size * 0.025))

    base_y = text_block['bottom'] + y_offset
    rng_state = canvas_size * 37 + font_size * 13  # 确定性伪随机

    for i in range(count):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        cx = (canvas_size // 2) + (rng_state % (spread * 2 + 1)) - spread
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        cy = base_y + (rng_state % (spread // 2 + 1))

        # 十字微光
        draw.line([(cx - arm_len, cy), (cx + arm_len, cy)], fill=_white(180), width=1)
        draw.line([(cx, cy - arm_len), (cx, cy + arm_len)], fill=_white(180), width=1)


@register_decoration('circle_ring')
def draw_circle_ring(draw, canvas_size, text_block, font_size, params):
    """一个细线圆环。"""
    y_offset = params.get('y_offset', int(font_size * 0.1))
    radius = params.get('radius', int(font_size * 0.25))
    thickness = params.get('thickness', max(1, int(font_size * 0.01)))

    cx = canvas_size // 2
    cy = text_block['bottom'] + y_offset + radius

    draw.ellipse(
        [(cx - radius, cy - radius), (cx + radius, cy + radius)],
        outline=_white(),
        width=thickness
    )


@register_decoration('mountain')
def draw_mountain(draw, canvas_size, text_block, font_size, params):
    """2-3 座三角山剪影。"""
    peak_count = params.get('count', 3)
    height = params.get('height', int(font_size * 0.45))
    y_offset = params.get('y_offset', int(font_size * 0.5))

    base_y = text_block['bottom'] + y_offset + height
    mountain_width = int(canvas_size * 0.3)
    start_x = (canvas_size - mountain_width) // 2

    peaks = []
    for i in range(peak_count):
        # 每座山：底边宽、峰高不同
        seg_w = mountain_width // (peak_count - 1) if peak_count > 1 else mountain_width
        cx = start_x + i * seg_w if peak_count > 1 else canvas_size // 2
        peak_h = height * (0.7 + 0.3 * ((i * 137 + 59) % 100) / 100)  # 确定性变高
        peaks.append((cx, base_y - int(peak_h)))

    # 画每座山
    for i, (cx, peak_y) in enumerate(peaks):
        half_base = mountain_width // (peak_count * 2 - 2) if peak_count > 1 else mountain_width // 3
        if peak_count == 1:
            half_base = mountain_width // 2
        left = max(0, cx - half_base)
        right = min(canvas_size, cx + half_base)
        draw.polygon(
            [(left, base_y), (cx, peak_y), (right, base_y)],
            outline=_white(60),
            width=1
        )


@register_decoration('wave')
def draw_wave(draw, canvas_size, text_block, font_size, params):
    """正弦波曲线。"""
    y_offset = params.get('y_offset', int(font_size * 0.45))
    amplitude = params.get('amplitude', max(4, int(font_size * 0.06)))
    width_pct = params.get('width_pct', 30)
    segments = params.get('segments', 40)

    wave_width = int(canvas_size * width_pct / 100)
    start_x = (canvas_size - wave_width) // 2
    base_y = text_block['bottom'] + y_offset + amplitude

    points = []
    for i in range(segments + 1):
        t = i / segments
        x = start_x + int(wave_width * t)
        y = base_y - int(amplitude * math.sin(t * 2 * math.pi))
        points.append((x, y))

    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=_white(120), width=2)


@register_decoration('water_drop')
def draw_water_drop(draw, canvas_size, text_block, font_size, params):
    """水滴/泪滴形。"""
    y_offset = params.get('y_offset', int(font_size * 0.5))
    size = params.get('size', int(font_size * 0.18))

    cx = canvas_size // 2
    cy = text_block['bottom'] + y_offset

    # 水滴形状：上方弧形 + 下方尖角
    points = []
    num_points = 24
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        # 上方圆形，下方收尖
        if angle < math.pi:
            r = size
        else:
            # 下方逐渐收尖
            progress = (angle - math.pi) / math.pi
            r = size * (1 - progress * 0.85)
        px = cx + r * math.sin(angle)
        py = cy - r * math.cos(angle) + size * 0.25
        points.append((px, py))

    draw.polygon(points, fill=_white(80), outline=_white(150))


@register_decoration('seed')
def draw_seed(draw, canvas_size, text_block, font_size, params):
    """小椭圆种子 + 嫩芽线。"""
    y_offset = params.get('y_offset', int(font_size * 0.55))
    size = params.get('size', int(font_size * 0.2))

    cx = canvas_size // 2
    cy = text_block['bottom'] + y_offset

    # 种子（椭圆）
    seed_w = int(size * 0.7)
    seed_h = int(size * 0.5)
    draw.ellipse(
        [(cx - seed_w, cy - seed_h), (cx + seed_w, cy + seed_h)],
        fill=_white(100),
        outline=_white(160),
        width=1
    )

    # 嫩芽（从顶部伸出的小弧线）
    sprout_h = int(size * 0.6)
    sprout_points = [
        (cx, cy - seed_h),
        (cx + int(size * 0.15), cy - seed_h - sprout_h // 2),
        (cx + int(size * 0.05), cy - seed_h - sprout_h),
    ]
    for i in range(len(sprout_points) - 1):
        draw.line([sprout_points[i], sprout_points[i + 1]], fill=_white(150), width=2)
