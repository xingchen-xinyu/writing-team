#!/usr/bin/env python3
"""
Shared Gemini Web cookie utilities — used by both config_check.py and visualize.py.

No bun subprocess needed. Pure Python urllib HTTP calls.
"""

import json
import re
import ssl
import urllib.request
import urllib.error

# ── SSL context (http/1.1 + TLS 1.2 for proxy/VPN compatibility) ──

_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.set_alpn_protocols(['http/1.1'])
_SSL_CONTEXT.maximum_version = ssl.TLSVersion.TLSv1_2
if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
    _SSL_CONTEXT.options |= ssl.OP_LEGACY_SERVER_CONNECT

# ── Proxy-aware opener (respects system proxy settings like VPN) ──

def _build_https_handler():
    """Build an HTTPSHandler that uses our custom SSL context."""
    return urllib.request.HTTPSHandler(context=_SSL_CONTEXT)

# Build a shared opener that auto-detects system proxy settings.
# On Windows, ProxyHandler() reads from IE/Edge internet settings,
# which is what most VPN software configures.
try:
    _PROXY_OPENER = urllib.request.build_opener(
        urllib.request.ProxyHandler(),  # auto-detect system proxy
        _build_https_handler(),
    )
except Exception:
    _PROXY_OPENER = urllib.request.build_opener(_build_https_handler())


def urlopen_with_proxy(req, timeout=30):
    """Like urllib.request.urlopen but respects system proxy settings."""
    return _PROXY_OPENER.open(req, timeout=timeout)

# ── Constants ──

TIMEOUT_HTTP_VALIDATE = 30
TIMEOUT_HTTP_ROTATE = 30

GEMINI_INIT_URL = "https://gemini.google.com/app"
GEMINI_ROTATE_URL = "https://accounts.google.com/RotateCookies"
GEMINI_INIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Cookie file I/O ──

def read_cookies_from_file(cookie_path):
    """Read cookies.json and return {name: value} dict, or None if unreadable."""
    try:
        with open(cookie_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    for key in ("cookieMap", "cookies"):
        if key in data and isinstance(data[key], dict):
            return {k: v for k, v in data[key].items() if isinstance(v, str)}

    result = {}
    for k, v in data.items():
        if isinstance(v, str):
            result[k] = v
    return result if result else None


def write_cookies_to_file(cookie_path, cookies, source="manual"):
    """Write cookies dict back to cookies.json in vendor-compatible format."""
    from datetime import datetime
    payload = {
        "version": 1,
        "updatedAt": datetime.now().isoformat(),
        "cookieMap": cookies,
        "source": source,
    }
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cookie_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def build_cookie_header(cookies):
    """Build Cookie header string from cookie dict."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())

# ── Session validation ──

def validate_session_http(cookies, timeout=TIMEOUT_HTTP_VALIDATE):
    """Validate gemini-web cookies via HTTP GET to Gemini init endpoint.

    Returns (valid: bool, reason: str).
    """
    sid = cookies.get("__Secure-1PSID", "")
    if not sid:
        return False, "missing __Secure-1PSID cookie"

    headers = dict(GEMINI_INIT_HEADERS)
    headers["Cookie"] = build_cookie_header(cookies)

    req = urllib.request.Request(GEMINI_INIT_URL, headers=headers)
    try:
        with urlopen_with_proxy(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            if '"SNlM0e":"' in text or "'SNlM0e':" in text:
                return True, "session valid"
            return False, "SNlM0e token not found (status={})".format(resp.status)
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 403:
            return False, "HTTP {} — session expired".format(e.code)
        return False, "HTTP {}".format(e.code)
    except Exception as e:
        return False, "network error: {}".format(e)


# ── Cookie rotation ──

def rotate_cookie_http(cookies, timeout=TIMEOUT_HTTP_ROTATE):
    """Try to refresh __Secure-1PSIDTS via Google RotateCookies endpoint.

    Returns the new 1PSIDTS value if successful, None otherwise.
    """
    sid = cookies.get("__Secure-1PSID", "")
    if not sid:
        return None

    headers = {
        "Content-Type": "application/json",
        "Cookie": build_cookie_header(cookies),
    }
    body = b'[000,"-0000000000000000000"]'

    req = urllib.request.Request(GEMINI_ROTATE_URL, headers=headers, data=body, method="POST")
    try:
        with urlopen_with_proxy(req, timeout=timeout) as resp:
            set_cookie = resp.headers.get("Set-Cookie", "")
            match = re.search(r'__Secure-1PSIDTS=([^;]+)', set_cookie)
            if match:
                new_value = match.group(1).strip()
                if new_value:
                    return new_value
            return None
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None
