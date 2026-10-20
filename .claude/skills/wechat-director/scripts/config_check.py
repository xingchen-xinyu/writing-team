#!/usr/bin/env python3
"""
config_check.py - WeChat Director 配置检测
首次触发时自动运行，检查生图相关配置是否就绪。

返回状态:
  ok              - 至少有一个可用的生图 provider
  optional_missing - 无 provider（用户可选择手动生图或跳过）
"""

import json
import os
import shutil
import subprocess
import sys
# Fix Windows GBK encoding for emoji output
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass
from pathlib import Path

# ── Shared helpers ──
_SHARED = Path(__file__).resolve().parent.parent.parent.parent.parent / ".claude" / "scripts"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
import obsidian_helpers as _obs

# ── Shared gemini-web cookie utilities ──
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import gemini_web_utils as _gwu

# --- 路径解析（使用共享实现）---

def get_workspace_root():
    return _obs.get_workspace_root()

def get_skill_root():
    """Find the wechat-director skill root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent  # scripts -> wechat-director

def load_api_config():
    config_path = get_workspace_root() / "conductor" / "api_keys.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# Re-export from shared module with config_check.py naming conventions
_read_cookies_from_file = _gwu.read_cookies_from_file
_rotate_cookie_http = _gwu.rotate_cookie_http


def _validate_gemini_web_session(cookie_path, timeout=_gwu.TIMEOUT_HTTP_VALIDATE):
    """Validate gemini-web session from cookie file path (config_check-compatible wrapper)."""
    if not cookie_path.exists():
        return False, "cookie file not found"
    cookies = _read_cookies_from_file(cookie_path)
    if not cookies:
        return False, "cookie file empty or unreadable"
    return _gwu.validate_session_http(cookies, timeout)


def _auto_refresh_gemini_web_cookie(api_config, cookie_path):
    """Try to refresh gemini-web cookie.

    First tries L2 HTTP rotation (silent). If that fails, falls back to
    launching Chrome for CDP-based cookie extraction (requires bun + vendor).

    Returns True if cookie was refreshed successfully.
    """
    # L2: Try HTTP cookie rotation first (fast, no browser)
    if cookie_path.exists():
        cookies = _read_cookies_from_file(cookie_path)
        if cookies:
            new_1psidts = _rotate_cookie_http(cookies)
            if new_1psidts:
                cookies["__Secure-1PSIDTS"] = new_1psidts
                try:
                    _gwu.write_cookies_to_file(cookie_path, cookies, source="rotate-http")
                    print("  ✅ Cookie 已通过 HTTP 续期 (L2)")
                    return True
                except Exception as e:
                    print(f"  ⚠️ 保存续期 cookie 失败: {e}")
                    return False
            print("  ⚠️ Cookie HTTP 续期失败")

    # L3: Launch Chrome for CDP-based cookie extraction.
    # After L3, skip HTTP re-validation (VPN may block Python urllib even when
    # Chrome CDP succeeds). Trust that Chrome wrote valid cookies.
    try:
        import importlib.util
        skill_root = get_skill_root()
        viz_path = skill_root / "scripts" / "visualize.py"
        if not viz_path.exists():
            print("  ℹ️ visualize.py not found, cannot auto-refresh cookie")
            return False

        spec = importlib.util.spec_from_file_location("visualize", str(viz_path))
        viz_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(viz_module)

        print("  🔐 启动 Chrome 提取 cookie...")
        viz_module.login_gemini_web(api_config)

        if cookie_path.exists():
            cookies = _read_cookies_from_file(cookie_path)
            if cookies and cookies.get("__Secure-1PSID"):
                print("  ✅ Gemini Web cookie 已刷新 (L3)")
                return True
        print("  ⚠️ 登录流程完成但 cookie 文件未生成或缺少关键字段")
        return False
    except Exception as e:
        print(f"  ⚠️ 自动刷新 cookie 失败: {e}")
        return False

# --- 配置检测逻辑 ---

def check_image_providers(api_config):
    """检测生图 provider"""
    issues = []
    providers = []

    # 0. Gemini Web（优先，无需 API key，但需要 vendor + bun + 登录）
    skill_root = get_skill_root()
    gemini_web_scripts = skill_root / "vendor" / "baoyu-danger-gemini-web" / "scripts"
    has_bun = bool(shutil.which("bun"))
    has_vendor = gemini_web_scripts.exists()
    has_cookies = False
    if has_vendor:
        repo_root = get_workspace_root()
        provider_config = api_config.get("gemini_web", {})
        # Two-step resolution matching visualize.py resolve_gemini_web_settings():
        # runtime_dir → cookie_path (defaults to {runtime_dir}/cookies.json)
        runtime_dir = Path(provider_config.get(
            "runtime_dir",
            repo_root / ".gemini" / "wechat-director" / "gemini-web"
        ))
        cookie_path = Path(provider_config.get("cookie_path", runtime_dir / "cookies.json"))
        has_cookies = cookie_path.exists()

    if has_vendor and has_bun:
        if has_cookies:
            # Validate that the session is actually still active (lightweight HTTP check)
            valid, reason = _validate_gemini_web_session(cookie_path)
            if valid:
                providers.append("gemini-web")
                issues.append("✅ gemini-web 可用（vendor + bun + 会话有效）")
            else:
                print(f"  ⚠️ gemini-web 会话验证失败: {reason}")
                # Auto-refresh expired cookie
                if _auto_refresh_gemini_web_cookie(api_config, cookie_path):
                    providers.append("gemini-web")
                    issues.append("✅ gemini-web 已重新登录，现在可用")
                else:
                    issues.append("⚠️ gemini-web cookie 已过期且自动刷新失败。手动运行: python scripts/visualize.py --gemini-web-login")
        else:
            issues.append("⚠️ gemini-web vendor 和 bun 就绪，但未登录。运行: python scripts/visualize.py --gemini-web-login")
    elif not has_vendor:
        issues.append("ℹ️ gemini-web vendor 未安装（可选，需 git submodule 或手动拉取）")
    elif not has_bun:
        issues.append("ℹ️ bun 未安装（gemini-web 需要 bun 运行时）")

    # 1. Gemini API（需要 api_key）
    gemini = api_config.get("gemini", {})
    if gemini.get("api_key") and gemini.get("base_url"):
        providers.append("gemini")
    elif gemini.get("api_key"):
        issues.append("⚠️ gemini.api_key 已配置，但缺少 base_url")
    else:
        issues.append("ℹ️ gemini 未配置（可选，需要 API key）")

    # 2. GPT-Image2（需要 api_key）
    gpt = api_config.get("gpt-image2", {})
    if gpt.get("api_key") and gpt.get("base_url"):
        providers.append("gpt-image2")
    elif gpt.get("api_key"):
        issues.append("⚠️ gpt-image2.api_key 已配置，但缺少 base_url")
    else:
        issues.append("ℹ️ gpt-image2 未配置（可选，需要 API key）")

    # 3. SiliconFlow（需要 api_key）
    siliconflow = api_config.get("siliconflow", {})
    if siliconflow.get("api_key") and siliconflow.get("base_url"):
        providers.append("siliconflow")
    elif siliconflow.get("api_key"):
        issues.append("⚠️ siliconflow.api_key 已配置，但缺少 base_url")
    else:
        issues.append("ℹ️ siliconflow 未配置（可选，需要 API key）")

    return providers, issues

def check_optional_services(api_config):
    """检测可选服务"""
    issues = []

    # TinyPNG 压缩
    tinify = api_config.get("tinify", {})
    if tinify.get("api_key"):
        issues.append("✅ TinyPNG 压缩已配置")
    else:
        issues.append("ℹ️ TinyPNG 压缩未配置（可选，图片将不压缩）")

    # 腾讯云 COS 上传
    cos = api_config.get("cos", {})
    required = ["region", "secret_id", "secret_key", "bucket"]
    if all(cos.get(k) for k in required):
        issues.append("✅ 腾讯云 COS 上传已配置")
    else:
        issues.append("ℹ️ 腾讯云 COS 未配置（可选，图片将不上传到 CDN）")

    return issues

def run_check():
    api_config = load_api_config()
    providers, provider_issues = check_image_providers(api_config)
    optional_issues = check_optional_services(api_config)

    has_provider = len(providers) > 0

    print("=" * 50)
    print("🎬 WeChat Director 配置检测")
    print("=" * 50)
    print()

    print("📦 生图 Provider 状态:")
    for issue in provider_issues:
        print(f"  {issue}")
    print()

    if has_provider:
        print(f"✅ 可用 provider: {', '.join(providers)}")
        print()
        print("▶️  可选服务状态:")
        for issue in optional_issues:
            print(f"  {issue}")
        print()
        print("✅ 配置检测通过，Director 可以自动生图。")
        print("   如需跳过，可在 /draw 时选择手动生图或使用已有图片链接。")
        return 0
    else:
        print("⚠️  没有配置任何生图 provider")
        print()
        print("   📋 选择方案:")
        print("   1. 配置 API key（推荐 Gemini 或 GPT-Image2）：")
        print("      → 在 conductor/api_keys.json 中添加 gemini 或 gpt-image2 配置")
        print("   2. 跳过: 手动生图，在 Storyboard 中填入图片 URL")
        print()
        print(f"   配置路径: {get_workspace_root()}/conductor/api_keys.json")
        return 1

if __name__ == "__main__":
    sys.exit(run_check())