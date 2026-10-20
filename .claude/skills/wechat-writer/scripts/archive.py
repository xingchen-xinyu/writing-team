#!/usr/bin/env python3
import json
import argparse
import shutil
import re
import subprocess
import sys
# Fix Windows GBK encoding for emoji output
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass
import traceback
from pathlib import Path
from datetime import datetime

# ── Shared helpers (single source for Obsidian CLI + workspace paths) ──
_SHARED = Path(__file__).resolve().parent.parent.parent.parent.parent / ".claude" / "scripts"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

# ── Ensure scripts directory is in sys.path (for format import) ──
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import obsidian_helpers as _obs

def obsidian_move(src, dest):
    """Move a file using Obsidian CLI to preserve links."""
    src_rel = _obs.get_obsidian_path(src)
    dest_rel = _obs.get_obsidian_path(dest)
    ok, err = _obs.run_obsidian_cmd(["move", f"path={src_rel}", f"to={dest_rel}"])
    if not ok:
        print(f"⚠️ CLI Move failed: {err}")
    return ok

def get_knowledge_dir():
    # knowledge/ is at Skills/wechat-writer/knowledge (relative to repo root)
    skill_root = Path(__file__).resolve().parent.parent  # wechat-writer/
    return skill_root / "knowledge"

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def yaml_escape(value):
    """Escape text for YAML double-quoted string values."""
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"')

def to_vault_path(path_value, vault_dir_name):
    """Normalize path into vault-root based relative path.

    Paths are relative to the Obsidian vault root (where .obsidian/ resides).
    The vault_dir_name is used only to strip an accidentally doubled prefix.

    Example: published/img/cover-main.jpg -> published/img/cover-main.jpg
    """
    raw = "" if path_value is None else str(path_value).strip()
    if not raw:
        return ""

    normalized = raw.replace("\\", "/").lstrip("/")

    # Keep explicit URL-like values untouched.
    if "://" in normalized:
        return normalized

    # Strip accidentally doubled vault name prefix (if any).
    # Correct path: published/img/cover.jpg (vault-relative).
    prefix = f"{vault_dir_name}/"
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix):]

    return normalized

def pick_cover_image(img_dir):
    """Pick cover image from archived image folder.

    Priority:
    1. Exact match: cover-combined.jpg
    2. Exact match: cover-main.jpg
    3. Partial match: *cover-combined*
    4. Partial match: *cover-main*
    """
    if not img_dir.exists() or not img_dir.is_dir():
        return None

    # 1. Try exact matches (simple naming preference)
    exact_priorities = ["cover-combined.jpg", "cover-main.jpg"]
    for name in exact_priorities:
        f = img_dir / name
        if f.exists():
            return f

    # 2. Fallback to sorting and partial match
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    image_files = sorted(
        [
            p for p in img_dir.iterdir()
            if p.is_file() and p.suffix.lower() in image_exts
        ],
        key=lambda p: p.name.lower()
    )

    if not image_files:
        return None

    priorities = ("cover-combined", "cover-main")
    for keyword in priorities:
        for file_path in image_files:
            if keyword in file_path.name.lower():
                return file_path

    return None

def update_index(title, excerpt, filename, card_data=None, frontmatter_tags=None):
    """更新 published_article_index.md

    支持两种格式:
    - 新格式 (8列): | 日期 | 标题 | 系列 | 写作模式 | 类型 | 标签 | 摘要 | 卡片 |
    - 旧格式 (2列): | 标题 | 摘要 |  (向后兼容)

    当 card_data 存在时使用新格式，否则退回旧格式。
    """
    index_path = get_knowledge_dir() / "published_article_index.md"
    if not index_path.exists():
        print(f"Warning: Index file {index_path} not found.")
        return

    link = f"[[{filename}]]"
    month_header = f"## {datetime.now().strftime('%Y-%m')}"
    date_str = filename[:8]

    use_new_format = bool(card_data)
    tags_list = frontmatter_tags or []

    if use_new_format:
        series = card_data.get("series", "")
        writing_mode = card_data.get("writing_mode", "")
        article_type = card_data.get("article_type", "")
        tags_str = ", ".join(tags_list)
        card_filename = f"Card_{filename}.md"
        card_cell = f"[→](article_cards/{card_filename})"
        line = f"| {date_str} | {link} | {series} | {writing_mode} | {article_type} | {tags_str} | {excerpt} | {card_cell} |"
        NEW_HEADER = "| 日期 | 标题 | 系列 | 写作模式 | 类型 | 标签 | 摘要 | 卡片 |"
        NEW_SEPARATOR = "| --- | --- | --- | --- | --- | --- | --- | --- |"
    else:
        line = f"| {link} | {excerpt} |"
        NEW_HEADER = "| 标题 | 摘要 |"
        NEW_SEPARATOR = "| --- | --- |"

    try:
        content = index_path.read_text(encoding="utf-8")
        if link in content:
            print(f"Index already contains entry: {link}")
            return

        lines = content.splitlines()

        if month_header not in content:
            insert_pos = 0
            for i, l in enumerate(lines):
                if l.strip().startswith("## 20"):
                    insert_pos = i
                    break
            new_section = f"\n{month_header}\n\n{NEW_HEADER}\n{NEW_SEPARATOR}\n{line}\n"
            lines.insert(insert_pos, new_section)
            index_path.write_text("\n".join(lines), encoding="utf-8")
            print(f"Created new month section in index: {index_path}")
        else:
            for i, l in enumerate(lines):
                if l.strip() == month_header:
                    for j in range(i + 1, min(i + 30, len(lines) - 1)):
                        cur = lines[j].strip()
                        nxt = lines[j + 1].strip()
                        if not cur.startswith("|") or not nxt.startswith("|"):
                            continue
                        if "-" not in nxt:
                            continue
                        # C1: If using new format but existing section is old 2-column format, migrate header/separator
                        if use_new_format:
                            sep_line = lines[j + 1].strip()
                            col_count = sep_line.count("---")
                            if col_count == 2:
                                lines[j] = NEW_HEADER
                                lines[j + 1] = NEW_SEPARATOR
                        lines.insert(j + 2, line)
                        index_path.write_text("\n".join(lines), encoding="utf-8")
                        print(f"Updated index: {index_path}")
                        return

            with index_path.open("a", encoding="utf-8") as f:
                f.write(f"\n{line}\n")

    except Exception as e:
        print(f"Error updating index: {e}")
        traceback.print_exc()

def strip_frontmatter(content):
    if content.startswith("---\n"):
        parts = content.split("\n---\n", 1)
        if len(parts) >= 2: return parts[1].lstrip()
    return content

def strip_h1_title(content):
    """去除开头的一级标题（如 # 02_Draft: xxx）"""
    lines = content.split('\n')
    if lines and lines[0].startswith('# '):
        return '\n'.join(lines[1:]).lstrip()
    return content

def strip_editorial_metadata(content):
    """Remove editorial metadata sections from draft before publishing.

    Sections removed: [金句标记], 语流自检, 结构检查, and their content.
    These are internal workflow artifacts, not article content.

    Also removes trailing --- separators that preceded these sections,
    leaving the article body clean for publishing.
    """
    # Pattern: blank line + --- + blank line + ## [金句标记] or ## 语流自检 or ## 结构检查
    # Remove everything from that point to end of file
    cleaned = re.sub(
        r'\n+---\n+\s*##\s*\[(?:金句标记|语流自检|结构检查)\].*$',
        '',
        content,
        flags=re.DOTALL
    )
    return cleaned.rstrip() + '\n'


def strip_draft_metadata(content):
    """去除 Draft 文件开头的元信息块（仅当包含特定元数据关键词时才删除）

    元数据块特征:
    > **版本**: v2
    > **主笔**: 冰清
    > ...

    ---
    """
    lines = content.split('\n')
    if not lines:
        return content

    # 1. 预读开头的引用块
    i = 0
    quote_lines = []
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('>'):
            quote_lines.append(line)
            i += 1
        elif line == '':
            i += 1 # 允许引用块中间有空行（虽然标准Markdown引用块通常连续，但容错）
        else:
            break # 遇到非引用非空行，停止

    # 2. 检查是否包含元数据关键词
    # 必须包含至少一个强特征词，才认为是Draft Metadata
    quote_text = "".join(quote_lines)
    metadata_keywords = ["**版本**", "**主笔**", "**创建时间**", "**Version**", "**Author**",
                         "主笔:", "版本:", "创建时间:", "Author:", "写作模式:"]
    is_metadata = any(keyword in quote_text for keyword in metadata_keywords)

    if not is_metadata:
        return content # 认为是正文引用，不作处理

    # 3. 如果确认是元数据，执行删除逻辑
    # i 此时停留在引用块之后的第一行（非空行，或者文件末尾）

    # 检查是否紧跟分隔线
    # 回溯一下，因为上面的循环可能跳过了引用块后的空行
    # 我们重新定位删除的截止点

    delete_end_index = 0

    # 重新扫描一遍确定精确的删除边界
    j = 0
    has_seen_quote = False
    while j < len(lines):
        line = lines[j].strip()
        if line.startswith('>'):
            has_seen_quote = True
            j += 1
        elif line == '':
            j += 1
        elif line == '---':
            # 只有在已经看到过引用块的情况下，遇到分隔线才认为是元数据区的结束
            if has_seen_quote:
                j += 1 # 吞掉分隔线
                # 再吞掉分隔线后的空行
                while j < len(lines) and lines[j].strip() == '':
                    j += 1
                delete_end_index = j
                break
            else:
                # 没看到引用块就遇到了分隔线？不应该发生，保留原样
                return content
        else:
            # 遇到正文了，还没遇到分隔线？
            # 这种情况下，也许没有分隔线，只是引用块结束。
            # 为了安全，只在有分隔线的情况下才删除？
            # 或者，只要确认是元数据块，就删除引用块部分。
            # 按照 io_schema，Draft 头部通常有 ---。
            # 这里采取激进但基于内容的策略：只要确认是元数据块，就删除到当前位置。
            delete_end_index = j
            break

    return '\n'.join(lines[delete_end_index:])

def _read_bio_body():
    """读取 bio_footer.md 去除 YAML frontmatter 后的正文，返回原始文本。"""
    skill_root = Path(__file__).resolve().parent.parent  # wechat-writer/
    bio_path = skill_root / "references" / "bio_footer.md"

    if not bio_path.exists():
        print("⚠️ bio_footer.md not found.")
        return None

    raw = bio_path.read_text(encoding='utf-8')

    if raw.startswith("---\n"):
        parts = raw.split("\n---\n", 1)
        if len(parts) >= 2:
            raw = parts[1].lstrip()

    return raw


def load_bio_header():
    """读取文首星辰个人介绍，从 bio_footer.md 中提取「文章开头」区块。
    返回一句话介绍纯文本，不含 markdown 标记。"""
    body = _read_bio_body()
    if body is None:
        return None

    # 提取「# 文章开头」和下一个「# 文章结尾」之间的内容
    m_start = re.search(r'#\s*文章开头[^\n]*\n', body)
    m_end = re.search(r'#\s*文章结尾[^\n]*\n', body)

    if not m_start:
        print("⚠️ bio_footer.md missing '# 文章开头' section, skipping bio header.")
        return None

    start_pos = m_start.end()
    end_pos = m_end.start() if m_end else len(body)
    section = body[start_pos:end_pos].strip()

    # 去掉 --- 分割线和空行，只保留正文
    lines = [l.strip() for l in section.split('\n') if l.strip() and l.strip() != '---']
    if not lines:
        print("⚠️ bio_footer.md header section is empty, skipping bio header.")
        return None

    return '\n\n'.join(lines)


def load_bio_footer():
    """读取文末编码人生.lab 公众号介绍，从 bio_footer.md 中提取「文章结尾」区块。
    qrcode_url 从 frontmatter 注入到正文图片链接中，只需改一处。"""
    body = _read_bio_body()
    if body is None:
        return None

    # 提取「# 文章结尾」之后的内容
    m_start = re.search(r'#\s*文章结尾[^\n]*\n', body)

    if not m_start:
        print("⚠️ bio_footer.md missing '# 文章结尾' section, skipping bio footer.")
        return None

    raw = body[m_start.end():].strip()

    # 清掉正文前的空行（保留 --- 分割线，它是 footer 的视觉分隔符）
    raw = raw.lstrip('\n').lstrip()

    # Ensure each line renders as a separate paragraph in HTML
    # by adding blank lines between lines (standard markdown paragraph separation)
    lines = raw.split('\n')
    raw = '\n\n'.join(line.strip() for line in lines if line.strip())

    # 用 frontmatter 中的 qrcode_url 替换正文中的图片链接
    # Parse frontmatter again to extract qrcode_url
    skill_root = Path(__file__).resolve().parent.parent
    bio_path = skill_root / "references" / "bio_footer.md"
    raw_file = bio_path.read_text(encoding='utf-8')
    qrcode_url = ""
    if raw_file.startswith("---\n"):
        parts = raw_file.split("\n---\n", 1)
        if len(parts) >= 2:
            for line in parts[0].split("\n"):
                if line.startswith("qrcode_url:"):
                    qrcode_url = line.split(":", 1)[1].strip().strip('"')
                    break
    if qrcode_url:
        raw = re.sub(r'!\[.*?\]\(https?://[^)]+\)', f'![关注编码人生.lab]({qrcode_url})', raw)

    return raw


def load_related_reading(project_dir):
    """从 03_Production.md 提取「相关阅读」列表，生成 > 相关阅读 引用块。
    返回 None 表示无相关阅读或 production 文件不存在。"""
    prod_file = project_dir / "03_Production.md"
    if not prod_file.exists():
        return None

    content = prod_file.read_text(encoding='utf-8')
    in_section = False
    links = []

    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('### 相关阅读'):
            in_section = True
            continue
        if in_section:
            if stripped.startswith('###') or stripped.startswith('##'):
                break  # next section, stop
            match = re.match(r'^- \[\[(.+?)\]\]', stripped)
            if match:
                links.append(f"[[{match.group(1)}]]")

    if not links:
        return None

    block = "> 相关阅读\n"
    for link in links:
        block += f"> {link}\n"
    return block


def generate_article_card(card_data, target_filename):
    """Generate L2 article index card from card data.

    Args:
        card_data: dict from _temp_archive.json 'card' field, or None
        target_filename: e.g. '20260624_微习惯_种子种下去了'
    """
    if not card_data:
        return

    cards_dir = get_knowledge_dir() / "article_cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    card_path = cards_dir / f"Card_{target_filename}.md"
    if card_path.exists():
        print(f"Card already exists: {card_path}")
        return

    def esc(val):
        """Escape pipe characters in table cells."""
        return "" if val is None else str(val).replace("|", "\\|")

    series = card_data.get("series", "")
    article_type = card_data.get("article_type", "")
    writing_mode = card_data.get("writing_mode", "")
    core_insight = card_data.get("core_insight", "")
    key_scenes = card_data.get("key_scenes", [])
    metaphor_system = card_data.get("metaphor_system", "")
    characters = card_data.get("characters", [])
    framework = card_data.get("framework", "")
    golden_quotes = card_data.get("golden_quotes", [])
    image_plan = card_data.get("image_plan", [])

    title = card_data.get("title", "")
    date_str = card_data.get("date", target_filename[:8])
    slug = card_data.get("slug", "")
    tags = card_data.get("tags", [])
    excerpt = card_data.get("excerpt", "")

    td = card_data.get("title_design") or {}
    td_selected = td.get("selected") or {}
    td_alt = td.get("alternative_paths", [])

    lines = []
    safe_title = title.replace("#", "&#35;")
    lines.append(f"# 文章索引卡: {safe_title}")
    lines.append("")
    lines.append("## 基本信息")
    lines.append("| 字段 | 值 |")
    lines.append("|------|-----|")
    lines.append(f"| 发布日期 | {date_str} |")
    lines.append(f"| slug | {esc(slug)} |")
    lines.append(f"| 系列 | {esc(series)} |")
    lines.append(f"| 写作模式 | {esc(writing_mode)} |")
    lines.append(f"| 文章类型 | {esc(article_type)} |")
    tags_str = ", ".join(tags) if tags else ""
    lines.append(f"| 标签 | {esc(tags_str)} |")
    lines.append(f"| 摘要 | {esc(excerpt)} |")
    lines.append("")
    lines.append("## 内容概要")
    lines.append("### 核心洞察")
    lines.append(esc(core_insight) if core_insight else "（无）")
    lines.append("")
    lines.append("### 关键场景")
    if key_scenes:
        for s in key_scenes:
            lines.append(f"- {esc(s)}")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("### 隐喻体系")
    lines.append(esc(metaphor_system) if metaphor_system else "（无）")
    lines.append("")
    lines.append("### 人物/关系")
    if characters:
        for c in characters:
            lines.append(f"- {esc(c)}")
    else:
        lines.append("无")
    lines.append("")
    lines.append("### 方法论/框架")
    lines.append(esc(framework) if framework else "无")
    lines.append("")

    lines.append("## 标题设计")
    if td_selected:
        path = td_selected.get("path", "")
        stitle = td_selected.get("title", "")
        c_val = td_selected.get("c", "")
        e_val = td_selected.get("e", "")
        v_val = td_selected.get("v", "")
        lines.append(f"| 路径 | 选定标题 | C | E | V |")
        lines.append(f"|------|---------|---|---|---|")
        lines.append(f"| {esc(path)} | {esc(stitle)} | {c_val} | {e_val} | {v_val} |")
        if td_alt:
            lines.append(f"备选路径：{'、'.join(esc(p) for p in td_alt)}")
    else:
        lines.append("（无标题设计数据）")
    lines.append("")

    lines.append("## 金句")
    if golden_quotes:
        for q in golden_quotes:
            lines.append(f"- {esc(q)}")
    else:
        lines.append("（无）")
    lines.append("")

    lines.append("## 配图方案")
    if image_plan:
        lines.append("| # | 画面主题 | 位置 | IP 形象 |")
        lines.append("|---|---------|------|---------|")
        for ip in image_plan:
            seq = ip.get("seq", "")
            theme = ip.get("theme", "")
            position = ip.get("position", "")
            has_ip = ip.get("has_ip", False)
            ip_style = ip.get("ip_style", "")
            ip_cell = f"有（{esc(ip_style)}）" if has_ip else "无"
            lines.append(f"| {esc(seq)} | {esc(theme)} | {esc(position)} | {ip_cell} |")
    else:
        lines.append("（无配图数据）")
    lines.append("")

    card_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Article card generated: {card_path}")


def _copy_and_verify(src_dir, dst_dir):
    """Copy project directory to archive, verify integrity, then delete source.

    Used as a fallback when shutil.move fails on Windows due to file locks.
    Only deletes the source after confirming the copy is complete.
    """
    src = Path(src_dir)
    dst = Path(dst_dir)

    # Collect source files
    src_files = []
    for item in src.rglob('*'):
        if item.is_file():
            src_files.append(item.relative_to(src))

    if not src_files:
        print(f"⚠️ No files to copy from {src_dir}")
        return

    # Copy file by file
    copied = 0
    failed = []
    for rel_path in src_files:
        src_file = src / rel_path
        dst_file = dst / rel_path
        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied += 1
        except Exception as e:
            failed.append((rel_path, str(e)))

    # Verify
    dst_files = []
    for item in dst.rglob('*'):
        if item.is_file():
            dst_files.append(item.relative_to(dst))

    mismatch = len(src_files) - len(dst_files)

    if failed:
        print(f"⚠️ Copy partially failed: {copied}/{len(src_files)} copied, {len(failed)} failures")
        for path, err in failed:
            print(f"   - {path}: {err}")
        print(f"⚠️ Source directory NOT deleted: {src_dir}")
        return

    if mismatch != 0:
        print(f"⚠️ Copy verification failed: source has {len(src_files)} files, dest has {len(dst_files)}")
        print(f"⚠️ Source directory NOT deleted: {src_dir}")
        return

    # Copy verified — safe to delete source
    shutil.rmtree(str(src_dir))
    print(f"   Verified {len(src_files)} files, source deleted.")


def process_archive(data, no_move=False, move_only=False, skip_html=False):
    source_file = Path(data.get('source_file', ''))
    fm = data.get('frontmatter', {})

    # ── Source file validation (prevent empty publish) ──
    if not move_only:  # publish mode: strict validation
        if not source_file.exists():
            print(f"❌ 错误: source_file 不存在: {source_file}")
            print(f"   请检查 _temp_archive.json 中 source_file 的路径是否正确。")
            print(f"   source_file 应相对于 JSON 所在目录（如 02_Draft.md），不应带 To-be-used/ 前缀。")
            sys.exit(1)
        if "Project_" not in str(source_file):
            print(f"❌ 错误: source_file 不在 Project_* 目录下: {source_file}")
            print(f"   请确认文件在 To-be-used/Project_[Title]/ 目录中。")
            sys.exit(1)
        if source_file.stat().st_size == 0:
            print(f"❌ 错误: source_file 为空: {source_file}")
            sys.exit(1)
    else:  # move-only mode: relaxed validation (draft may already be published)
        project_dir = source_file.parent
        if not project_dir.exists():
            print(f"❌ 错误: 项目目录不存在: {project_dir}")
            print(f"   无法执行搬迁。请确认项目目录路径正确。")
            sys.exit(1)

    # ── move-only mode: skip everything except project migration ──
    if move_only:
        # Security: validate source is under To-be-used/ before allowing move
        workspace_root = _obs.get_workspace_root()
        allowed_parent = (workspace_root / "To-be-used").resolve()
        project_dir = source_file.parent if source_file.exists() else None
        if project_dir:
            try:
                current_parent = project_dir.parent.resolve()
            except Exception:
                traceback.print_exc()
                current_parent = None
            if current_parent != allowed_parent:
                print(f"⚠️ Security Violation: project '{current_parent}' not under '{allowed_parent}'. Aborted.")
                return
        if source_file.exists():
            _migrate_project(source_file, workspace_root)
        else:
            print(f"⚠️ Source file {source_file} not found, cannot migrate.")
        _cleanup_history(workspace_root)
        return

    # --- Security Validation (Move to top) ---
    # Ensure source file is inside 'To-be-used/Project_*' before reading/writing anything.
    workspace_root = _obs.get_workspace_root()
    workspace_name = workspace_root.name

    allowed_parent = (workspace_root / "To-be-used").resolve()

    if source_file.exists():
        project_dir = source_file.parent
        try:
            current_parent = project_dir.parent.resolve()
        except Exception:
            traceback.print_exc()
            current_parent = None

        if current_parent != allowed_parent:
            print(f"⚠️ Security Violation: Source file is in '{current_parent}', but must be in '{allowed_parent}' to be archived.")
            print("   Operation aborted to prevent unauthorized access or data loss.")
            return
    else:
        project_dir = source_file.parent
        try:
            current_parent = project_dir.resolve()
            if not str(current_parent).startswith(str(allowed_parent)):
                print(f"⚠️ Security Violation: Source path '{current_parent}' is not under '{allowed_parent}'. Aborted.")
                return
        except Exception:
            traceback.print_exc()
            print("⚠️ Could not validate source path. Aborted for safety.")
            return

    title = fm.get('title', 'Untitled')
    safe_title = sanitize_filename(title)

    target_dir = workspace_root / "published"
    target_dir.mkdir(parents=True, exist_ok=True)

    publish_date = datetime.now()  # snapshot for _cleanup_history to avoid midnight drift
    date_prefix = publish_date.strftime('%Y%m%d')
    target_filename = f"{date_prefix}_{safe_title}"
    target_file = target_dir / f"{target_filename}.md"

    # Handle same-day name collision (e.g. rewrite or multi-article same topic)
    if target_file.exists():
        counter = 2
        while target_file.exists():
            target_filename = f"{date_prefix}_{safe_title}_{counter}"
            target_file = target_dir / f"{target_filename}.md"
            counter += 1
    
    # Read & Clean
    if source_file.exists():
        content = source_file.read_text(encoding='utf-8')
        content = strip_frontmatter(content)
        content = strip_h1_title(content)
        content = strip_draft_metadata(content)
        content = strip_editorial_metadata(content)
    else:
        content = ""
        print(f"Warning: Source file {source_file} not found. Creating empty published file.")

    # Prepend bio header (personal intro) at the beginning of the article
    bio_header = load_bio_header()
    if bio_header:
        content = bio_header + "\n\n" + content
        print("📝 Bio header prepended to article.")

    # Append related reading links from 03_Production.md (before bio footer)
    if source_file.exists():
        related_block = load_related_reading(source_file.parent)
        if related_block:
            # Avoid duplicate injection
            if "> 相关阅读" not in content:
                content = content.rstrip() + "\n\n" + related_block
                print("📖 Related reading links appended from 03_Production.md.")
            else:
                print("ℹ️ Related reading already present in content, skipping.")
        else:
            print("ℹ️ No related reading found in 03_Production.md, skipping.")

    # Append bio footer (personal IP intro) from centralized config — always last
    bio_footer = load_bio_footer()
    if bio_footer:
        # Check if bio footer is already in content (e.g. already appended in Stage 3)
        # Use first two non-empty lines as signature to avoid false match with "---" separators
        bio_lines = [l.strip() for l in bio_footer.strip().split('\n') if l.strip()]
        bio_sig = '\n'.join(bio_lines[:2]) if len(bio_lines) >= 2 else bio_lines[0] if bio_lines else ""
        if bio_sig and bio_sig not in content:
            content = content.rstrip() + "\n\n" + bio_footer
            print("📝 Bio footer appended to article.")
        else:
            print("ℹ️ Bio footer already present in content, skipping.")

    # Move img/ folder to published/ and resolve cover path.
    # Keep explicit cover if provided by upstream input.
    cover_path = to_vault_path(fm.get('cover', ''), workspace_name)
    excerpt = "" if fm.get('excerpt') is None else str(fm.get('excerpt')).strip()
    if len(excerpt) > 120:
        print(f"⚠️ Excerpt length is {len(excerpt)} (>120). Please shorten it in Stage 3.")
    if source_file.exists():
        project_dir = source_file.parent
        img_dir = project_dir / "img"

        if img_dir.exists() and img_dir.is_dir():
            # Keep fixed output directory name for plugin config compatibility.
            img_dest = target_dir / "img"

            try:
                # Preserve previous published/img if present, then replace with new one.
                if img_dest.exists():
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup = target_dir / f"img_prev_{timestamp}"
                    counter = 1
                    while backup.exists():
                        backup = target_dir / f"img_prev_{timestamp}_{counter}"
                        counter += 1
                    shutil.move(str(img_dest), str(backup))
                    print(f"📦 Existing published/img moved to backup: {backup}")

                shutil.copytree(str(img_dir), str(img_dest))
                print(f"🖼️  Copied images to: {img_dest}")

                # Auto-pick only when cover was not explicitly provided.
                if not cover_path:
                    cover_file = pick_cover_image(img_dest)
                    if cover_file:
                        relative_path = cover_file.relative_to(workspace_root).as_posix()
                        cover_path = to_vault_path(relative_path, workspace_name)
                        print(f"🖼️  Cover selected: {cover_path}")
                    else:
                        print("⚠️ No cover-combined/cover-main found. cover stays empty.")
                else:
                    print(f"ℹ️ Keep explicit cover from input: {cover_path}")
            except Exception as e:
                # Non-blocking: publish text first even if image move fails.
                print(f"⚠️ Image archive failed, continue without auto cover: {e}")
                traceback.print_exc()

    # Generate properties dict
    props = {
        "title": title,
        "date": fm.get('date', datetime.now().strftime('%Y-%m-%d')),
        "slug": fm.get('slug', ''),
        "excerpt": excerpt,
        "cover": cover_path,
        "tags": fm.get('tags', []),
        "status": "published"
    }

    # Write & Update Properties
    # If Obsidian CLI is available, we attempt CLI-Native update
    cli_ok = shutil.which("obsidian") is not None
    cli_success = False
    
    if cli_ok and _obs.is_obsidian_reachable(target_file):
        # 1. Write content with empty FM shell
        target_file.write_text(f"---\n---\n{content}", encoding='utf-8')
        # 2. Set properties via CLI (Checking if ALL properties were set correctly)
        if _obs.set_obsidian_properties(target_file, props):
            print(f"🚀 Published article to: {target_file} (CLI-Native)")
            cli_success = True
        else:
            print(f"⚠️ CLI Property sync failed. Falling back to Legacy metadata writing...")
            cli_success = False

    if not cli_success:
        # Legacy / Fallback: Manual YAML-like construction
        # This is the 'Source of Truth' for metadata safety.
        new_content = f"""---
title: "{yaml_escape(title)}"
date: "{props['date']}"
slug: "{yaml_escape(props['slug'])}"
excerpt: "{yaml_escape(props['excerpt'])}"
cover: "{yaml_escape(props['cover'])}"
tags: {json.dumps(props['tags'])}
status: published
---
{content}"""
        target_file.write_text(new_content, encoding='utf-8')
        if cli_ok:
            print(f"🚀 Published article to: {target_file} (Fallback-Mode)")
        else:
            print(f"🚀 Published article to: {target_file} (Legacy-Mode)")
    
    # Update Index (with optional card data for new wide format)
    update_index(title, excerpt, target_filename, data.get("card"), fm.get("tags", []))

    # Generate L2 article index card (if card data provided in JSON)
    card_data = dict(data.get("card") or {})
    if card_data:
        try:
            # Pass frontmatter-level fields needed in the card
            card_data["title"] = title
            card_data["date"] = props["date"]
            card_data["slug"] = props["slug"]
            card_data["tags"] = props["tags"]
            card_data["excerpt"] = excerpt
            generate_article_card(card_data, target_filename)
        except Exception as e:
            print(f"⚠️ 文章卡片生成失败（发布稿已保存，可稍后手动补）: {e}")
            traceback.print_exc()

    # ── Generate HTML (between publish and migrate) ──
    if not no_move and not skip_html:
        try:
            from format import process_format
            _prod_file = project_dir / '03_Production.md' if project_dir else None
            _html_output = target_dir / f'{target_filename}.html'
            print(f"📄 生成 HTML...")
            process_format({
                'draft_file': str(target_file),
                'production_file': str(_prod_file) if _prod_file and _prod_file.exists() else '',
                'output_path': str(_html_output)
            })
        except FileNotFoundError as e:
            print(f"⚠️ HTML 生成跳过（文件缺失）: {e}")
        except Exception as e:
            print(f"⚠️ HTML 生成失败（发布稿已保存，可稍后手动生成）: {e}")
            traceback.print_exc()

    # Archive Project Folder (skip if --no-move)
    if not no_move:
        _migrate_project(source_file, workspace_root)
        _cleanup_history(workspace_root, publish_date)

    # Memory Suggestion
    print("\n🧠 **Memory Suggestion** (Please update knowledge/team_memory.md):")
    print(f"- [{datetime.now().strftime('%Y-%m-%d')}] [Experience] Completed {title}.")


def _migrate_project(source_file, workspace_root):
    """Move project directory to conductor/archive/. Must be called last — after all
    other Stage 4 steps (publish, format.py, etc.) have finished writing files."""
    cli_ok = shutil.which("obsidian") is not None

    if not source_file.exists():
        print(f"⚠️ Source file {source_file} not found, cannot migrate.")
        return

    project_dir = source_file.parent

    # Safety: only move well-formed project folders.
    if "Project_" not in project_dir.name:
        if project_dir.name == "To-be-used":
            print("⚠️ Source file not in 'Project_*' folder, skipping project archive.")
        else:
            print("⚠️ Source file not in 'To-be-used' or 'Project_*' folder, skipping project archive.")
        return

    archive_base = workspace_root / "conductor" / "archive"
    archive_base.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime('%Y%m%d')
    # Strip 'Project_' prefix (case-insensitive) for cleaner archive name
    clean_name = re.sub(r'^project_', '', project_dir.name, flags=re.IGNORECASE)
    archive_dest = archive_base / f"{today}_{sanitize_filename(clean_name)}"

    # Handle name collision by adding suffix
    if archive_dest.exists():
        counter = 1
        while archive_dest.exists():
            archive_dest = archive_base / f"{today}_{sanitize_filename(clean_name)}_{counter}"
            counter += 1

    # Use Obsidian CLI move to preserve links if available
    if cli_ok and _obs.is_obsidian_reachable(project_dir):
        print(f"📦 Archiving project via CLI: {project_dir.name} -> {archive_dest.name}")
        archive_dest.mkdir(parents=True, exist_ok=True)

        cli_success = True
        for item in project_dir.rglob('*'):
            if item.is_file():
                rel_path = item.relative_to(project_dir)
                target_item = archive_dest / rel_path
                target_item.parent.mkdir(parents=True, exist_ok=True)
                if not obsidian_move(item, target_item):
                    cli_success = False
                    shutil.move(str(item), str(target_item))

        if cli_success:
            print(f"📦 Archived project to: {archive_dest} (CLI-Native)")
        else:
            print(f"📦 Archived project to: {archive_dest} (Partial CLI/Fallback)")

        # Cleanup source directory
        try:
            shutil.rmtree(str(project_dir))
        except Exception as e:
            print(f"⚠️ Failed to remove source folder after move: {e}")
            traceback.print_exc()
    else:
        # Try move first; fall back to copy+verify+delete on Windows file-lock errors
        try:
            shutil.move(str(project_dir), str(archive_dest))
            print(f"📦 Archived project to: {archive_dest} (Legacy-Mode)")
        except (PermissionError, OSError) as e:
            print(f"⚠️ shutil.move failed ({e}), falling back to copy+verify+delete...")
            _copy_and_verify(project_dir, archive_dest)
            print(f"📦 Archived project to: {archive_dest} (Legacy-Mode, copy-fallback)")


def _cleanup_history(workspace_root, today=None):
    """Move non-today files from published/ and diary/ roots into history/YYYY-MM/.

    - published/: files with YYYYMMDD date prefix → history/YYYY-MM/
    - diary/: files with YYYY-MM-DD date prefix → history/YYYY-MM/
    - img_prev_* backup directories → history/YYYY-MM/ (date extracted from name)
    - Active img/ directory, history/ itself, and other non-date dirs are kept in place.
    - Today's files remain in root.

    Args:
        workspace_root: Obsidian vault root path.
        today: Optional datetime snapshot from publish step.  When omitted
               (--move-only mode), datetime.now() is used instead.
    """
    if today is None:
        today = datetime.now()
    today_published_prefix = today.strftime('%Y%m%d')       # e.g. 20260706
    today_diary_prefix = today.strftime('%Y-%m-%d')          # e.g. 2026-07-06

    configs = [
        {
            "dir": "published",
            "today_prefix": today_published_prefix,
            "month_from_stem": lambda stem: f"{stem[:4]}-{stem[4:6]}"
            if len(stem) >= 6 and stem[:8].isdigit() else None,
        },
        {
            "dir": "diary",
            "today_prefix": today_diary_prefix,
            "month_from_stem": lambda stem: stem[:7]
            if len(stem) >= 10 and stem[4] == '-' and stem[7] == '-' else None,
        },
    ]

    # Directories always kept in place (never moved to history)
    KEPT_DIRS = {"img", "history"}

    for cfg in configs:
        dir_path = workspace_root / cfg["dir"]
        if not dir_path.exists():
            continue

        moved_files = 0
        moved_dirs = 0
        skipped = []
        for item in sorted(dir_path.iterdir()):
            if item.is_dir():
                name = item.name
                # Keep active img/ and history/ container in place
                if name in KEPT_DIRS:
                    continue
                # Move img_prev_* backup dirs to history alongside their month's files
                if name.startswith("img_prev_"):
                    date_part = name[len("img_prev_"):len("img_prev_") + 8]
                    if len(date_part) == 8 and date_part.isdigit():
                        month = f"{date_part[:4]}-{date_part[4:6]}"
                        history_dir = dir_path / "history" / month
                        history_dir.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.move(str(item), str(history_dir / name))
                            moved_dirs += 1
                        except (PermissionError, OSError) as e:
                            print(f"⚠️ Failed to move {name}: {e}")
                    else:
                        print(f"📎 {cfg['dir']}/{name}: img_prev dir with unrecognized date pattern, kept in place")
                    continue
                # Skip other unexpected directories (safety)
                continue

            name = item.stem
            if not name:
                continue

            # Keep today's files in root
            if name.startswith(cfg["today_prefix"]):
                continue

            # Extract month from filename
            month = cfg["month_from_stem"](name)
            if not month:
                skipped.append(item.name)
                continue

            # Move to history/YYYY-MM/
            history_dir = dir_path / "history" / month
            history_dir.mkdir(parents=True, exist_ok=True)

            try:
                shutil.move(str(item), str(history_dir / item.name))
                moved_files += 1
            except (PermissionError, OSError) as e:
                print(f"⚠️ Failed to move {item.name}: {e}")

        if skipped:
            print(f"📎 {cfg['dir']}/: {len(skipped)} file(s) skipped (unrecognized date pattern): {', '.join(skipped)}")
        if moved_files > 0 or moved_dirs > 0:
            parts = []
            if moved_files > 0:
                parts.append(f"{moved_files} files")
            if moved_dirs > 0:
                parts.append(f"{moved_dirs} dirs")
            print(f"🧹 Cleaned {cfg['dir']}/: {', '.join(parts)} → history/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json")
    parser.add_argument("--no-move", action="store_true",
                        help="仅发布 Markdown，不生成 HTML，不搬迁项目目录（调试用）")
    parser.add_argument("--skip-html", action="store_true",
                        help="跳过 HTML 生成（仍会搬迁项目目录）")
    # --move-only kept for backward compatibility (deprecated)
    parser.add_argument("--move-only", action="store_true",
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        json_path = Path(args.input_json).resolve()
        json_dir = json_path.parent

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Resolve source_file relative to JSON file's directory (not cwd),
        # so callers can use bare filenames like "02_Draft.md" when JSON sits next to the project.
        raw_source = data.get('source_file', '')
        if raw_source:
            source_path = Path(raw_source)
            if not source_path.is_absolute():
                data['source_file'] = str(json_dir / source_path)

        process_archive(data, no_move=args.no_move, move_only=args.move_only, skip_html=args.skip_html)
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
