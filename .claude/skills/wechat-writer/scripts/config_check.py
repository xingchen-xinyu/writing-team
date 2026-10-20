#!/usr/bin/env python3
"""
config_check.py - WeChat Writer 配置检测
首次触发时自动运行，检查写作环境是否就绪。

返回状态:
  0 - 所有检查通过
  1 - 有配置缺失或问题（仍可继续，但功能受限）
"""

import json
import sys
# Fix Windows GBK encoding for emoji output
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass
import shutil
from pathlib import Path

# ── Shared helpers ──
_SHARED = Path(__file__).resolve().parent.parent.parent.parent.parent / ".claude" / "scripts"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
import obsidian_helpers as _obs

# --- 路径解析 ---

def get_workspace_root():
    return _obs.get_workspace_root()

def get_skill_root():
    return Path(__file__).resolve().parent.parent  # wechat-writer/

def get_knowledge_dir():
    return get_skill_root() / "knowledge"

# --- 检测逻辑 ---

def check_python():
    issues = []
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        issues.append(f"⚠️ Python {version.major}.{version.minor}（需要 3.8+）")
    else:
        issues.append(f"✅ Python {version.major}.{version.minor}")
    return issues

def check_obsidian_cli():
    issues = []
    if shutil.which("obsidian"):
        issues.append("✅ Obsidian CLI 已安装（用于文件属性写入和移动）")
    else:
        issues.append("ℹ️ Obsidian CLI 未安装（archive 功能将降级为手动模式，不影响写作流程）")
    return issues

def check_scripts():
    issues = []
    skill_root = get_skill_root()
    required_scripts = [
        "scripts/research.py",
        "scripts/review_toolkit.py",
        "scripts/archive.py",
        "scripts/format.py",
    ]
    for script in required_scripts:
        if (skill_root / script).exists():
            issues.append(f"  ✅ {script}")
        else:
            issues.append(f"  ❌ {script} 未找到")
    return issues

def check_personal_files():
    """检测需要用户个人化的文件"""
    issues = []
    knowledge_dir = get_knowledge_dir()
    personal_files = {
        "style_guide.md": "写作风格指南（星辰的个人风格，可根据需要继续调整）",
        "team_memory.md": "团队记忆与踩坑记录（目前为示例，需要按需更新）",
        "published_article_index.md": "已发布文章索引（目前为示例，需要替换为你自己的文章列表）",
    }
    for filename, description in personal_files.items():
        file_path = knowledge_dir / filename
        if file_path.exists():
            issues.append(f"  ⚠️ {filename} - {description}")
        else:
            issues.append(f"  ℹ️ {filename} 不存在（可跳过）")
    return issues

def run_check():
    print("=" * 50)
    print("✍️  WeChat Writer 配置检测")
    print("=" * 50)
    print()

    has_failure = False

    # Python 版本
    print("🔧 环境检查:")
    for msg in check_python():
        print(f"  {msg}")
        if "⚠️" in msg:
            has_failure = True
    for msg in check_obsidian_cli():
        print(f"  {msg}")
    print()

    # 脚本完整性
    print("📦 脚本检查:")
    for msg in check_scripts():
        print(msg)
        if "❌" in msg:
            has_failure = True
    print()

    # 个人化文件提示
    print("👤 个人化文件（首次使用前建议检查）:")
    has_personal = False
    for msg in check_personal_files():
        print(msg)
        if "⚠️" in msg:
            has_personal = True
    print()

    if has_failure:
        print("⚠️ WeChat Writer 环境存在问题，部分功能可能受限。")
        print("   请根据上述 ❌ 标记检查缺失的脚本文件。")
        print()
        return 1

    print("✅ WeChat Writer 环境就绪。")
    print("   写作流程不依赖 API key，可直接开始使用 /interview 或 /write。")
    print()
    if has_personal:
        print("   💡 tip: 进入写作流程前，可先浏览 knowledge/ 目录下的文件，")
        print("      按需替换 style_guide.md 和 team_memory.md 为你自己的风格。")
    return 0

if __name__ == "__main__":
    sys.exit(run_check())