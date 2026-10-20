#!/usr/bin/env python3
"""
Image Generator - WeChat Director v2.4.0
Automated "Generate-Compress-Upload-Inject" Pipeline

Usage:
    PYTHONIOENCODING=utf-8 python visualize.py --brief path/to/Storyboard.md --draft path/to/Draft.md
"""

import argparse
import base64
import json
import os
import re
import shutil
import struct
import subprocess
import sys
# Fix Windows GBK encoding for emoji output
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        pass
import time
import hashlib
import urllib.request
import urllib.error
import ssl
from datetime import datetime
from pathlib import Path
import logging

# Work around SSL UNEXPECTED_EOF_WHILE_READING / WRONG_VERSION_NUMBER caused by:
#  - HTTP/2 (h2) ALPN negotiation on certain proxy/CDN combinations
#  - Broken TLS 1.3 implementations on third-party API proxies (e.g. packyapi)
# Restrict ALPN to http/1.1 only and cap TLS at 1.2 for maximum compatibility.
_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.set_alpn_protocols(['http/1.1'])
_SSL_CONTEXT.maximum_version = ssl.TLSVersion.TLSv1_2
# Enable OP_LEGACY_SERVER_CONNECT if available (Python 3.12+) for broken TLS implementations
if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
    _SSL_CONTEXT.options |= ssl.OP_LEGACY_SERVER_CONNECT


def _build_ssl_context(api_config=None):
    """Build an SSL context, optionally skipping verification for third-party proxies.

    Set "ssl_verify": false in the provider config (e.g. gemini.ssl_verify) to disable
    certificate verification. This is useful for third-party API proxies that use
    self-signed or misconfigured certificates.
    """
    if api_config and api_config.get("ssl_verify") is False:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_alpn_protocols(['http/1.1'])
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        return ctx
    return _SSL_CONTEXT

# ── Shared helpers (single source for Obsidian CLI + workspace paths) ──
_SHARED = Path(__file__).resolve().parent.parent.parent.parent.parent / ".claude" / "scripts"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
import obsidian_helpers as _obs

# ── Shared gemini-web cookie utilities ──
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import gemini_web_utils as _gwu

# ── Local Pillow sidebar renderer (non-AI, fast, reliable Chinese text) ──
try:
    from sidebar_renderer import (
        parse_sidebar_prompt,
        render_sidebar_locally,
        FONT_PATH as SIDEBAR_FONT_PATH,
    )
    SIDEBAR_LOCAL_AVAILABLE = True
except ImportError:
    SIDEBAR_LOCAL_AVAILABLE = False

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Optional dependencies
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("⚠️ Pillow not installed. Image stitching will be skipped.")

try:
    import tinify
    TINIFY_AVAILABLE = True
except ImportError:
    TINIFY_AVAILABLE = False
    logger.warning("⚠️ tinify not installed. Compression will be skipped.")

try:
    from qcloud_cos import CosConfig
    from qcloud_cos import CosS3Client
    COS_AVAILABLE = True
except ImportError:
    COS_AVAILABLE = False
    logger.warning("⚠️ cos-python-sdk-v5 not installed. Upload will be skipped.")


# --- Configurations & Constants ---

ASPECT_RATIOS = {
    "cover-main": {"width": 1504, "height": 640, "suffix": "cover-main"},
    "cover-sidebar": {"width": 1024, "height": 1024, "suffix": "cover-sidebar"},
    "illustration": {"width": 768, "height": 1024, "suffix": "illustration"},
    "quote": {"width": 768, "height": 1024, "suffix": "quote"},
}
DIRECTOR_VERSION = "2.5.0"

# ── Timeout constants (seconds) ──
TIMEOUT_GEMINI_API = 90       # Gemini image generation API call
TIMEOUT_SILICONFLOW = 60      # SiliconFlow image generation API call
TIMEOUT_GPT_IMAGE2 = 300      # GPT-Image2 generation (can be slow)
TIMEOUT_GEMINI_WEB = 240      # Gemini Web headless browser default
TIMEOUT_GEMINI_WEB_LOGIN = 300 # Gemini Web login initialization

# Re-export from shared module for internal use
TIMEOUT_HTTP_VALIDATE = _gwu.TIMEOUT_HTTP_VALIDATE
TIMEOUT_HTTP_ROTATE = _gwu.TIMEOUT_HTTP_ROTATE

def get_skill_root():
    """Find the wechat-director skill root directory."""
    return Path(__file__).resolve().parent.parent

def load_api_config():
    """Load API keys from conductor/api_keys.json"""
    config_path = _obs.get_workspace_root() / "conductor" / "api_keys.json"
    if not config_path.exists():
        logger.warning("⚠️ API Config not found. API providers, compression, and upload may be unavailable.")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config

# --- Helper Functions ---

def sanitize_filename(text):
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'\s+', '-', text)
    return text[:50]

def clean_prompt(prompt):
    prompt = prompt.strip()
    if len(prompt) < 5: return None
    # Remove "2.35:1 aspect ratio" / "aspect ratio 2.35:1" patterns (both orders)
    prompt = re.sub(r',?\s*[\d.:]+\s*aspect\s+ratio', '', prompt, flags=re.IGNORECASE)
    prompt = re.sub(r',?\s*aspect\s+ratio\s*[\d.:]+', '', prompt, flags=re.IGNORECASE)
    # Remove --ar flags
    prompt = re.sub(r'\s--\w+(?:\s+[\w.:]+)?', '', prompt)
    return prompt.strip()

def check_ip_requirement(text):
    return bool(re.search(r'(?:IP(?:形象)?|Reference|参考图?)\s*[:：]\s*(?:Yes|True|是|On|Required|1)', text, re.IGNORECASE))

def calculate_hash(prompt, width, height, model, use_ip=False):
    content = f"{prompt}|{width}|{height}|{model}|{use_ip}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:8]

def require_config(api_config, provider_name, required_keys):
    if not api_config:
        raise RuntimeError(f"{provider_name} config missing.")

    missing = [key for key in required_keys if not api_config.get(key)]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(f"{provider_name} config incomplete: missing {missing_str}.")

def resolve_gemini_web_settings(api_config):
    repo_root = _obs.get_workspace_root()
    skill_root = get_skill_root()
    provider_config = api_config.get("gemini_web", {})
    runtime_dir = Path(provider_config.get(
        "runtime_dir",
        repo_root / ".gemini" / "wechat-director" / "gemini-web"
    ))

    return {
        "model": provider_config.get("model", "gemini-3.0-flash"),
        "timeout": int(provider_config.get("timeout", TIMEOUT_GEMINI_WEB)),
        "script_dir": skill_root / "vendor" / "baoyu-danger-gemini-web" / "scripts",
        "data_dir": Path(provider_config.get("data_dir", runtime_dir / "data")),
        "cookie_path": Path(provider_config.get("cookie_path", runtime_dir / "cookies.json")),
        "profile_dir": Path(provider_config.get("profile_dir", runtime_dir / "chrome-profile")),
    }

def run_gemini_web_command(api_config, extra_args, timeout=None):
    settings = resolve_gemini_web_settings(api_config)
    script_dir = settings["script_dir"]
    bun_path = shutil.which("bun")

    if not script_dir.exists():
        raise FileNotFoundError(f"Gemini Web backend not found: {script_dir}")
    if not bun_path:
        raise RuntimeError("bun is required for gemini-web provider, but was not found in PATH.")

    settings["data_dir"].mkdir(parents=True, exist_ok=True)
    settings["profile_dir"].mkdir(parents=True, exist_ok=True)
    settings["cookie_path"].parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["GEMINI_WEB_DATA_DIR"] = str(settings["data_dir"])
    env["GEMINI_WEB_CHROME_PROFILE_DIR"] = str(settings["profile_dir"])
    env["GEMINI_WEB_COOKIE_PATH"] = str(settings["cookie_path"])
    env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"  # bypass cert issues in restricted network environments

    cmd = [bun_path, "run", "main.ts", *extra_args]
    result = subprocess.run(
        cmd,
        cwd=script_dir,
        env=env,
        capture_output=True,
        encoding="utf-8",  # force UTF-8; text=True would use system GBK on Windows
        errors="replace",
        timeout=timeout or settings["timeout"],
    )

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        # Always log full stderr so the user can diagnose the real cause
        if stderr:
            logger.error(f"gemini-web stderr:\n{stderr}")
        login_hint = ""
        lower_err = stderr.lower()
        # Only suggest re-login for genuine auth/cookie-expiry errors,
        # not for network/socket errors that merely mention "cookie" in passing.
        if any(s in lower_err for s in _AUTH_SIGNALS):
            login_hint = " Run visualize.py with --gemini-web-login once first."
        raise RuntimeError(f"gemini-web failed: {stderr[:800]}{login_hint}")

    return result, settings

# ── HTTP-level Cookie Validation & Rotation (delegates to shared module) ──

# Thin adapters that delegate to gemini_web_utils; kept as module-level
# functions so the rest of visualize.py doesn't need to be rewritten.
_read_cookies_from_file = _gwu.read_cookies_from_file
_validate_gemini_session_http = _gwu.validate_session_http
_rotate_cookie_http = _gwu.rotate_cookie_http
_build_cookie_header = _gwu.build_cookie_header

# Auth/cookie-expiry signals shared between run_gemini_web_command error detection
# and generate()'s auto-re-login trigger. Keep in sync with vendor error messages.
_AUTH_SIGNALS = ["401", "403", "auth error", "login required", "session expired",
                 "cookie expired", "missing __secure", "not authenticated",
                 "failed to initialize client", "make sure cookie",
                 "secure_1psidts could get expired"]


def _urlopen_with_proxy_and_ssl(req, timeout, ssl_ctx):
    """Like urllib.request.urlopen but respects system proxy + custom SSL context."""
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(),  # auto-detect system proxy
            urllib.request.HTTPSHandler(context=ssl_ctx),
        )
        return opener.open(req, timeout=timeout)
    except Exception:
        # If proxy setup itself fails, fall back to direct connection
        return urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx)


def _is_retryable_error(error_msg):
    """Check if an error from gemini-web is a network issue (retryable)
    vs an auth/config issue (not retryable)."""
    msg_lower = error_msg.lower()
    network_keywords = [
        "timeout", "timed out", "connection", "reset", "refused",
        "eof", "network", "unreachable", "temporary failure",
        "ssl", "tls", "broken pipe",
    ]
    non_retryable_keywords = [
        "login", "auth", "cookie", "401", "403", "blocked",
        "not found", "model", "bun",
    ]
    for kw in non_retryable_keywords:
        if kw in msg_lower:
            return False
    for kw in network_keywords:
        if kw in msg_lower:
            return True
    return False  # default: don't retry unknown errors


def _submit_gemini_web_with_retry(api_config, prompt, output_path, use_ip=False):
    """Call submit_task_gemini_web with progressive retry on network errors.

    Retry schedule: 5s → 10s → 20s (3 retries, 4 total attempts).
    Non-network errors (auth, config) are NOT retried.
    """
    delays = [5, 10, 20]
    last_error = None
    total_attempts = len(delays) + 1

    for attempt in range(total_attempts):
        try:
            submit_task_gemini_web(api_config, prompt, output_path, use_ip)
            return  # success
        except Exception as e:
            last_error = e
            error_msg = str(e)
            if not _is_retryable_error(error_msg):
                raise  # auth/config error, don't retry
            if attempt < len(delays):
                delay = delays[attempt]
                logger.info(f"   🔄 网络波动，{delay}s 后重试 ({attempt+2}/{total_attempts})...")
                time.sleep(delay)
            # else: last attempt failed, fall through to raise

    raise last_error


def extract_context(text_block):
    match = re.search(r'>\s*Context\s*[:：]\s*["“](.*?)["”]', text_block, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r'>\s*Context\s*[:：]\s*(.+)', text_block, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def parse_visual_brief(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Base title from filename
    filename_title = sanitize_filename(Path(file_path).stem)
    title = filename_title

    # 2. Fallback: If filename is generic "Storyboard", use parent directory name (Project Name)
    if title.lower() == "storyboard":
        parent_dir = Path(file_path).parent.name
        if parent_dir:
            title = sanitize_filename(parent_dir)

    # 3. Override: Explicit frontmatter title has highest priority
    fm_match = re.search(r'^title:\s*"(.+?)"', content, re.MULTILINE)
    if fm_match:
        title = sanitize_filename(fm_match.group(1))

    tasks = []

    # 1. Main Cover
    if "cover-main" in content or "主视觉" in content:
        section_match = re.search(r'#{2,3}\s*Part\s*A[:：][^\n]*主视觉.*?(?=#{2,3}\s*Part\s*B|##|\Z)', content, re.DOTALL | re.IGNORECASE)
        if section_match:
            section_text = section_match.group(0)
            prompt_match = re.search(r'```(?:\w+)?\n(.*?)```', section_text, re.DOTALL)
            if prompt_match:
                prompt = clean_prompt(prompt_match.group(1))
                if prompt:
                    dims = ASPECT_RATIOS["cover-main"]
                    tasks.append({
                        "type": "cover-main", "prompt": prompt,
                        "width": dims["width"], "height": dims["height"],
                        "suffix": "cover-main",
                        "use_ip": check_ip_requirement(section_text),
                        "context": None,
                        "should_upload": False,
                    })

    # 2. Sidebar Cover
    if "cover-sidebar" in content or "侧边栏" in content:
        section_match = re.search(r'#{2,3}\s*Part\s*B[:：][^\n]*侧边栏.*?(?=##|\Z)', content, re.DOTALL | re.IGNORECASE)
        if section_match:
            section_text = section_match.group(0)
            prompt_match = re.search(r'```(?:\w+)?\n(.*?)```', section_text, re.DOTALL)
            if prompt_match:
                prompt = clean_prompt(prompt_match.group(1))
                if prompt:
                    dims = ASPECT_RATIOS["cover-sidebar"]
                    tasks.append({
                        "type": "cover-sidebar", "prompt": prompt,
                        "width": dims["width"], "height": dims["height"],
                        "suffix": "cover-sidebar",
                        "use_ip": check_ip_requirement(section_text),
                        "context": None,
                        "should_upload": False,
                    })

    # 3. In-article Illustrations
    illustration_count = 0
    for match in re.finditer(r'#{2,3}\s*Part\s*C[:：][^\n]*内文配图.*?(?=#{2,3}\s*Part\s*[A-Z]|\Z)', content, re.DOTALL | re.IGNORECASE):
        section_text = match.group(0)
        for block in re.finditer(r'####\s*插图\s*\d+.*?(?=####\s*插图|##|\Z)', section_text, re.DOTALL):
            block_text = block.group(0)

            # Extract Description
            desc_match = re.match(r'####\s*插图\s*\d+[:：]?\s*(.*)', block_text)
            description = ""
            if desc_match:
                description = re.sub(r'[<>:"/\\|?*]', '', desc_match.group(1)).strip()

            prompt_match = re.search(r'```(?:\w+)?\n(.*?)```', block_text, re.DOTALL)
            if not prompt_match: continue

            prompt = clean_prompt(prompt_match.group(1))
            if not prompt: continue

            illustration_count += 1
            dims = ASPECT_RATIOS["illustration"]
            context = extract_context(block_text)

            tasks.append({
                "type": "illustration",
                "prompt": prompt,
                "width": dims["width"],
                "height": dims["height"],
                "suffix": f"illustration-{illustration_count:02d}",
                "use_ip": check_ip_requirement(block_text),
                "context": context,
                "description": description,
                "should_upload": True,
            })

    return title, tasks

# --- Generation Logic ---

def _is_openai_compatible(api_config):
    """Detect whether the gemini config points to an OpenAI-compatible proxy (packyapi, etc.)
    rather than Google's native API.

    Priority: explicit 'protocol' field > auto-detection (sk- key prefix + base_url heuristic).
    Set "protocol": "google" or "protocol": "openai" in api_keys.json to override auto-detection.
    """
    protocol = api_config.get("protocol", "").lower()
    if protocol == "openai":
        return True
    if protocol == "google":
        return False
    # Auto-detect: sk- prefix = OpenAI-format key; non-googleapis base URL = third-party proxy
    api_key = api_config.get("api_key", "")
    base_url = api_config.get("base_url", "")
    return api_key.startswith("sk-") or "googleapis.com" not in base_url


def _build_aspect_prompt(prompt, width, height):
    """Append aspect ratio hints to the prompt for better composition."""
    ratio = int(width) / int(height)
    if ratio > 1.7:
        return prompt + ", cinematic anamorphic shot, 2.35:1 aspect ratio"
    elif ratio < 0.6:
        return prompt + ", tall portrait shot, 9:16 aspect ratio"
    elif ratio < 0.85:
        return prompt + ", portrait shot, 3:4 aspect ratio"
    return prompt


def _load_ip_b64():
    """Load IP reference image as base64 data URI string."""
    ip_image_path = Path(__file__).resolve().parent.parent / "assets" / "IP_Reference.jpg"
    if not ip_image_path.exists():
        logger.warning("[Gemini] IP flag is ON, but reference image not found.")
        return None
    try:
        with open(ip_image_path, "rb") as img_f:
            return base64.b64encode(img_f.read()).decode("utf-8")
    except Exception as e:
        logger.warning(f"[Gemini] Failed to load IP image: {e}")
        return None


def _extract_image_openai(data):
    """Extract base64 image data from OpenAI-compatible chat completions response.
    Supports multiple proxy response formats:
      - choices[0].message.images[0].image_url.url  (liteLLM / OpenRouter)
      - choices[0].message.content (raw base64 or data URI)
    """
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})

    # Format 1: images array (liteLLM / OpenRouter standard)
    images = msg.get("images", [])
    if images:
        url = images[0].get("image_url", {}).get("url", "")
        if url:
            if url.startswith("data:"):
                return url.split(",", 1)[1]
            return url

    # Format 2: content is a list with image_url parts (OpenAI multimodal format)
    content = msg.get("content", "")
    if isinstance(content, list):
        for part in content:
            if part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                if url.startswith("data:"):
                    return url.split(",", 1)[1]
                return url

    # Format 3: Markdown image syntax ![alt](data:...) from some proxies (packyapi etc.)
    if isinstance(content, str) and content.strip():
        md_match = re.search(r'!\[.*?\]\((data:[^)]+)\)', content)
        if md_match:
            data_uri = md_match.group(1)
            if data_uri.startswith("data:"):
                return data_uri.split(",", 1)[1]
            return data_uri

    # Format 4: content is a raw base64 string or data URI
    if isinstance(content, str) and content.strip():
        if content.startswith("data:"):
            return content.split(",", 1)[1]
        # Must look like valid base64 (not a natural-language text response)
        if len(content) > 100 and not content.startswith("{"):
            if re.match(r'^[A-Za-z0-9+/=\s]+$', content):
                return content

    raise RuntimeError(f"No image data in response. Preview: {str(msg)[:300]}")


def submit_task_gemini(api_config, prompt, width, height, use_ip=False):
    require_config(api_config, "Gemini API", ["base_url", "model", "api_key"])

    base_url = api_config['base_url'].rstrip('/')
    if base_url.endswith('/models'):
        base_url = base_url[:-7]
    model_id = api_config['model']
    api_key = api_config['api_key']
    tuned_prompt = _build_aspect_prompt(prompt, width, height)

    if _is_openai_compatible(api_config):
        return _submit_gemini_openai(base_url, model_id, api_key, tuned_prompt, use_ip, api_config)
    else:
        return _submit_gemini_native(base_url, model_id, api_key, tuned_prompt, use_ip, api_config)


def _submit_gemini_native(base_url, model_id, api_key, prompt, use_ip, api_config=None):
    """Call Google's native Gemini API (:generateContent endpoint)."""
    url = f"{base_url}/models/{model_id}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    parts = [{"text": prompt}]

    if use_ip:
        ip_b64 = _load_ip_b64()
        if ip_b64:
            parts.append({"inlineData": {"mimeType": "image/png", "data": ip_b64}})

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
    }

    req = urllib.request.Request(url, headers=headers, data=json.dumps(payload).encode('utf-8'))
    logger.info("[Gemini Native] Calling Google Gemini API...")

    return _gemini_request_with_retry(req, lambda data: _extract_image_native(data), api_config)


def _submit_gemini_openai(base_url, model_id, api_key, prompt, use_ip, api_config=None):
    """Call Gemini via OpenAI-compatible proxy (packyapi, etc.) using /v1/chat/completions."""
    url = f"{base_url}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    content = prompt
    if use_ip:
        ip_b64 = _load_ip_b64()
        if ip_b64:
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{ip_b64}"}}
            ]

    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": content}]
    }

    req = urllib.request.Request(url, headers=headers, data=json.dumps(payload).encode('utf-8'))
    logger.info(f"[Gemini OpenAI] Calling {url} with model {model_id}...")

    return _gemini_request_with_retry(req, lambda data: _extract_image_openai(data), api_config)


def _gemini_request_with_retry(req, extract_fn, api_config=None):
    """Send request with progressive retry for network errors.

    Retry schedule for network errors: 5s → 10s → 20s (4 total attempts).
    On first network failure, switches to permissive SSL (no verification)
    for subsequent attempts. HTTP 429/5xx errors get a single fast retry.
    """
    ssl_ctx = _build_ssl_context(api_config)
    network_delays = [5, 10, 20]

    for attempt in range(len(network_delays) + 1):
        try:
            with _urlopen_with_proxy_and_ssl(req, TIMEOUT_GEMINI_API, ssl_ctx) as resp:
                data = json.load(resp)
                return extract_fn(data)
        except urllib.error.HTTPError as e:
            if (e.code == 429 or 500 <= e.code < 600) and attempt < 1:
                logger.info(f"[Gemini] Error {e.code}, retrying...")
                time.sleep(3)
                continue
            body = e.read().decode('utf-8', errors='replace')[:300]
            raise RuntimeError(f"Gemini failed ({e.code}): {body}") from e
        except (urllib.error.URLError, OSError) as e:
            if attempt < len(network_delays):
                delay = network_delays[attempt]
                logger.info(f"[Gemini] 网络波动，{delay}s 后重试 ({attempt+2}/{len(network_delays)+1})...")
                time.sleep(delay)
                # Fall back to permissive SSL on retry for third-party proxies
                if attempt == 0:
                    ssl_ctx = _build_ssl_context({"ssl_verify": False})
                continue
            raise RuntimeError(f"Gemini network failed: {e}") from e


def _extract_image_native(data):
    """Extract base64 image data from Google-native Gemini API response."""
    try:
        parts_resp = data["candidates"][0]["content"]["parts"]
        for part in parts_resp:
            if "inlineData" in part:
                return part["inlineData"]["data"]
            if "inline_data" in part:
                return part["inline_data"]["data"]
        raise RuntimeError(f"No image data. Preview: {str(parts_resp)[:200]}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected format: {str(data)[:500]}") from e

def submit_task_gemini_web(api_config, prompt, output_path, use_ip=False):
    settings = resolve_gemini_web_settings(api_config)
    cmd = [
        "--prompt", prompt,
        "--image", output_path.resolve().as_posix(),
        "--model", settings["model"],
        "--profile-dir", str(settings["profile_dir"]),
        "--cookie-path", str(settings["cookie_path"]),
    ]

    if use_ip:
        ip_image_path = Path(__file__).resolve().parent.parent / "assets" / "IP_Reference.jpg"
        if ip_image_path.exists():
            cmd.extend(["--reference", ip_image_path.resolve().as_posix()])
            logger.info("[Gemini Web] IP Reference injected")
        else:
            logger.warning("[Gemini Web] IP flag is ON, but reference image not found.")

    run_gemini_web_command(api_config, cmd, timeout=settings["timeout"])

    if not output_path.exists():
        raise RuntimeError(f"gemini-web did not create output file: {output_path}")

def login_gemini_web(api_config):
    result, settings = run_gemini_web_command(
        api_config,
        [
            "--login",
            "--profile-dir", str(resolve_gemini_web_settings(api_config)["profile_dir"]),
            "--cookie-path", str(resolve_gemini_web_settings(api_config)["cookie_path"]),
        ],
        timeout=TIMEOUT_GEMINI_WEB_LOGIN,
    )
    logger.info(result.stdout.strip() or f"Gemini Web login prepared: {settings['cookie_path']}")

def submit_task_siliconflow(api_config, prompt, width, height):
    require_config(api_config, "SiliconFlow", ["base_url", "model", "api_key"])
    url = f"{api_config['base_url']}images/generations"
    headers = {"Authorization": f"Bearer {api_config['api_key']}", "Content-Type": "application/json"}
    payload = {
        "model": api_config["model"], "prompt": prompt,
        "image_size": f"{int(width)}x{int(height)}", "batch_size": 1,
        "num_inference_steps": 20, "guidance_scale": 3.5
    }

    req = urllib.request.Request(url, headers=headers, data=json.dumps(payload).encode('utf-8'))
    try:
        with _urlopen_with_proxy_and_ssl(req, TIMEOUT_SILICONFLOW, _SSL_CONTEXT) as resp:
            data = json.load(resp)
            if "data" in data and len(data["data"]) > 0: return data["data"][0]["url"]
            raise RuntimeError(f"Unexpected response: {data}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"SiliconFlow failed ({e.code}): {e.read().decode('utf-8', errors='replace')[:200]}...") from e

def submit_task_gpt_image2(api_config, prompt, width, height, use_ip=False):
    """Generate image via gpt-image-2 using OpenAI-compatible endpoint."""
    require_config(api_config, "GPT-Image2", ["base_url", "model", "api_key"])

    url = f"{api_config['base_url'].rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {api_config['api_key']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": api_config["model"],
        "prompt": prompt,
        "size": f"{int(width)}x{int(height)}",
        "n": 1,
        "response_format": "b64_json"
    }

    req = urllib.request.Request(url, headers=headers, data=json.dumps(payload).encode('utf-8'))
    max_retries = 1
    for attempt in range(max_retries + 1):
        try:
            with _urlopen_with_proxy_and_ssl(req, TIMEOUT_GPT_IMAGE2, _SSL_CONTEXT) as resp:
                data = json.load(resp)
                if "data" in data and len(data["data"]) > 0:
                    return data["data"][0]["b64_json"]
                raise RuntimeError(f"Unexpected response: {str(data)[:200]}")
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            if (e.code == 429 or 500 <= e.code < 600) and attempt < max_retries:
                logger.info(f"[GPT-Image2] Error {e.code}, retrying...")
                time.sleep(3)
                continue
            raise RuntimeError(f"GPT-Image2 failed ({e.code}): {body[:200]}...") from e

# --- Pipeline Class ---

class VisualPipeline:
    def __init__(self, api_config, output_dir, force=False, switch_to_api=False):
        self.config = api_config
        self.output_dir = output_dir
        self.force = force
        self.manifest_path = output_dir / "manifest.json"
        self.manifest = self._load_manifest()
        self._gemini_web_checked = False  # batch-level guard: validate session only once
        self._gemini_web_ready = False   # cached result of session check
        self._gemini_web_failures = 0
        self._switch_to_api = switch_to_api
        self._web_failure_asked = False  # only ask once per batch

        if TINIFY_AVAILABLE and "tinify" in self.config and self.config["tinify"].get("api_key"):
            tinify.key = self.config["tinify"]["api_key"]
            self.compress_enabled = True
        else:
            self.compress_enabled = False

        if COS_AVAILABLE and "cos" in self.config:
            cos_conf = self.config["cos"]
            required_keys = ["region", "secret_id", "secret_key", "bucket"]
            if all(k in cos_conf and cos_conf[k] for k in required_keys):
                self.cos_config = CosConfig(
                    Region=cos_conf["region"],
                    SecretId=cos_conf["secret_id"],
                    SecretKey=cos_conf["secret_key"]
                )
                self.cos_client = CosS3Client(self.cos_config)
                self.bucket = cos_conf["bucket"]
                self.cdn_domain = cos_conf.get("cdn_domain", "")
                self.upload_enabled = True
            else:
                logger.warning(f"⚠️ COS config incomplete. Upload disabled.")
                self.upload_enabled = False
        else:
            self.upload_enabled = False

    def _resolve_providers(self, provider):
        if provider != "auto":
            return [provider]

        providers = []

        # HTTP first (uses cookies.json directly, no browser needed),
        # CDP as fallback (launches Chrome with injected cookies)
        if not self._switch_to_api:
            gemini_web_scripts = get_skill_root() / "vendor" / "baoyu-danger-gemini-web" / "scripts"
            if gemini_web_scripts.exists() and shutil.which("bun"):
                providers.append("gemini-web")
                # gemini-web-browser (CDP) as backup when HTTP fails
                providers.append("gemini-web-browser")

        # gemini API as fallback when web providers fail
        if self.config.get("gemini"):
            providers.append("gemini")

        if self.config.get("gpt-image2"):
            providers.append("gpt-image2")
        if self.config.get("siliconflow"):
            providers.append("siliconflow")

        return providers

    def _load_manifest(self):
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return {}

    def _save_manifest(self):
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(self.manifest, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"⚠️ Failed to save manifest: {e}")

    def _enforce_ratio(self, img_path, target_w, target_h):
        """Deterministically force image to target dimensions (Aspect Fill + Top-Weighted Crop)."""
        if not PIL_AVAILABLE or not img_path.exists(): return False

        try:
            with Image.open(img_path) as img:
                src_w, src_h = img.size
                if (src_w, src_h) == (target_w, target_h):
                    return False

                logger.info(f"✂️  Enforcing {target_w}x{target_h} for {img_path.name}...")

                # Aspect Fill logic
                scale_w = target_w / src_w
                scale_h = target_h / src_h
                scale = max(scale_w, scale_h)

                new_w = int(src_w * scale)
                new_h = int(src_h * scale)
                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Top-Weighted Crop
            diff_w = new_w - target_w
            diff_h = new_h - target_h

            left = diff_w / 2
            top = diff_h * 0.2 # Bias: keep top 20% visible, cut mostly from bottom
            right = left + target_w
            bottom = top + target_h

            img_final = img_resized.crop((left, top, right, bottom))
            img_final.save(img_path, quality=95)
            return True

        except Exception as e:
            logger.warning(f"⚠️ Ratio enforcement failed: {e}")
            return False

    def _maybe_ask_switch_to_api(self):
        """If web failures reached threshold, print switch-to-api suggestion once."""
        if self._gemini_web_failures >= 2 and not self._web_failure_asked and not self._switch_to_api:
            if self.config.get("gemini"):
                self._web_failure_asked = True
                logger.warning("")
                logger.warning("═" * 50)
                logger.warning("⚠️  gemini-web 连续失败，是否切换到付费的 gemini-api？")
                logger.warning(f"   重试: PYTHONIOENCODING=utf-8 python {__file__} --brief <Storyboard> --draft <Draft> --provider gemini")
                logger.warning("═" * 50)

    def _ensure_gemini_web_ready(self):
        """Validate gemini-web session once per batch.

        Three-tier recovery (only runs on first call; subsequent calls short-circuit):
          L1: HTTP validate cached cookies (fast, no subprocess)
          L2: Rotate __Secure-1PSIDTS via HTTP (silent refresh)
          L3: Launch Chrome with persistent profile for CDP cookie extraction.
              After L3, skips HTTP re-validation (VPN may block Python urllib
              even when Chrome CDP succeeds) — trusts that Chrome wrote valid cookies.

        Returns True if session is (or was made) ready, False if all tiers exhausted.
        """
        # Batch-level guard: only validate once per pipeline instance
        if self._gemini_web_checked:
            return self._gemini_web_ready

        self._gemini_web_checked = True
        settings = resolve_gemini_web_settings(self.config)
        cookie_path = settings["cookie_path"]

        # L1: Try cached cookies via lightweight HTTP check
        if cookie_path.exists():
            cookies = _read_cookies_from_file(cookie_path)
            if cookies:
                valid, reason = _validate_gemini_session_http(cookies)
                if valid:
                    logger.info("✅ gemini-web session valid (HTTP check)")
                    self._gemini_web_ready = True
                    return True
                logger.info(f"🔐 gemini-web session check: {reason}")

                # L2: Try cookie rotation (silent HTTP refresh)
                logger.info("   🔄 尝试 HTTP 续期 (L2)...")
                new_1psidts = _rotate_cookie_http(cookies)
                if new_1psidts:
                    cookies["__Secure-1PSIDTS"] = new_1psidts
                    valid2, reason2 = _validate_gemini_session_http(cookies)
                    if valid2:
                        try:
                            _gwu.write_cookies_to_file(cookie_path, cookies, source="rotate-http")
                            logger.info("   ✅ Cookie 续期成功 (L2)")
                        except Exception as e:
                            logger.warning(f"   ⚠️ 保存续期 cookie 失败: {e}")
                        self._gemini_web_ready = True
                        return True
                    logger.info(f"   ⚠️ 续期后仍无效: {reason2}")
                else:
                    logger.info("   ⚠️ Cookie 续期失败，进入 L3")
        else:
            logger.info("🔐 gemini-web: no cookie file found")

        # L3: Launch Chrome with persistent profile for CDP cookie extraction.
        # NOTE: After L3, we do NOT re-validate via HTTP because Python urllib may
        # not be able to reach Google through the user's VPN/proxy even when Chrome
        # CDP succeeds. We trust that if Chrome wrote cookies.json, they are valid.
        logger.info("   🔐 启动 Chrome 提取 cookie (L3)...")
        try:
            login_gemini_web(self.config)
            if cookie_path.exists():
                cookies = _read_cookies_from_file(cookie_path)
                if cookies and cookies.get("__Secure-1PSID"):
                    logger.info("   ✅ Chrome cookie 提取成功 (L3)")
                    self._gemini_web_ready = True
                    return True
            logger.error("   ❌ L3: Chrome 启动完成但未获取有效 cookie，可能需要手动登录")
            self._gemini_web_ready = False
            return False
        except Exception as e:
            logger.error(f"❌ gemini-web login failed: {e}")
            self._gemini_web_ready = False
            return False

    def _run_batch_internal(self, tasks, title, cdp=False):
        """Shared batch-submit logic for gemini-web and gemini-web-browser.

        Builds batch JSON, invokes bun command, parses results, updates manifest.
        cdp=False → HTTP batch (gemini-web), cdp=True → CDP batch (gemini-web-browser).
        """
        if not tasks:
            return {}

        settings = resolve_gemini_web_settings(self.config)

        batch_tasks = []
        for task in tasks:
            suffix = task['suffix']
            local_filename = f"{suffix}.jpg" if suffix.startswith("cover") else f"{title}-{suffix}.jpg"
            entry = {
                "prompt": task['prompt'],
                "image": str((self.output_dir / local_filename).resolve()),
            }
            if task.get('use_ip'):
                ip_path = Path(__file__).resolve().parent.parent / "assets" / "IP_Reference.jpg"
                if ip_path.exists():
                    entry["reference"] = [str(ip_path.resolve())]
            batch_tasks.append(entry)

        batch_input = {"model": settings["model"], "tasks": batch_tasks}

        input_name = "_batch_cdp_input.json" if cdp else "_batch_input.json"
        result_name = "_batch_result_cdp.json" if cdp else "_batch_result.json"
        label = "CDP" if cdp else "Batch"
        emoji = "🌐" if cdp else "📦"
        desc = "Chrome browser" if cdp else "gemini-web"
        per_task_timeout = 120 if cdp else 60

        batch_path = self.output_dir / input_name
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(batch_input, f, ensure_ascii=False, indent=2)

        logger.info(f"{emoji} {label}: {len(tasks)} tasks via {desc}...")

        extra_args = [
            "--batch-file", str(batch_path.resolve()),
            "--profile-dir", str(settings["profile_dir"]),
            "--cookie-path", str(settings["cookie_path"]),
        ]
        if cdp:
            extra_args.insert(0, "--cdp-generate")

        try:
            run_gemini_web_command(
                self.config, extra_args,
                timeout=settings["timeout"] + (len(tasks) * per_task_timeout),
            )
        except Exception as e:
            logger.error(f"❌ {label} batch failed: {e}")

        result_path = self.output_dir / result_name
        if not result_path.exists():
            logger.warning(f"⚠️ No {label} batch result file — all tasks failed.")
            return {}

        try:
            with open(result_path, "r", encoding="utf-8") as f:
                results = json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ Failed to read {label} batch results: {e}")
            return {}

        success_map = {}
        provider_name = "gemini-web-browser" if cdp else "gemini-web"
        for r in results:
            idx = r.get("index", -1)
            if idx < 0 or idx >= len(tasks):
                continue
            task = tasks[idx]
            if r.get("success"):
                current_hash = calculate_hash(
                    task['prompt'], task['width'], task['height'],
                    "gemini-web", task.get('use_ip', False),
                )
                self.manifest[task['suffix']] = {
                    "hash": current_hash,
                    "provider": provider_name,
                    "prompt": task['prompt'],
                    "updated_at": time.time(),
                    "url": None,
                    "compressed": False,
                }
                self._save_manifest()
                success_map[task['suffix']] = True
                logger.info(f"   ✅ {label} [{idx+1}/{len(tasks)}] {task['suffix']}")
            else:
                logger.error(f"   ❌ {label} [{idx+1}/{len(tasks)}] {task['suffix']}: {r.get('error', 'unknown')[:100]}")

        self._gemini_web_failures = 0
        return success_map

    def submit_gemini_web_batch(self, tasks, title):
        """Batch-submit gemini-web tasks in a single Bun process (HTTP)."""
        return self._run_batch_internal(tasks, title, cdp=False)

    def submit_gemini_web_browser_batch(self, tasks, title):
        """Batch-submit tasks via Chrome CDP (gemini-web-browser provider)."""
        return self._run_batch_internal(tasks, title, cdp=True)

    def generate(self, task, title, provider="auto"):
        # Cover files use simple names (deleted after publish); illustrations keep title prefix
        if task['suffix'].startswith("cover"):
            local_filename = f"{task['suffix']}.jpg"
        else:
            local_filename = f"{title}-{task['suffix']}.jpg"
        local_path = self.output_dir / local_filename

        providers = self._resolve_providers(provider)
        if not providers:
            logger.error("❌ No available providers. Check gemini-web vendor or API config.")
            return None, local_path

        preferred_provider = providers[0]
        current_hash = calculate_hash(
            task['prompt'],
            task['width'],
            task['height'],
            preferred_provider,
            task.get('use_ip', False)
        )

        cached = self.manifest.get(task['suffix'], {})

        # URL Cache Hit
        if (
            not self.force and
            cached.get("hash") == current_hash and
            cached.get("provider") == preferred_provider and
            cached.get("url")
        ):
            logger.info(f"⏭️  [Cache Hit] {task['suffix']} -> {cached['url']}")
            # Safety Net: Enforce Ratio on cached images (all types, needed for OpenAI-compatible providers)
            if self._enforce_ratio(local_path, task['width'], task['height']):
                cached["compressed"] = False
            return cached['url'], local_path

        # Local File Cache Hit
        generated_new = False
        if (
            not self.force and
            local_path.exists() and
            cached.get("hash") == current_hash and
            cached.get("provider") == preferred_provider
        ):
             logger.info(f"📂 [Local Hit] {task['suffix']} exists.")
             # Safety Net: Enforce Ratio on cached images (all types)
             if self._enforce_ratio(local_path, task['width'], task['height']):
                 cached["compressed"] = False
        else:
            # Generate new image
            logger.info(f"🎨 Generating {task['suffix']}...")
            success = False

            provider_used = None

            # ── Local Pillow sidebar rendering (fast, reliable Chinese text) ──
            if (
                SIDEBAR_LOCAL_AVAILABLE
                and task.get('type') == 'cover-sidebar'
                and not success
            ):
                sidebar_params = parse_sidebar_prompt(task['prompt'])
                if sidebar_params is not None:
                    try:
                        img = render_sidebar_locally(
                            bg_color=sidebar_params['bg_color'],
                            line1=sidebar_params['line1'],
                            line2=sidebar_params['line2'],
                            decoration=sidebar_params.get('decoration'),
                            font_path=SIDEBAR_FONT_PATH,
                        )
                        img.save(local_path, quality=95)
                        provider_used = preferred_provider  # use AI provider name for manifest/cache consistency
                        success = True
                        dec_info = ""
                        if sidebar_params.get('decoration'):
                            dec_info = f" + {sidebar_params['decoration']['type']}"
                        logger.info(
                            f"✅ Local sidebar: '{sidebar_params['line1']}' / "
                            f"'{sidebar_params['line2']}' "
                            f"[{sidebar_params['bg_color']}]{dec_info}"
                        )
                    except Exception as e:
                        logger.warning(
                            "⚠️ Local sidebar render failed: %s, falling back to AI", e
                        )

            for p in providers:
                if success:
                    break
                try:
                    if p == "gemini":
                        b64 = submit_task_gemini(self.config["gemini"], task['prompt'], task['width'], task['height'], task.get('use_ip', False))
                        with open(local_path, "wb") as f: f.write(base64.b64decode(b64))
                        provider_used = p
                        success = True
                        break
                    if p == "gpt-image2":
                        b64 = submit_task_gpt_image2(self.config["gpt-image2"], task['prompt'], task['width'], task['height'], task.get('use_ip', False))
                        with open(local_path, "wb") as f: f.write(base64.b64decode(b64))
                        provider_used = p
                        success = True
                        break
                    if p == "gemini-web":
                        if not self._ensure_gemini_web_ready():
                            logger.warning("⚠️ gemini-web session unavailable, skipping...")
                            self._gemini_web_failures += 1
                            self._maybe_ask_switch_to_api()
                            continue
                        try:
                            _submit_gemini_web_with_retry(self.config, task['prompt'], local_path, task.get('use_ip', False))
                            provider_used = p
                            success = True
                            self._gemini_web_failures = 0
                            break
                        except Exception as e:
                            error_msg = str(e).lower()
                            # If generation fails due to auth/cookie, try one more auto-login then retry
                            if any(s in error_msg for s in _AUTH_SIGNALS):
                                logger.info("🔐 生成时检测到 cookie 过期，尝试自动重新登录...")
                                self._gemini_web_checked = False
                                self._gemini_web_ready = False
                                if self._ensure_gemini_web_ready():
                                    try:
                                        _submit_gemini_web_with_retry(self.config, task['prompt'], local_path, task.get('use_ip', False))
                                        provider_used = p
                                        success = True
                                        self._gemini_web_failures = 0
                                        break
                                    except Exception as e2:
                                        logger.error(f"❌ gemini-web 重新登录后仍失败: {e2}")
                                else:
                                    logger.warning("⚠️ 自动登录未成功")
                            raise  # re-raise to be caught by outer exception handler
                    if p == "gemini-web-browser":
                        if not self._ensure_gemini_web_ready():
                            logger.warning("⚠️ gemini-web-browser session unavailable, skipping...")
                            self._gemini_web_failures += 1
                            continue
                        # CDP single-task: wrap in batch format
                        result = self.submit_gemini_web_browser_batch([task], title)
                        if task['suffix'] in result:
                            provider_used = p
                            success = True
                            break
                    if p == "siliconflow":
                        image_url = submit_task_siliconflow(self.config["siliconflow"], task['prompt'], task['width'], task['height'])
                        # urlretrieve doesn't support custom SSL context; use urlopen + write
                        image_req = urllib.request.Request(image_url)
                        with _urlopen_with_proxy_and_ssl(image_req, 60, _SSL_CONTEXT) as img_resp:
                            with open(local_path, 'wb') as f:
                                f.write(img_resp.read())
                        provider_used = p
                        success = True
                        break
                except Exception as e:
                    logger.error(f"❌ {p} failed: {e}")
                    if p == "gemini-web":
                        self._gemini_web_failures += 1
                        self._maybe_ask_switch_to_api()

            if not success:
                logger.error(f"❌ Failed to generate {task['suffix']}")
                self._maybe_ask_switch_to_api()
                return None, local_path

            # Safety Net: Enforce Ratio on newly generated images (all types)
            if self._enforce_ratio(local_path, task['width'], task['height']):
                cached["compressed"] = False

            generated_new = True

        # COMPRESS
        if self.compress_enabled and local_path.exists() and (generated_new or not cached.get("compressed")):
            try:
                logger.info(f"🗜️  Compressing {local_filename}...")
                source = tinify.from_file(str(local_path))
                source.to_file(str(local_path))
                cached["compressed"] = True
            except Exception as e:
                logger.warning(f"⚠️ Compression failed: {e}")

        # UPLOAD (Illustrations only)
        final_url = None
        if self.upload_enabled and local_path.exists() and task.get('should_upload'):
            date_suffix = datetime.now().strftime("%Y%m%d")
            # Filename: {Project}_{Suffix}_{Hash}_{Date}.jpg (Flat structure in 'wechat/' folder)
            cos_filename = f"{title}_{task['suffix']}_{current_hash}_{date_suffix}.jpg"
            cos_key = f"wechat/{cos_filename}"
            try:
                logger.info(f"☁️  Uploading to COS: {cos_key}")
                self.cos_client.put_object_from_local_file(Bucket=self.bucket, LocalFilePath=str(local_path), Key=cos_key)
                if self.cdn_domain:
                    final_url = f"{self.cdn_domain.rstrip('/')}/{cos_key}"
                else:
                    final_url = self.cos_config.uri(self.bucket, cos_key)
                logger.info(f"✅ Uploaded: {final_url}")
            except Exception as e:
                logger.error(f"❌ Upload failed: {e}")

        if not final_url and cached.get("hash") == current_hash and cached.get("url"):
            final_url = cached["url"]

        self.manifest[task['suffix']] = {
            "hash": current_hash,
            "provider": cached.get("provider", preferred_provider) if not generated_new else provider_used,
            "prompt": task['prompt'],
            "updated_at": time.time(),
            "url": final_url,
            "compressed": cached.get("compressed", False)
        }
        self._save_manifest()

        return final_url, local_path

    def inject(self, draft_path, task, image_url):
        if not draft_path or not draft_path.exists(): return False
        if not task.get("context") or not image_url: return False

        context_sent = task["context"]
        logger.info(f"💉 Injecting {task['suffix']}...")

        with open(draft_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        matches = []
        for i, line in enumerate(lines):
            if context_sent in line:
                matches.append(i)

        if len(matches) == 0:
            logger.warning(f"⚠️ Injection Skipped: Context not found -> '{context_sent[:30]}...'")
            return False
        elif len(matches) > 1:
            logger.error(f"❌ Injection Failed: Context ambiguous ({len(matches)} matches) -> '{context_sent[:30]}...'")
            return False

        match_index = matches[0]
        # Fix: Ensure fallback to suffix if description is empty string (Falsey)
        alt_text = task.get("description") or task['suffix']

        existing_line_idx = -1
        is_exact_match = False

        for j in range(1, 10):
            if match_index + j < len(lines):
                idx = match_index + j
                line_content = lines[idx]
                img_match = re.search(r'!\[(.*?)\]\((.*?)\)', line_content)
                if img_match:
                    current_alt = img_match.group(1)
                    current_url = img_match.group(2)
                    if task['suffix'] in current_url:
                        existing_line_idx = idx
                        if image_url.strip() in current_url and current_alt.strip() == alt_text.strip():
                            is_exact_match = True
                        break

        if is_exact_match:
            logger.info("   ⏭️  Image already up-to-date, skipping.")
        elif existing_line_idx != -1:
            logger.info(f"   🔄 Updating stale link at line {existing_line_idx+1}...")
            lines[existing_line_idx] = f"![{alt_text}]({image_url})\n"
            with open(draft_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        else:
            img_md = f"\n![{alt_text}]({image_url})\n"
            lines.insert(match_index + 1, img_md)
            with open(draft_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            logger.info("   ✅ Injected successfully.")

        return True


# ── 封面检测（简单模式） ──

_SYSTEM_COVER_NAMES = {"cover-main", "cover-sidebar", "cover-combined"}
_COVER_RATIO_MIN = 2.20
_COVER_RATIO_MAX = 2.50


def detect_user_cover(img_dir):
    """Detect a user-provided 2.35:1 cover image in img_dir.

    Scans *.jpg / *.jpeg / *.png files, skipping known system-generated
    cover filenames.  Returns the first file whose aspect ratio falls within
    [_COVER_RATIO_MIN, _COVER_RATIO_MAX], or None if no match is found.

    When Pillow is unavailable, falls back to reading JPEG/PNG headers with
    the stdlib.  Non-JPEG/PNG files that Pillow cannot open are silently
    skipped.
    """
    if not img_dir.exists():
        return None

    candidates = sorted(
        p for p in img_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png")
        and p.stem not in _SYSTEM_COVER_NAMES
    )
    if not candidates:
        return None

    for path in candidates:
        w, h = _get_image_size(path)
        if w is None or h is None or h == 0:
            continue
        ratio = w / h
        if _COVER_RATIO_MIN <= ratio <= _COVER_RATIO_MAX:
            return path
    return None


def _get_image_size(path):
    """Return (width, height) for a JPEG or PNG file.

    Prefers Pillow; falls back to stdlib header parsing when unavailable.
    Returns (None, None) on failure.
    """
    # Try Pillow first
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size
    except ImportError:
        pass
    except Exception:
        # PIL can read it but something went wrong — fall through to stdlib
        pass

    # Fallback: read headers with stdlib
    try:
        return _read_jpeg_png_size_stdlib(path)
    except Exception:
        return None, None


def _read_jpeg_png_size_stdlib(path):
    """Read image dimensions from JPEG/PNG headers using only the stdlib.

    JPEG: scan for SOF0/SOF1/SOF2 marker (0xFF 0xC0-C2), read 2-byte
          height + width at offset +5 from marker.
    PNG:  signature (8 bytes) → IHDR chunk → width (4 bytes BE) +
          height (4 bytes BE) at offset 16.

    Returns (width, height) or raises ValueError on unsupported format.
    """
    with open(path, "rb") as f:
        header = f.read(24)

        # PNG: 89 50 4E 47 0D 0A 1A 0A
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            w = struct.unpack(">I", header[16:20])[0]
            h = struct.unpack(">I", header[20:24])[0]
            return w, h

        # JPEG: starts with FF D8 FF
        if header[:3] == b"\xff\xd8\xff":
            # Continue scanning from same file handle (header already consumed 24 bytes)
            f.seek(2)
            while True:
                marker = f.read(2)
                if len(marker) < 2:
                    break
                if marker[0] != 0xFF:
                    break
                # SOF0 (0xC0), SOF1 (0xC1), SOF2 (0xC2)
                if marker[1] in (0xC0, 0xC1, 0xC2):
                    f.read(3)  # skip length(2) + precision(1)
                    chunk = f.read(4)
                    h = struct.unpack(">H", chunk[:2])[0]
                    w = struct.unpack(">H", chunk[2:4])[0]
                    return w, h
                # Skip other markers
                seg_len_bytes = f.read(2)
                if len(seg_len_bytes) < 2:
                    break
                seg_len = struct.unpack(">H", seg_len_bytes)[0]
                if seg_len < 2:
                    break
                f.seek(seg_len - 2, 1)
            raise ValueError("Cannot find SOF marker in JPEG")

        raise ValueError(f"Unsupported image format: {path.suffix}")


def stitch_covers(output_dir, title, user_cover_path=None):
    """Stitch main cover + sidebar into a single combined cover.

    Full mode (user_cover_path=None):  cover-main.jpg + cover-sidebar.jpg
    Simple mode (user_cover_path set): user-supplied cover + cover-sidebar.jpg

    The main/sidebar images are horizontally concatenated.  The sidebar height
    determines the target height; the main image is resized proportionally.
    """
    if not PIL_AVAILABLE:
        return

    sidebar_path = output_dir / "cover-sidebar.jpg"
    if not sidebar_path.exists():
        return

    if user_cover_path is not None:
        main_path = Path(user_cover_path)
    else:
        main_path = output_dir / "cover-main.jpg"

    if not main_path.exists():
        return

    combined_path = output_dir / "cover-combined.jpg"

    try:
        with Image.open(main_path) as img_main, Image.open(sidebar_path) as img_sidebar:
            target_height = img_sidebar.height
            aspect = img_main.width / img_main.height
            new_width = int(target_height * aspect)
            img_main_resized = img_main.resize((new_width, target_height), Image.Resampling.LANCZOS)

            combined = Image.new('RGB', (new_width + img_sidebar.width, target_height))
            combined.paste(img_main_resized, (0, 0))
            combined.paste(img_sidebar, (new_width, 0))
            combined.save(combined_path, quality=95)
        logger.info(f"🖼️  Stitched Cover: {combined_path}")
    except Exception as e:
        logger.error(f"❌ Stitching failed: {e}")

def _sync_to_archive(args, brief_path, output_dir, user_cover_path=None):
    """Post-archive sync: if draft is under published/, mirror Storyboard + img/ to the
    matching conductor/archive/ directory so the archived project stays complete."""
    if not args.draft:
        return
    draft_path = Path(args.draft)
    # Detect post-archive scenario: draft is directly under <repo>/published/
    try:
        repo_root = _obs.get_workspace_root()
    except Exception:
        return
    published_dir = repo_root / "published"
    archive_base = repo_root / "conductor" / "archive"
    try:
        draft_path_rel = draft_path.resolve().relative_to(published_dir.resolve())
    except ValueError:
        return  # draft is not under published/ — nothing to sync

    # Extract date prefix (first 8 chars = YYYYMMDD) from draft filename
    draft_stem = draft_path.stem
    if len(draft_stem) < 8:
        return
    date_prefix = draft_stem[:8]

    # Find the archive directory whose name starts with the same date prefix
    if not archive_base.exists():
        return
    candidates = [d for d in archive_base.iterdir() if d.is_dir() and d.name.startswith(date_prefix)]
    if not candidates:
        logger.warning(f"⚠️ No archive dir found with prefix '{date_prefix}' — skipping archive sync.")
        return

    # Use the most recently modified matching archive dir
    archive_dir = max(candidates, key=lambda d: d.stat().st_mtime)

    # Sync Storyboard.md
    if brief_path.exists():
        dest_storyboard = archive_dir / brief_path.name
        try:
            shutil.copy2(brief_path, dest_storyboard)
            logger.info(f"📋 Synced Storyboard to archive: {dest_storyboard.name}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to sync Storyboard to archive: {e}")

    # Sync img/ directory
    dest_img = archive_dir / "img"
    if output_dir.exists():
        try:
            if dest_img.exists():
                # Merge: copy only newer or missing files
                for f in output_dir.iterdir():
                    if f.is_file():
                        target = dest_img / f.name
                        if not target.exists() or f.stat().st_mtime > target.stat().st_mtime:
                            shutil.copy2(f, target)
            else:
                shutil.copytree(output_dir, dest_img)
            logger.info(f"🖼️  Synced img/ to archive: {archive_dir.name}/img/")
        except Exception as e:
            logger.warning(f"⚠️ Failed to sync img/ to archive: {e}")

    # 简单模式：同步用户封面到归档
    if user_cover_path is not None and user_cover_path.exists():
        dest_cover = dest_img / user_cover_path.name
        try:
            if not dest_cover.exists() or user_cover_path.stat().st_mtime > dest_cover.stat().st_mtime:
                shutil.copy2(user_cover_path, dest_cover)
                logger.info(f"🖼️  Synced user cover to archive: {user_cover_path.name}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to sync user cover to archive: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", help="Path to Storyboard.md")
    parser.add_argument("--draft", help="Path to Draft.md for injection")
    parser.add_argument("--output-dir")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--provider", default="auto", choices=["auto", "gemini-web-browser", "gemini-web", "gemini", "gpt-image2", "siliconflow"])
    parser.add_argument("--gemini-web-login", action="store_true", help="Initialize Gemini Web login, then exit")
    parser.add_argument("--mode", default="full", choices=["full", "simple"],
                        help="配图模式: full=完整生成, simple=仅sidebar+拼接 (default: full)")
    parser.add_argument("--cover", default=None,
                        help="简单模式下显式指定封面图路径, 跳过自动检测")
    args = parser.parse_args()

    try:
        api_config = load_api_config()
    except Exception as e:
        logger.error(str(e))
        return

    if args.gemini_web_login:
        try:
            login_gemini_web(api_config)
        except Exception as e:
            logger.error(str(e))
        return

    if not args.brief:
        logger.error("--brief is required unless --gemini-web-login is used.")
        return

    brief_path = Path(args.brief)
    if not brief_path.exists():
        logger.error(f"File not found: {brief_path}")
        return

    # 简单模式：确定封面图路径
    user_cover_path = None
    if args.mode == "simple":
        if args.cover:
            user_cover_path = Path(args.cover)
            if not user_cover_path.exists():
                logger.error(f"指定的封面图不存在: {args.cover}")
                return
        else:
            # 自动检测（由 LLM 在 Step 0.5 预检通过后才调用脚本）
            img_dir = Path(args.output_dir) if args.output_dir else brief_path.parent / "img"
            if img_dir.exists():
                user_cover_path = detect_user_cover(img_dir)
            if user_cover_path is None:
                logger.error("未在 img/ 下检测到 2.35:1 封面图。")
                logger.error("封面要求: 2.35:1 超宽幅 (推荐 900×383), 放入 img/ 后重新运行。")
                return
            logger.info(f"检测到封面图: {user_cover_path.name}")

        # 校验封面尺寸
        cover_w, cover_h = _get_image_size(user_cover_path)
        if cover_w is None or cover_h is None or cover_h == 0:
            logger.error(f"无法读取封面图尺寸: {user_cover_path}")
            return
        cover_ratio = cover_w / cover_h
        if not (_COVER_RATIO_MIN <= cover_ratio <= _COVER_RATIO_MAX):
            logger.error(
                f"封面宽高比 {cover_ratio:.2f} 不符合要求 "
                f"(需 {_COVER_RATIO_MIN:.2f}~{_COVER_RATIO_MAX:.2f}, "
                f"推荐 900×383)。当前: {cover_w}x{cover_h}"
            )
            return
        logger.info(f"封面校验通过: {cover_w}x{cover_h} (比例 {cover_ratio:.2f})")

    output_dir = Path(args.output_dir) if args.output_dir else brief_path.parent / "img"
    output_dir.mkdir(parents=True, exist_ok=True)

    title, tasks = parse_visual_brief(brief_path)
    if not tasks:
        logger.warning("No tasks found.")
        # ── Diagnostic: scan the file for common format mistakes ──
        with open(brief_path, "r", encoding="utf-8") as _f:
            _content = _f.read()
        has_part_a = bool(re.search(r'Part\s*A', _content, re.IGNORECASE))
        has_part_b = bool(re.search(r'Part\s*B', _content, re.IGNORECASE))
        has_part_c = bool(re.search(r'Part\s*C', _content, re.IGNORECASE))
        has_visual = bool(re.search(r'主视觉|cover-main', _content))
        has_sidebar = bool(re.search(r'侧边栏|cover-sidebar', _content))
        has_illus = bool(re.search(r'内文配图|illustration', _content))
        has_triple = bool(re.search(r'^###\s', _content, re.MULTILINE))
        has_double = bool(re.search(r'^##\s', _content, re.MULTILINE))
        has_context_blockquote = bool(re.search(r'^>\s*Context', _content, re.MULTILINE))
        has_context_in_code = bool(re.search(r'```[^`]*>\s*Context', _content, re.DOTALL))
        logger.warning("  Diagnostic:")
        logger.warning(f"    Part A text found: {has_part_a}, Part B: {has_part_b}, Part C: {has_part_c}")
        logger.warning(f"    主视觉/cover-main: {has_visual}, 侧边栏/cover-sidebar: {has_sidebar}, 内文配图: {has_illus}")
        logger.warning(f"    ### headings: {has_triple}, ## headings: {has_double}")
        logger.warning(f"    Context as blockquote (> Context): {has_context_blockquote}")
        logger.warning(f"    Context inside code block: {has_context_in_code}")
        if has_double and not has_triple:
            logger.warning("  ⚠️ Storyboard uses '##' for Part headings — should be '###' (three #).")
        if has_context_in_code and not has_context_blockquote:
            logger.warning("  ⚠️ '> Context:' is inside a code block — should be a standalone blockquote.")
        if has_part_c and not has_illus:
            logger.warning("  ⚠️ Part C found but no '内文配图' or 'illustration' keyword in heading.")
        return

    # 简单模式：防御性过滤 — 仅保留 Part B 任务
    if args.mode == "simple":
        tasks = [t for t in tasks if t.get("type") == "cover-sidebar"]
        if not tasks:
            logger.error("Storyboard 中未找到 Part B (cover-sidebar) 任务。")
            return
        logger.info(f"📋 简单模式: {len(tasks)} 个 sidebar 任务")

    pipeline = VisualPipeline(api_config, output_dir, force=args.force,
                              switch_to_api=(args.provider in ("gemini", "gpt-image2")))

    print(f"🎬 Director v{DIRECTOR_VERSION} starting for '{title}'")
    print(f"   Tasks: {len(tasks)} | Provider: {args.provider}")
    print(f"   Compression: {'ON' if pipeline.compress_enabled else 'OFF'}")
    print(f"   Upload: {'ON' if pipeline.upload_enabled else 'OFF'}")
    print("-" * 40)

    # Batch HTTP tasks first (2+ tasks → single Bun session, uses cookies.json directly)
    # Fallback chain: HTTP → CDP → per-task API fallback
    # Skip cover-sidebar tasks — they're handled locally by Pillow in generate()
    providers = pipeline._resolve_providers(args.provider)
    batch_tasks = [t for t in tasks if t.get('type') != 'cover-sidebar']
    if providers and providers[0] == "gemini-web" and len(batch_tasks) >= 2:
        if pipeline._ensure_gemini_web_ready():
            pipeline.submit_gemini_web_batch(batch_tasks, title)
            # Collect tasks that failed in HTTP batch for CDP fallback
            cdp_tasks = [t for t in batch_tasks
                         if not (pipeline.manifest.get(t['suffix'], {}).get("provider") == "gemini-web"
                                 and pipeline.manifest.get(t['suffix'], {}).get("hash"))]
            if cdp_tasks and "gemini-web-browser" in providers:
                logger.info(f"🔄 {len(cdp_tasks)} task(s) failed HTTP batch, trying CDP...")
                pipeline.submit_gemini_web_browser_batch(cdp_tasks, title)

    # Batch CDP when gemini-web-browser is explicitly selected (2+ tasks → single CDP session)
    batch_tasks_cdp = [t for t in tasks if t.get('type') != 'cover-sidebar']
    if providers and providers[0] == "gemini-web-browser" and len(batch_tasks_cdp) >= 2:
        if pipeline._ensure_gemini_web_ready():
            pipeline.submit_gemini_web_browser_batch(batch_tasks_cdp, title)

    for task in tasks:
        url, local_path = pipeline.generate(task, title, provider=args.provider)

        image_url = url
        if not image_url and not pipeline.upload_enabled and local_path and local_path.exists():
            image_url = f"img/{local_path.name}"

        injection_done = False
        # 简单模式：封面类任务不注入正文
        if args.mode == "simple":
            if local_path and local_path.exists():
                logger.info(f"ℹ️  简单模式: 保留本地文件 {local_path.name}")
            else:
                logger.warning(f"⚠️  简单模式: 生成失败，无本地文件 {local_path.name if local_path else 'N/A'}")
        elif args.draft and image_url and task.get("context"):
            injection_done = pipeline.inject(Path(args.draft), task, image_url)
        elif not args.draft:
            logger.info(f"ℹ️  Skipping injection (no draft provided). Local file retained: {local_path.name}")
        elif not task.get("context"):
             logger.warning(f"⚠️ Skipping injection (missing context). Local file retained: {local_path.name}")

        if url and not task.get('should_upload') and injection_done:
            try:
                if local_path.exists():
                    local_path.unlink()
                    logger.info(f"🗑️  Cleanup: Deleted local file {local_path.name}")
            except Exception as e:
                logger.warning(f"⚠️ Cleanup failed: {e}")

    stitch_covers(output_dir, title, user_cover_path)

    # --- Post-archive sync: if draft is under published/, mirror outputs to conductor/archive/ ---
    _sync_to_archive(args, brief_path, output_dir, user_cover_path=user_cover_path)

    # --- Obsidian CLI Enhancements (完整模式) ---
    if args.mode != "simple":
        cli_ok = shutil.which("obsidian") is not None
        if cli_ok and args.draft:
            draft_p = Path(args.draft)
            if draft_p.exists() and _obs.is_obsidian_reachable(draft_p):
                # 1. Set property (Verify result)
                if _obs.set_obsidian_properties(draft_p, {"visual_ready": True}):
                    logger.info(f"🏷️  Marked 'visual_ready: true' in {draft_p.name}")
                    # 2. Open in GUI for preview
                    if _obs.obsidian_open(draft_p):
                        logger.info(f"🚀 Focus jumping to Obsidian for preview: {draft_p.name}")
                else:
                    logger.warning(f"⚠️ Failed to mark 'visual_ready' in {draft_p.name} via CLI.")

    print("-" * 40)
    print("✅ Director finished.")

if __name__ == "__main__":
    main()
