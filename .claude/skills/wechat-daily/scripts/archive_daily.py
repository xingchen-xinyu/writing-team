#!/usr/bin/env python3
"""
archive_daily.py — wechat-daily「生活中的美好」轻量发布脚本 v2.0.0。

与 wechat-writer/scripts/archive.py 对齐核心能力：
- 发布到 published/（与 writer 共享目录）
- 追加 bio footer（文末个人 IP 介绍）
- Frontmatter + Obsidian CLI 属性同步
- 封面图处理（cover-combined > cover-main）
- HTML 生成（复用 writer 的 format.py）
- 更新 daily_article_index.md
- 项目归档到 conductor/archive/
- published/ + diary/ 历史文件自动清理
"""
import json
import argparse
import re
import shutil
import sys
import traceback
from pathlib import Path
from datetime import datetime

# Fix Windows GBK encoding for emoji output
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass

# ── Shared helpers ──
_SHARED = Path(__file__).resolve().parent.parent.parent.parent.parent / ".claude" / "scripts"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import obsidian_helpers as _obs

# ── Cross-skill: format.py lives in wechat-writer ──
_WRITER_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "wechat-writer" / "scripts"
if str(_WRITER_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_WRITER_SCRIPTS_DIR))

# ── Cross-skill: bio functions from wechat-writer/scripts/archive.py ──
from archive import load_bio_header, load_bio_footer


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()


def yaml_escape(value):
    """Escape text for YAML double-quoted string values."""
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"').replace('\n', '\\n')


def to_vault_path(path_value, vault_dir_name):
    """Normalize path into vault-root based relative path."""
    raw = "" if path_value is None else str(path_value).strip()
    if not raw:
        return ""
    normalized = raw.replace("\\", "/").lstrip("/")
    if "://" in normalized:
        return normalized
    prefix = f"{vault_dir_name}/"
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix):]
    return normalized


def get_skill_root():
    return Path(__file__).resolve().parent.parent  # wechat-daily/


def get_daily_index_path():
    return get_skill_root() / "knowledge" / "daily_article_index.md"


# ── Cover image ──

def pick_cover_image(img_dir):
    """Pick cover image from image folder. Priority: cover-combined > cover-main."""
    if not img_dir.exists() or not img_dir.is_dir():
        return None

    exact_priorities = ["cover-combined.jpg", "cover-main.jpg"]
    for name in exact_priorities:
        f = img_dir / name
        if f.exists():
            return f

    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    image_files = sorted(
        [p for p in img_dir.iterdir() if p.is_file() and p.suffix.lower() in image_exts],
        key=lambda p: p.name.lower()
    )
    if not image_files:
        return None

    for keyword in ("cover-combined", "cover-main"):
        for fp in image_files:
            if keyword in fp.name.lower():
                return fp
    return None


# ── Daily index ──

def _read_index_safe(index_path):
    """Read index file, falling back to GBK if UTF-8 fails (legacy files)."""
    try:
        return index_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = index_path.read_text(encoding="gbk")
        # Rewrite as UTF-8 to auto-fix encoding going forward
        index_path.write_text(content, encoding="utf-8")
        print(f"🔧 索引文件已从 GBK 转换为 UTF-8: {index_path}")
        return content


def update_daily_index(stem, title, tags, excerpt):
    """Append entry to daily_article_index.md."""
    index_path = get_daily_index_path()
    date_str = stem[:8]
    date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}" if len(date_str) == 8 and date_str.isdigit() else date_str
    tags_str = ", ".join(tags or [])
    link = f"[[{stem}]]"
    row = f"| {date_display} | {link} | {tags_str} | {excerpt or ''} |\n"

    if not index_path.exists():
        index_path.parent.mkdir(parents=True, exist_ok=True)
        header = "# wechat-daily「生活中的美好」索引\n\n"
        table_header = "| 日期 | 标题 | 标签 | 摘要 |\n| --- | --- | --- | --- |\n"
        index_path.write_text(header + table_header + row, encoding="utf-8")
        print(f"📋 创建 daily 索引: {index_path}")
        return

    content = _read_index_safe(index_path)
    if link in content:
        print(f"ℹ️ 索引中已存在: {link}")
        return
    index_path.write_text(content.rstrip("\n") + "\n" + row, encoding="utf-8")
    print(f"📋 已更新 daily 索引: {index_path}")


# ── Image copy ──

def copy_images(img_dir, workspace_root):
    """Copy images from project img/ to published/img/."""
    if not img_dir:
        return None
    src = Path(img_dir)
    if not src.exists() or not src.is_dir():
        return None
    dest_dir = Path(workspace_root) / "published" / "img"
    dest_dir.mkdir(parents=True, exist_ok=True)
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    copied = 0
    for f in sorted(src.iterdir()):
        if not f.is_file() or f.suffix.lower() not in image_exts:
            continue
        dest_file = dest_dir / f.name
        if dest_file.exists():
            print(f"⚠️ 图片同名已存在，跳过: {f.name}")
            continue
        shutil.copy2(f, dest_file)
        copied += 1
        print(f"🖼️ 已复制图片: {dest_file}")
    return dest_dir if copied > 0 else None


# ── Project archive ──

def _copy_and_verify(src_dir, dst_dir):
    """Copy project directory to archive, verify integrity, then delete source."""
    src = Path(src_dir)
    dst = Path(dst_dir)
    src_files = []
    for item in src.rglob('*'):
        if item.is_file():
            src_files.append(item.relative_to(src))

    if not src_files:
        print(f"⚠️ No files to copy from {src_dir}")
        return

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

    dst_files = []
    for item in dst.rglob('*'):
        if item.is_file():
            dst_files.append(item.relative_to(dst))

    if failed:
        print(f"⚠️ Copy partially failed: {copied}/{len(src_files)} copied, {len(failed)} failures")
        for path, err in failed:
            print(f"   - {path}: {err}")
        print(f"⚠️ Source directory NOT deleted: {src_dir}")
        return

    if len(src_files) != len(dst_files):
        print(f"⚠️ Copy verification failed: source has {len(src_files)} files, dest has {len(dst_files)}")
        print(f"⚠️ Source directory NOT deleted: {src_dir}")
        return

    shutil.rmtree(str(src_dir))
    print(f"   Verified {len(src_files)} files, source deleted.")


def migrate_project(project_dir, workspace_root, title=None):
    """Move Project_Daily_* directory to conductor/archive/.

    Archive name is derived from the final published `title` when given
    (Step 0's working title may drift from Step 1's final title, since the
    project directory itself is never renamed). Falls back to the directory
    name when no title is available (e.g. direct script invocation).
    """
    if "Project_Daily_" not in project_dir.name:
        print(f"ℹ️ 跳过归档：{project_dir.name} 不是 Project_Daily_ 目录")
        return

    archive_base = Path(workspace_root) / "conductor" / "archive"
    archive_base.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime('%Y%m%d')
    if title:
        short_title = title.split("：", 1)[-1].split(":", 1)[-1].strip() or title
        clean_name = f"Daily_{short_title}"
    else:
        # Strip 'Project_' prefix for cleaner archive name (keeps Daily_ prefix)
        clean_name = re.sub(r'^project_', '', project_dir.name, flags=re.IGNORECASE)
    archive_dest = archive_base / f"{today}_{sanitize_filename(clean_name)}"

    if archive_dest.exists():
        counter = 1
        while archive_dest.exists():
            archive_dest = archive_base / f"{today}_{sanitize_filename(clean_name)}_{counter}"
            counter += 1

    cli_ok = shutil.which("obsidian") is not None

    if cli_ok and _obs.is_obsidian_reachable(project_dir):
        print(f"📦 归档项目 (CLI): {project_dir.name} -> {archive_dest.name}")
        archive_dest.mkdir(parents=True, exist_ok=True)
        cli_success = True
        for item in project_dir.rglob('*'):
            if item.is_file():
                rel_path = item.relative_to(project_dir)
                target_item = archive_dest / rel_path
                target_item.parent.mkdir(parents=True, exist_ok=True)
                src_rel = _obs.get_obsidian_path(item)
                dest_rel = _obs.get_obsidian_path(target_item)
                ok, err = _obs.run_obsidian_cmd(["move", f"path={src_rel}", f"to={dest_rel}"])
                if not ok:
                    cli_success = False
                    shutil.move(str(item), str(target_item))
        if cli_success:
            print(f"📦 已归档到: {archive_dest} (CLI-Native)")
        else:
            print(f"📦 已归档到: {archive_dest} (Partial CLI/Fallback)")
        try:
            shutil.rmtree(str(project_dir))
        except Exception as e:
            print(f"⚠️ Failed to remove source folder after move: {e}")
    else:
        try:
            shutil.move(str(project_dir), str(archive_dest))
            print(f"📦 已归档到: {archive_dest}")
        except (PermissionError, OSError) as e:
            print(f"⚠️ shutil.move failed ({e}), falling back to copy+verify+delete...")
            _copy_and_verify(project_dir, archive_dest)
            print(f"📦 已归档到: {archive_dest} (copy-fallback)")


# ── History cleanup ──

def cleanup_history(workspace_root, today=None):
    """Move non-today files from published/ and diary/ into history/YYYY-MM/.

    - published/: files with YYYYMMDD date prefix → history/YYYY-MM/
    - diary/: files with YYYY-MM-DD date prefix → history/YYYY-MM/
    - Active img/ directory, history/ itself are kept in place.
    - Today's files remain in root.
    """
    if today is None:
        today = datetime.now()
    today_published_prefix = today.strftime('%Y%m%d')
    today_diary_prefix = today.strftime('%Y-%m-%d')

    KEPT_DIRS = {"img", "history"}

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
                if name in KEPT_DIRS:
                    continue
                # Move img_prev_* backup dirs to history
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
                    continue
                continue

            name = item.stem
            if not name:
                continue

            if name.startswith(cfg["today_prefix"]):
                continue

            month = cfg["month_from_stem"](name)
            if not month:
                skipped.append(item.name)
                continue

            history_dir = dir_path / "history" / month
            history_dir.mkdir(parents=True, exist_ok=True)

            try:
                shutil.move(str(item), str(history_dir / item.name))
                moved_files += 1
            except (PermissionError, OSError) as e:
                print(f"⚠️ Failed to move {item.name}: {e}")

        if skipped:
            print(f"📎 {cfg['dir']}/: {len(skipped)} file(s) skipped (unrecognized date): {', '.join(skipped)}")
        if moved_files > 0 or moved_dirs > 0:
            parts = []
            if moved_files > 0:
                parts.append(f"{moved_files} files")
            if moved_dirs > 0:
                parts.append(f"{moved_dirs} dirs")
            print(f"🧹 Cleaned {cfg['dir']}/: {', '.join(parts)} → history/")


# ── Main processing ──

def process_daily(data, json_dir, workspace_root, no_move=False, skip_html=False):
    title = (data.get("title") or "").strip()
    if not title:
        print("❌ 错误: title 不能为空")
        sys.exit(1)
    body_markdown = (data.get("body_markdown") or "").strip()
    if not body_markdown:
        print("❌ 错误: body_markdown 不能为空")
        sys.exit(1)

    publish_time = datetime.now()  # snapshot once, avoid midnight race with cleanup_history

    date_str = data.get("date") or publish_time.strftime("%Y-%m-%d")
    excerpt = data.get("excerpt", "")
    tags = data.get("tags") or []
    img_dir = data.get("img_dir", "")

    # ── Resolve paths ──
    workspace_name = workspace_root.name
    safe_title = sanitize_filename(title)
    date_prefix = date_str.replace("-", "")
    target_stem = f"{date_prefix}_{safe_title}"

    target_dir = workspace_root / "published"
    target_dir.mkdir(parents=True, exist_ok=True)

    target_file = target_dir / f"{target_stem}.md"
    # Handle name collision
    if target_file.exists():
        counter = 2
        while target_file.exists():
            target_stem = f"{date_prefix}_{safe_title}_{counter}"
            target_file = target_dir / f"{target_stem}.md"
            counter += 1

    # ── Resolve image dir (relative to JSON file directory) ──
    img_src_dir = None
    if img_dir:
        img_path = Path(img_dir)
        if not img_path.is_absolute():
            img_path = json_dir / img_path
        if img_path.exists() and img_path.is_dir():
            img_src_dir = img_path

    # ── Build content ──
    content = body_markdown.strip()

    # Prepend bio header (personal intro) at the beginning of the article
    bio_header = load_bio_header()
    if bio_header:
        content = bio_header + "\n\n" + content
        print("📝 Bio header prepended to article.")

    # Append bio footer
    bio_footer = load_bio_footer()
    if bio_footer:
        bio_lines = [l.strip() for l in bio_footer.strip().split('\n') if l.strip()]
        bio_sig = '\n'.join(bio_lines[:2]) if len(bio_lines) >= 2 else bio_lines[0] if bio_lines else ""
        if bio_sig and bio_sig not in content:
            content = content.rstrip() + "\n\n" + bio_footer
            print("📝 Bio footer appended.")
        else:
            print("ℹ️ Bio footer already present, skipping.")

    # ── Copy images + resolve cover ──
    cover_path = ""
    if img_src_dir:
        # Backup existing published/img/ before replacing (same as writer)
        existing_img = target_dir / "img"
        if existing_img.exists():
            timestamp = publish_time.strftime('%Y%m%d_%H%M%S')
            backup = target_dir / f"img_prev_{timestamp}"
            counter = 1
            while backup.exists():
                backup = target_dir / f"img_prev_{timestamp}_{counter}"
                counter += 1
            shutil.move(str(existing_img), str(backup))
            print(f"📦 旧图片已备份: {backup.name}")

        dest_img_dir = copy_images(str(img_src_dir), workspace_root)
        if dest_img_dir:
            cover_file = pick_cover_image(dest_img_dir)
            if cover_file:
                relative_path = cover_file.relative_to(workspace_root).as_posix()
                cover_path = to_vault_path(relative_path, workspace_name)
                print(f"🖼️ Cover selected: {cover_path}")
            else:
                print("⚠️ No cover-combined/cover-main found, cover stays empty.")

    # ── Write published markdown ──
    props = {
        "title": title,
        "date": date_str,
        "slug": "",
        "excerpt": excerpt,
        "cover": cover_path,
        "tags": tags,
        "status": "published"
    }

    cli_ok = shutil.which("obsidian") is not None
    cli_success = False

    if cli_ok and _obs.is_obsidian_reachable(target_file):
        target_file.write_text(f"---\n---\n{content}", encoding='utf-8')
        if _obs.set_obsidian_properties(target_file, props):
            print(f"🚀 已发布: {target_file} (CLI-Native)")
            cli_success = True
        else:
            print("⚠️ CLI Property sync failed, falling back to legacy...")

    if not cli_success:
        fm_tags = json.dumps(tags, ensure_ascii=False)
        new_content = f"""---
title: "{yaml_escape(title)}"
date: "{date_str}"
excerpt: "{yaml_escape(excerpt)}"
cover: "{yaml_escape(cover_path)}"
tags: {fm_tags}
status: published
---
{content}"""
        target_file.write_text(new_content, encoding='utf-8')
        print(f"🚀 已发布: {target_file} (Legacy-Mode)")

    # ── Update daily index ──
    update_daily_index(target_stem, title, tags, excerpt)

    # ── Generate HTML ──
    if not skip_html:
        try:
            from format import process_format
            html_output = target_dir / f"{target_stem}.html"
            print(f"📄 生成 HTML...")

            # Bridge gold quotes: generate temp production file for format.py
            gold_quotes = data.get("gold_quotes", [])
            prod_file = ""
            if gold_quotes:
                prod_md = "## 金句提炼\n\n| # | 原文 | 打磨后 |\n| --- | --- | --- |\n"
                for i, gq in enumerate(gold_quotes, 1):
                    gq_clean = gq.strip()
                    if gq_clean:
                        prod_md += f"| {i} | {gq_clean} | {gq_clean} |\n"
                prod_path = json_dir / "_temp_production.md"
                prod_path.write_text(prod_md, encoding='utf-8')
                prod_file = str(prod_path)
                print(f"📝 金句标记: {len(gold_quotes)} 句")

            process_format({
                "draft_file": str(target_file),
                "production_file": prod_file,
                "output_path": str(html_output),
            })
        except FileNotFoundError as e:
            print(f"⚠️ HTML 生成跳过（文件缺失）: {e}")
        except Exception as e:
            print(f"⚠️ HTML 生成失败（发布稿已保存，可稍后手动生成）: {e}")
            traceback.print_exc()

    # ── Archive project ──
    if not no_move:
        migrate_project(json_dir, workspace_root, title=title)
        cleanup_history(workspace_root, today=publish_time)

    print(f"\n✅ daily 发布完成: {target_file}")


def main():
    parser = argparse.ArgumentParser(
        description="wechat-daily 轻量发布脚本 v2.0.0"
    )
    parser.add_argument("input_json", help="Path to _temp_daily.json")
    parser.add_argument("--no-move", action="store_true",
                        help="仅发布，不归档项目目录、不清理历史（调试用）")
    parser.add_argument("--skip-html", action="store_true",
                        help="跳过 HTML 生成（仍会归档项目）")
    args = parser.parse_args()

    try:
        json_path = Path(args.input_json).resolve()
        json_dir = json_path.parent

        # Security: validate JSON is under a Project_Daily_ directory
        if "Project_Daily_" not in json_dir.name:
            # Also accept _daily_scratch for backward compatibility
            if json_dir.name != "_daily_scratch":
                print(f"⚠️ 警告: JSON 不在 Project_Daily_* 目录下: {json_dir}")
                print("   建议将 _temp_daily.json 放在 To-be-used/Project_Daily_标题/ 下")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        workspace_root = _obs.get_workspace_root()
        process_daily(data, json_dir, workspace_root,
                      no_move=args.no_move, skip_html=args.skip_html)

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
