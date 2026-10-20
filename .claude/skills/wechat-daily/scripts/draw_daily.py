#!/usr/bin/env python3
"""
draw_daily.py — wechat-daily 配图轻量包装。

不复制 wechat-director 的生图引擎代码，只负责两件事：
1. 告诉调用方 daily 侧边栏固定用哪个颜色（两技能色板，见
   wechat-director/references/sidebar_design_system.md）
2. 拼出调用 wechat-director/scripts/visualize.py 的命令行参数

真正的模式选择对话、Storyboard 撰写由 Agent 按
daily_beauty_routine.md「配图」一节的指引在对话中完成，不在本脚本里。
"""
import sys
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass

# ── Cross-skill: 生图引擎在 wechat-director，不复制 ──
_DIRECTOR_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "wechat-director" / "scripts"
if str(_DIRECTOR_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_DIRECTOR_SCRIPTS_DIR))

DAILY_SIDEBAR_COLOR = "#D4A854"  # 琥珀金，见 sidebar_design_system.md 两技能色板


def resolve_director_scripts_dir():
    return _DIRECTOR_SCRIPTS_DIR


def get_sidebar_color():
    return DAILY_SIDEBAR_COLOR


def build_simple_mode_command(cover_path, brief_path):
    """拼出简单模式（用户自供封面 + AI 生成侧边栏并拼接）的调用命令。"""
    visualize_path = resolve_director_scripts_dir() / "visualize.py"
    return [
        "python",
        str(visualize_path),
        "--mode", "simple",
        "--brief", brief_path,
        "--cover", cover_path,
    ]


if __name__ == "__main__":
    print("draw_daily.py 是一个供 Agent 在对话中调用的辅助模块，不直接作为 CLI 运行。")
    print(f"生图引擎位置: {resolve_director_scripts_dir()}")
    print(f"daily 侧边栏固定色: {get_sidebar_color()}")
