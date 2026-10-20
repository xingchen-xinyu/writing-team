#!/usr/bin/env python3
"""
Shared Obsidian CLI helpers for wechat-writer and wechat-director skills.

Single source of truth for: vault root detection, path conversion,
Obsidian CLI invocation, and frontmatter property management.
Previously duplicated across archive.py (~90 lines) and visualize.py (~90 lines).
"""

import json
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

# ── Workspace / Vault ──────────────────────────────────────────────

def get_workspace_root():
    """Return the workspace root: the directory containing the repository.

    This module lives at .claude/scripts/obsidian_helpers.py, so:
        scripts/ -> .claude/ -> repo_root/ -> workspace_root
    """
    return Path(__file__).resolve().parent.parent.parent


def get_obsidian_vault_root(start_path=None):
    """Find the Obsidian vault root by locating the .obsidian config directory."""
    if start_path is None:
        start_path = Path(__file__).resolve()

    current = Path(start_path).resolve()
    if current.is_file():
        current = current.parent

    while current.parent != current:
        if (current / ".obsidian").is_dir():
            return current
        current = current.parent

    return get_workspace_root().resolve()


def get_obsidian_path(abs_path):
    """Convert absolute path to vault-relative path for Obsidian CLI."""
    vault_root = get_obsidian_vault_root()
    target_path = Path(abs_path).resolve()
    try:
        return str(target_path.relative_to(vault_root))
    except ValueError:
        return str(abs_path)


def is_obsidian_reachable(file_path):
    """Check if a file path is located within the current Obsidian vault."""
    vault_root = get_obsidian_vault_root()
    try:
        Path(file_path).resolve().relative_to(vault_root)
        return True
    except (ValueError, RuntimeError):
        return False


# ── Obsidian CLI ────────────────────────────────────────────────────

def run_obsidian_cmd(args):
    """Run an obsidian CLI command and return (success, output)."""
    if shutil.which("obsidian") is None:
        return False, "obsidian CLI not found in PATH"

    try:
        result = subprocess.run(
            ["obsidian"] + args, capture_output=True, text=True, check=True
        )
        output = (result.stdout + result.stderr).strip()
        if any(kw in output for kw in ("Error:", "not found", "Missing required parameter")):
            return False, output
        return True, output
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False, ""


def set_obsidian_properties(file_path, properties):
    """Set multiple frontmatter properties via Obsidian CLI.

    Returns True only if ALL properties were set successfully.
    """
    if not is_obsidian_reachable(file_path):
        return False

    rel_path = get_obsidian_path(file_path)
    success_count = 0
    total_props = len([v for v in properties.values() if v is not None])

    for key, value in properties.items():
        if value is None:
            continue
        val_str = json.dumps(value) if isinstance(value, list) else str(value)
        cmd_args = ["property:set", f"name={key}", f"value={val_str}", f"path={rel_path}"]
        ok, err = run_obsidian_cmd(cmd_args)
        if ok:
            success_count += 1
        else:
            print(f"⚠️ CLI Property set failed for {key}: {err}", file=sys.stderr)

    return success_count == total_props


def obsidian_open(file_path):
    """Open a file in Obsidian GUI."""
    if not is_obsidian_reachable(file_path):
        return False

    rel_path = get_obsidian_path(file_path)
    ok, err = run_obsidian_cmd(["open", f"path={rel_path}"])
    if not ok:
        print(f"⚠️ CLI Open failed: {err}", file=sys.stderr)
    return ok
