#!/usr/bin/env python3
"""
check_draft.py — wechat-daily 过程验证脚本 v2.2.0。

在 Step 1 落盘后、进入用户确认前调用，机械验证 Draft.md 和
_temp_daily.json 存在且格式合法。不做内容审计。

用法:
    PYTHONIOENCODING=utf-8 python .claude/skills/wechat-daily/scripts/check_draft.py To-be-used/Project_Daily_标题/
"""
import json
import re
import sys
from pathlib import Path


if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass


def count_chinese_chars(text):
    """统计中文字符数（忽略英文/数字/标点/空白）。"""
    return len(re.findall(r'[一-鿿]', text))


def check(project_dir):
    errors = []

    # ── 1. 目录存在 ──
    proj = Path(project_dir)
    if not proj.exists() or not proj.is_dir():
        print(f"❌ 目录不存在: {project_dir}")
        return 1

    # ── 2. Draft.md 存在且非空 ──
    draft_path = proj / "Draft.md"
    if not draft_path.exists():
        errors.append("Draft.md 缺失")
    elif draft_path.stat().st_size == 0:
        errors.append("Draft.md 为空")

    # ── 3. _temp_daily.json 存在且 JSON 合法 ──
    json_path = proj / "_temp_daily.json"
    if not json_path.exists():
        errors.append("_temp_daily.json 缺失")
    else:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"_temp_daily.json 格式错误: {e}")
            data = None

        if data is not None:
            # ── 4. title 和 body_markdown 非空 ──
            title = (data.get("title") or "").strip()
            body = (data.get("body_markdown") or "").strip()
            if not title:
                errors.append("_temp_daily.json: title 为空")
            elif not title.startswith("生活中的美好："):
                errors.append(f"_temp_daily.json: title 缺少前缀 '生活中的美好：'，当前为 '{title[:30]}'")
            if not body:
                errors.append("_temp_daily.json: body_markdown 为空")

            # ── 5. date 格式 ──
            date_str = data.get("date", "")
            if date_str and not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                errors.append(f"_temp_daily.json: date 格式错误 ({date_str})，应为 YYYY-MM-DD")

    # ── 汇总 ──
    if errors:
        for err in errors:
            print(f"❌ {err}")
        return 1

    # ── 6. 字数检查 + 通过汇总 ──
    draft_chars = 0
    if draft_path.exists():
        draft_text = draft_path.read_text(encoding='utf-8')
        if draft_text.startswith('---'):
            parts = draft_text.split('---', 2)
            draft_text = parts[2] if len(parts) > 2 else draft_text
        draft_chars = count_chinese_chars(draft_text)
        if draft_chars < 20:
            print(f"❌ Draft.md 正文字数过少 ({draft_chars} 字)，可能未充分展开")
            return 1

    title = ""
    tags = []
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            title = data.get("title", "")
            tags = data.get("tags", [])
        except (json.JSONDecodeError, KeyError):
            pass

    print(f"✅ check_draft 通过")
    print(f"   Draft.md: {draft_chars} 字")
    print(f"   _temp_daily.json: title={title}, tags={tags}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: PYTHONIOENCODING=utf-8 python check_draft.py <项目目录>")
        sys.exit(1)
    sys.exit(check(sys.argv[1]))
