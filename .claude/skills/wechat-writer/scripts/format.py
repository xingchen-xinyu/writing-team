#!/usr/bin/env python3
"""
format.py — Convert WeChat Writer Markdown to WeChat Editor-compatible HTML.

Reads 02_Draft.md + 03_Production.md (for gold quotes and layout card),
outputs HTML with inline styles suitable for copy-paste into WeChat
Official Account editor.
"""
import json
import argparse
import re
import sys
import base64
from difflib import SequenceMatcher
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass


def render_inline(text, index_mapping=None):
    """Convert inline Markdown to HTML.

    Handles: **bold** → <strong>, *italic* → <em>,
             [[wiki links]] → HTML <a> links (if index_mapping provided) or plain text.
    """
    # Bold: **text** → <strong>text</strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic: *text* (but not **) — use negative lookbehind/lookahead for single *
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    # Wiki links: resolve to HTML <a> if index available, else plain text
    text = resolve_wiki_links(text, index_mapping)
    return text


def parse_gold_quotes(production_text):
    """Parse gold quote table from 03_Production.md content.

    Looks for '## 金句提炼' heading, then parses table rows.
    Returns list of (original, polished) tuples. Empty list if no table found.
    """
    quotes = []
    in_section = False
    in_table = False
    has_counter_col = False  # True if first column is # (counter/index)

    for line in production_text.split('\n'):
        stripped = line.strip()

        if stripped.startswith('##') and '金句提炼' in stripped:
            in_section = True
            continue
        if not in_section:
            continue
        # Exit at next ## heading or ---
        if stripped.startswith('## ') and '金句提炼' not in stripped:
            break
        if stripped == '---':
            break
        # Parse table: skip separator rows like |---|...|
        if stripped.startswith('|') and not re.match(r'^\|[\s\-:]+\|', stripped):
            if '原文' in stripped and '打磨后' in stripped:
                in_table = True
                cells = [c.strip() for c in stripped.split('|')[1:-1]]
                # If first column is a counter/index (like #), offset indices
                has_counter_col = len(cells) > 0 and cells[0] in ('#', '编号')
                continue
            if in_table:
                cells = [c.strip() for c in stripped.split('|')[1:-1]]
                orig_idx = 1 if has_counter_col else 0
                pol_idx = 2 if has_counter_col else 1
                if len(cells) >= pol_idx + 1:
                    original = cells[orig_idx].strip()
                    polished = cells[pol_idx].strip()
                    if original and original != '---':
                        quotes.append((original, polished))
    return quotes


def parse_layout_card(production_text):
    """Parse layout design card from 03_Production.md content.

    Returns dict with keys:
      strong_breaks: list of int (1-based index of --- to upgrade)
      opening_quote: bool
    """
    card = {"strong_breaks": [], "opening_quote": False}
    in_card = False
    in_strong = False
    in_opening = False

    for line in production_text.split('\n'):
        stripped = line.strip()

        if stripped.startswith('##') and '排版设计卡' in stripped:
            in_card = True
            continue
        if not in_card:
            continue
        if stripped.startswith('## ') and not stripped.startswith('###'):
            break
        if stripped == '---' and not in_strong and not in_opening:
            break

        if stripped.startswith('### 强视觉停顿'):
            in_strong = True
            in_opening = False
            continue
        if stripped.startswith('### 开头引语'):
            in_strong = False
            in_opening = True
            continue
        if stripped.startswith('### 相关阅读'):
            in_strong = False
            in_opening = False
            continue

        # Strong breaks: parse table, extract index from first column
        if in_strong and stripped.startswith('|') and not re.match(r'^\|[\s\-:]+\|', stripped):
            if '编号' in stripped or '位置' in stripped:
                continue
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if cells and cells[0].isdigit():
                card["strong_breaks"].append(int(cells[0]))

        # Opening quote: if table has any data row, set to True
        if in_opening and stripped.startswith('|') and not re.match(r'^\|[\s\-:]+\|', stripped):
            if '段落' not in stripped:
                card["opening_quote"] = True

    return card


def extract_images(content):
    """Extract all image references with context for insertion guide.

    Returns list of (alt_text, url, context) tuples.
    """
    images = []
    lines = content.split('\n')

    for i, line in enumerate(lines):
        m = re.match(r'^!\[(.+?)\]\((.+?)\)$', line.strip())
        if m:
            alt_with_size = m.group(1)
            alt = alt_with_size.split('|')[0]  # Strip size suffix like |400
            url = m.group(2)
            # Find preceding non-empty, non-heading line for context
            context = ""
            for j in range(i - 1, max(i - 4, -1), -1):
                prev = lines[j].strip()
                if prev and not prev.startswith('#') and not prev.startswith('---'):
                    context = prev[:30] + ('...' if len(prev) > 30 else '')
                    break
            images.append((alt, url, context))

    return images


# ── Reference resolution (wiki link → HTML <a> with placeholder URLs) ──

def load_article_index():
    """Load published article index and build title→metadata mapping for reference resolution.

    Reads knowledge/published_article_index.md relative to the skill root.
    Returns dict keyed by both article title and full filename.
    """
    skill_root = Path(__file__).resolve().parent.parent  # wechat-writer/
    index_path = skill_root / "knowledge" / "published_article_index.md"
    if not index_path.exists():
        return {}

    mapping = {}
    content = index_path.read_text(encoding='utf-8')

    for line in content.split('\n'):
        # Match table rows with wiki links in the second column.
        # Date column may be YYYYMMDD (8 digits) or MM-DD (5 chars).
        # Wiki link may be [[filename]] or [[filename|display]].
        m = re.match(r'\|\s*\S+\s*\|\s*\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', line)
        if not m:
            continue
        filename = m.group(1).strip()
        # filename always starts with YYYYMMDD_
        if not re.match(r'^\d{8}_', filename):
            continue
        date_str = filename[:8]
        # Extract article title: YYYYMMDD_Title… → Title…
        parts = filename.split('_', 1)
        article_title = parts[1] if len(parts) > 1 else filename

        # Truncate for concise placeholder URL segment
        short = article_title[:16] if len(article_title) > 16 else article_title
        placeholder_url = f'https://mp.weixin.qq.com/s/__REF_{date_str}_{short}__'

        entry = {
            'filename': filename,
            'date': date_str,
            'title': article_title,
            'placeholder_url': placeholder_url,
        }
        mapping[article_title] = entry
        mapping[filename] = entry  # support [[filename|alias]] lookup

    return mapping


def resolve_wiki_links(text, index_mapping):
    """Convert [[title]] or [[filename|alias]] wiki links to HTML <a> tags.

    Uses placeholder URLs so they are easy to find-and-replace in WeChat Editor.
    Falls back to plain display text when no index match is found.

    Args:
        text: inline Markdown text to process
        index_mapping: dict from load_article_index(), or None

    Returns:
        text with wiki links replaced by HTML <a> tags (or plain text on miss)
    """
    if not index_mapping:
        return re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)

    def replace_link(match):
        inner = match.group(1)

        # [[filename|display text]]
        if '|' in inner:
            parts = inner.split('|', 1)
            lookup = parts[0].strip()
            display = parts[1].strip()
        else:
            lookup = inner.strip()
            display = re.sub(r'^\d{8}_', '', lookup)

        # 1) Exact match (by title or by filename)
        info = None
        if lookup in index_mapping:
            info = index_mapping[lookup]
        else:
            # 2) Fuzzy match: try substring against article titles only
            for key, val in index_mapping.items():
                if key.startswith('202'):   # skip date-prefixed duplicate keys
                    continue
                if lookup in key or key in lookup:
                    if info is None:
                        info = val
                    elif info['filename'] != val['filename']:
                        # Ambiguous → bail out (plain text)
                        info = None
                        break

        if info:
            return (
                f'<a href="{info["placeholder_url"]}" '
                f'style="color:inherit; text-decoration:none;">{display}</a>'
            )
        return display

    return re.sub(r'\[\[([^\]]+)\]\]', replace_link, text)


def collect_references(content, index_mapping):
    """Scan content for [[…]] wiki links and return deduplicated reference metadata.

    Used to generate the 「引用文章链接替换清单」appended at the bottom of HTML.

    Returns:
        list of dicts: [{ref_text, article_title, date, placeholder_url}, …]
    """
    if not index_mapping:
        return []

    refs = []
    seen_urls = set()

    for match in re.finditer(r'\[\[([^\]]+)\]\]', content):
        inner = match.group(1)

        if '|' in inner:
            parts = inner.split('|', 1)
            lookup = parts[0].strip()
        else:
            lookup = inner.strip()

        # Resolve (same logic as resolve_wiki_links)
        info = None
        if lookup in index_mapping:
            info = index_mapping[lookup]
        else:
            for key, val in index_mapping.items():
                if key.startswith('202'):
                    continue
                if lookup in key or key in lookup:
                    if info is None:
                        info = val
                    elif info['filename'] != val['filename']:
                        info = None
                        break

        if info and info['placeholder_url'] not in seen_urls:
            seen_urls.add(info['placeholder_url'])
            refs.append({
                'ref_text': lookup,
                'article_title': info['title'],
                'date': info['date'],
                'placeholder_url': info['placeholder_url'],
            })

    return refs


# 微信编辑器对块级元素的内联样式有两条硬要求，缺省写法会被判违规：
#   1. text-align 只认 left / center / right。不写 → 解析为 start → 报
#      「文本对齐属性使用了非标准值」（文档 #2.6 text-align）。
#   2. line-height 必须带单位。写无单位比值（1.75）会被当成 px 与 font-size
#      比较 → 报「行高小于字体大小」（文档 #2.3.2 line-height-overlapping）。
# 逐处模板去补太散，这里在输出前统一规范化。
_WECHAT_BASE_FONT_SIZE = 16
_WECHAT_STANDARD_ALIGNS = ('left', 'center', 'right')


def normalize_inline_styles(html):
    """把块级元素的 inline style 规范成微信可校验的自解释写法。

    覆盖 <p> 与 <section>——两者缺 text-align 都会被判非标准值。

    - 缺 text-align → 补 left（等价于原默认值，不改视觉）
    - text-align 非 left/center/right → 回落 left
    - line-height 为无单位比值 → 按该段字号换算为 px
    """

    def fix_block(match):
        tag = match.group(1)
        style = match.group(2) if match.group(2) is not None else ''
        decls = []
        for raw in style.split(';'):
            raw = raw.strip()
            if not raw or ':' not in raw:
                continue
            key, val = raw.split(':', 1)
            decls.append((key.strip(), val.strip()))

        by_key = {k.lower(): (k, v) for k, v in decls}

        # 该段字号：显式字号优先，否则按正文基准
        font_size = _WECHAT_BASE_FONT_SIZE
        if 'font-size' in by_key:
            try:
                font_size = float(re.sub(r'[^0-9.]', '', by_key['font-size'][1]) or 0)
            except ValueError:
                font_size = _WECHAT_BASE_FONT_SIZE

        # 1) 对齐：缺失或非标准值一律回落 left
        if 'text-align' in by_key:
            key, val = by_key['text-align']
            if val.lower() not in _WECHAT_STANDARD_ALIGNS:
                by_key['text-align'] = (key, 'left')
        else:
            by_key['text-align'] = ('text-align', 'left')
            decls.append(by_key['text-align'])

        # 2) 行高：无单位比值换算为 px
        if 'line-height' in by_key:
            key, val = by_key['line-height']
            if re.fullmatch(r'[0-9]*\.?[0-9]+', val):
                px = 0 if font_size == 0 else round(float(val) * font_size)
                by_key['line-height'] = (key, f'{px}px')

        rebuilt = '; '.join(f'{by_key[k.lower()][0]}:{by_key[k.lower()][1]}' for k, _ in decls)
        return f'<{tag} style="{rebuilt}">'

    return re.sub(r'<(p|section)(?:\s+style="([^"]*)")?>', fix_block, html)


def markdown_to_html(content, gold_quotes, layout_card, index_mapping=None):
    """Convert Markdown content to WeChat-compatible HTML with inline styles.

    Args:
        content: Raw Markdown string from 02_Draft.md
        gold_quotes: List of (original, polished) tuples
        layout_card: Dict with strong_breaks (list of int), opening_quote (bool)
        index_mapping: Optional dict from load_article_index() for wiki-link→HTML-link resolution

    Returns:
        HTML string (body content only, no <html>/<body> wrapper)
    """
    lines = content.split('\n')
    blocks = []  # (type, data) tuples
    current_block = None
    current_text = []

    # Strip YAML frontmatter (published format): skip from opening --- to closing ---
    if lines and lines[0].strip() == '---':
        fm_end = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                fm_end = i
                break
        if fm_end != -1:
            lines = lines[fm_end + 1:]

    strong_breaks = set(layout_card.get('strong_breaks', []))
    opening_quote_handled = not layout_card.get('opening_quote', False)
    divider_count = 0
    in_meta = True  # True while skipping draft header (# Title + metadata blockquote + ---)

    in_bio = False

    def flush_paragraph():
        nonlocal current_block, current_text, in_bio
        if current_text:
            is_related = (
                current_block == 'blockquote'
                and current_text
                and '相关阅读' in (current_text[0].strip() if current_text else '')
            )
            if current_block == 'bookquote' or in_bio or is_related:
                text = '<br>\n'.join(current_text).strip()
            else:
                text = ' '.join(current_text).strip()
            if text:
                blocks.append((current_block or 'paragraph', text))
            current_text = []
            current_block = None

    for line in lines:
        stripped = line.strip()

        if in_meta:
            # Draft metadata: # Title + metadata blockquote + ---
            if stripped.startswith('# ') and not stripped.startswith('##'):
                continue
            if stripped.startswith('> ') and ('主笔' in stripped or '版本' in stripped or '日期' in stripped or '写作模式' in stripped):
                continue
            if not stripped:
                continue
            if stripped == '---':
                in_meta = False
                continue
            in_meta = False

        # Horizontal rule
        if stripped == '---':
            flush_paragraph()
            divider_count += 1
            is_strong = divider_count in strong_breaks
            blocks.append(('divider', is_strong))
            continue

        # Headings
        if stripped.startswith('## '):
            flush_paragraph()
            blocks.append(('heading', {'level': 2, 'text': stripped[3:].strip()}))
            continue
        if stripped.startswith('### '):
            flush_paragraph()
            blocks.append(('heading', {'level': 3, 'text': stripped[4:].strip()}))
            continue

        # Standalone images: ![alt|size](url)
        img_match = re.match(r'^!\[(.+?)\]\((.+?)\)$', stripped)
        if img_match:
            flush_paragraph()
            alt_with_size = img_match.group(1)
            alt = alt_with_size.split('|')[0]
            url = img_match.group(2)
            blocks.append(('image', {'alt': alt, 'url': url}))
            continue

        # Book excerpt (>> prefix) — verbatim quote from source material, styled distinctively
        if stripped.startswith('>> ') or stripped == '>>':
            if current_block != 'bookquote':
                flush_paragraph()
                current_block = 'bookquote'
            if stripped.startswith('>> '):
                current_text.append(stripped[3:])
            else:
                current_text.append('')  # empty continuation line
            continue

        # Blockquotes
        if stripped.startswith('> ') or stripped == '>':
            if current_block != 'blockquote':
                flush_paragraph()
                current_block = 'blockquote'
            if stripped.startswith('> '):
                current_text.append(stripped[2:])
            else:
                current_text.append('')  # empty continuation line
            continue

        # Empty line — flush
        if not stripped:
            flush_paragraph()
            continue

        # Regular paragraph
        if current_block != 'paragraph':
            flush_paragraph()
            current_block = 'paragraph'
        current_text.append(stripped)

    flush_paragraph()

    # Build gold quote text lookup set
    gold_quote_texts = set()
    for orig, polished in gold_quotes:
        if polished.strip():
            gold_quote_texts.add(polished.strip())
        if orig.strip():
            gold_quote_texts.add(orig.strip())

    GOLD_QUOTE_THRESHOLD = 0.45

    def is_gold_quote(block_text):
        if not gold_quote_texts:
            return False
        # Try exact substring first (fast path)
        for gq in gold_quote_texts:
            if gq and gq in block_text:
                return True
        # Fuzzy match: check if significant portion of a gold quote appears
        for gq in gold_quote_texts:
            if not gq or len(gq) < 6:
                continue
            ratio = SequenceMatcher(None, gq, block_text).ratio()
            if ratio >= GOLD_QUOTE_THRESHOLD:
                return True
        return False

    def is_bio_header(block):
        """Detect bio header: the personal intro paragraph at the beginning of the article."""
        if block[0] != 'paragraph':
            return False
        text = block[1]
        return '用教练方法和技术思维重构人生' in text

    def is_bio_footer_start(idx):
        """Detect bio footer: the divider right before the public account intro section."""
        if idx + 1 >= len(blocks):
            return False
        next_block = blocks[idx + 1]
        if next_block[0] == 'paragraph':
            text = next_block[1]
            if '编码人生.lab' in text:
                return True
        return False

    # Find the bio header block (should be the first paragraph if present)
    bio_header_idx = None
    for i, block in enumerate(blocks):
        if is_bio_header(block):
            bio_header_idx = i
            break

    # Find the last divider preceding bio footer
    bio_footer_start_idx = None
    for i, (btype, _bdata) in enumerate(blocks):
        if btype == 'divider' and is_bio_footer_start(i):
            bio_footer_start_idx = i
            break

    in_gold_marker = False
    html_parts = []

    for i, (btype, bdata) in enumerate(blocks):
        # Bio header: temporary in_bio flag, reset after this block
        is_bio_header_block = (bio_header_idx is not None and i == bio_header_idx)
        if is_bio_header_block:
            in_bio = True

        if bio_footer_start_idx is not None and i == bio_footer_start_idx:
            in_bio = True
            html_parts.append(
                '<section style="border-top:1px solid #dddddd; padding-top:15px; '
                'font-size:0; line-height:0;">&nbsp;</section>'
            )
            continue

        if btype == 'heading':
            # ⛔ Cut-off: editorial metadata — stop rendering
            heading_text = bdata.get('text', '')
            if '[金句标记]' in heading_text or '语流自检' in heading_text or '结构检查' in heading_text:
                break
            if bdata['level'] == 2:
                html_parts.append(
                    f'<p style="color:#FF6B35; font-weight:bold; font-size:17px; '
                    f'padding-top:20px; padding-bottom:8px; line-height:1.75;">'
                    f'{render_inline(bdata["text"], index_mapping)}</p>'
                )
            else:
                html_parts.append(
                    f'<p style="color:#FF6B35; font-weight:bold; font-size:15px; '
                    f'line-height:1.75; padding-bottom:8px;">'
                    f'{render_inline(bdata["text"], index_mapping)}</p>'
                )

        elif btype == 'divider':
            if bdata:  # Strong visual break
                html_parts.append(
                    '<section style="border-top:1px solid #FF6B35; padding-top:15px; '
                    'font-size:0; line-height:0;">&nbsp;</section>'
                )
            else:
                html_parts.append(
                    '<section style="border-top:1px solid #dddddd; padding-top:10px; '
                    'font-size:0; line-height:0;">&nbsp;</section>'
                )

        elif btype == 'image':
            html_parts.append(
                f'<p style="padding:15px 0; text-align:center;">'
                f'<img src="{bdata["url"]}" alt="{bdata["alt"]}">'
                f'</p>'
            )

        elif btype == 'blockquote':
            text = render_inline(bdata, index_mapping)
            if text.strip().startswith('相关阅读'):
                # Split by <br> — first line is "相关阅读" header, rest are links
                lines = bdata.split('<br>\n')
                header = lines[0].strip() if lines else '相关阅读'
                items = [l.strip() for l in lines[1:] if l.strip()]
                html_parts.append(
                    f'<p style="color:#888888; font-weight:bold; line-height:1.75; '
                    f'padding-bottom:8px;">📖 {render_inline(header, index_mapping)}</p>'
                )
                for item in items:
                    rendered = render_inline(item, index_mapping)
                    html_parts.append(
                        f'<p style="color:#888888; line-height:1.75; '
                        f'padding-bottom:4px;">{rendered}</p>'
                    )
            elif not opening_quote_handled and layout_card.get('opening_quote'):
                opening_quote_handled = True
                html_parts.append(
                    f'<p style="color:#888888; text-align:center; font-size:15px; '
                    f'line-height:1.5; padding-bottom:10px;">'
                    f'{text}</p>'
                )
            else:
                html_parts.append(
                    f'<p style="line-height:1.75; padding-bottom:6px;">'
                    f'{text}</p>'
                )

        elif btype == 'bookquote':
            html_parts.append(
                '<section style="border-left:3px solid #D4C5A0; '
                'padding:12px 16px; margin:16px 0; '
                'background:#F9F6F0;">'
            )
            for line in bdata.split('<br>\n'):
                stripped = line.strip()
                if stripped:
                    center_match = re.match(r'^<center>(.+)</center>$', stripped)
                    if center_match:
                        rendered = render_inline(center_match.group(1), index_mapping)
                        html_parts.append(
                            f'<p style="color:#3f3f3f; line-height:1.75; '
                            f'padding-bottom:6px; text-align:center;">{rendered}</p>'
                        )
                    else:
                        rendered = render_inline(stripped, index_mapping)
                        html_parts.append(
                            f'<p style="color:#3f3f3f; line-height:1.75; '
                            f'padding-bottom:6px;">{rendered}</p>'
                        )
                else:
                    html_parts.append(
                        '<p style="font-size:0; line-height:0; '
                        'padding-bottom:0;">&nbsp;</p>'
                    )
            html_parts.append('</section>')

        elif btype == 'paragraph':
            text = render_inline(bdata, index_mapping)
            is_gold = is_gold_quote(bdata) if not in_gold_marker else False

            if in_bio:
                html_parts.append(
                    f'<p style="color:#888888; '
                    f'line-height:1.75; padding-bottom:8px;">{text}</p>'
                )
            elif is_gold:
                html_parts.append(
                    f'<p style="font-weight:bold; '
                    f'line-height:1.75; padding-bottom:10px;">{text}</p>'
                )
            else:
                html_parts.append(
                    f'<p style="line-height:1.75; padding-bottom:6px;">{text}</p>'
                )

            # Reset in_bio after bio header paragraph (only header, not footer)
            if is_bio_header_block:
                in_bio = False

    return '\n'.join(html_parts)


def _embed_local_images(html, draft_dir):
    """Replace local image paths with base64 data URIs.

    Remote URLs (http/https) and existing data URIs pass through unchanged.
    Local paths (img/file.jpg) are read from disk and inlined as base64.
    """
    def _replace(match):
        src = match.group(1)
        alt = match.group(2)
        if re.match(r'^(https?:|data:)', src):
            return match.group(0)
        img_path = draft_dir / src
        if img_path.exists():
            try:
                b64 = base64.b64encode(img_path.read_bytes()).decode('ascii')
                ext = img_path.suffix.lower().lstrip('.')
                mime_map = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png', 'webp': 'webp', 'gif': 'gif'}
                mime = mime_map.get(ext, 'jpeg')
                return f'<img src="data:image/{mime};base64,{b64}" alt="{alt}">'
            except Exception:
                pass
        return match.group(0)

    return re.sub(r'<img src="([^"]+)" alt="([^"]*)">', _replace, html)


def process_format(data):
    """Core logic: read inputs, convert, write output, print image guide.

    Args:
        data: Dict with draft_file, production_file, output_path keys.
    """
    draft_path = Path(data['draft_file'])
    prod_path = Path(data.get('production_file', ''))
    output_path = Path(data['output_path'])

    if not draft_path.exists():
        raise FileNotFoundError(f"draft_file not found: {draft_path}")
    content = draft_path.read_text(encoding='utf-8')

    # Parse production file
    gold_quotes = []
    layout_card = {}
    if prod_path and prod_path.is_file() and prod_path.exists():
        prod_text = prod_path.read_text(encoding='utf-8')
        gold_quotes = parse_gold_quotes(prod_text)
        layout_card = parse_layout_card(prod_text)
        if gold_quotes:
            print(f"📝 从金句表格加载了 {len(gold_quotes)} 条金句")
        if layout_card.get('strong_breaks'):
            print(f"💪 强视觉停顿: 第 {', '.join(map(str, layout_card['strong_breaks']))} 个 ---")
        if layout_card.get('opening_quote'):
            print("📜 开头引语已标记")
    else:
        print("ℹ️ 未找到 03_Production.md，跳过金句和排版设计卡")

    # Load published article index for cross-reference resolution
    index_mapping = load_article_index()

    # Convert
    html = markdown_to_html(content, gold_quotes, layout_card, index_mapping)

    # 微信编辑器校验：补全 text-align、把无单位 line-height 换算为 px
    html = normalize_inline_styles(html)

    # ── Related reading check ──
    if '📖 相关阅读' not in html:
        print("ℹ️ 正文中未检测到「> 相关阅读」引用块，如有旧文可关联请补充")

    # Embed local images as base64 so they display in any browser
    html = _embed_local_images(html, draft_path.parent)

    # ── Cross-reference log (terminal only) ──
    refs = collect_references(content, index_mapping)
    if refs:
        print(f"📎 检测到 {len(refs)} 处文章引用，占位链接（在 HTML 中搜索 __REF_ 替换）：")
        for idx, r in enumerate(refs, 1):
            date_display = f"{r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:8]}"
            print(f"   {idx}. __REF_{r['date']}_{r['article_title'][:16]}__ → 《{r['article_title']}》({date_display})")

    # Wrap in a minimal document for browser display
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>微信发布稿</title>
</head>
<body style="max-width:680px; margin:0 auto; padding:20px; font-size:16px; color:#3f3f3f;">
{html}
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_html, encoding='utf-8')
    print(f"✅ HTML 已生成: {output_path}")

    # Print image insertion guide
    images = extract_images(content)
    if images:
        print("\n📷 图片插入清单:")
        for idx, (alt, url, context) in enumerate(images, 1):
            location = f"位于「{context}」段落后" if context else "位置未识别"
            print(f"  {idx}. {alt} → {location}")
        print(f"\n  共 {len(images)} 张图片，请在微信编辑器中依次上传替换。")
    else:
        print("\n📷 未检测到图片。")


def main():
    parser = argparse.ArgumentParser(
        description="Convert WeChat Writer Markdown to WeChat Editor HTML"
    )
    parser.add_argument(
        "input_json",
        help="Path to JSON file with draft_file, production_file, output_path"
    )
    args = parser.parse_args()

    json_path = Path(args.input_json).resolve()
    json_dir = json_path.parent

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Resolve relative paths relative to JSON file directory
    for key in ('draft_file', 'production_file'):
        raw = data.get(key, '')
        if raw:
            p = Path(raw)
            if not p.is_absolute():
                data[key] = str(json_dir / p)

    output_raw = data.get('output_path', '')
    if output_raw:
        p = Path(output_raw)
        if not p.is_absolute():
            data['output_path'] = str(json_dir / p)

    process_format(data)


if __name__ == "__main__":
    main()
