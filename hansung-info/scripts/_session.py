#!/usr/bin/env python3
"""Hansung info session helpers.

Centralizes:
- cookie jar loading
- expired-session detection
- one-shot auto refresh (login_refresh) if credentials exist in ~/.openclaw/.env

This keeps the user workflow simple: "if cookie expired, just refresh automatically".
"""

from __future__ import annotations

import json
import pathlib
from typing import Callable, Tuple

import httpx

from _dotenv import load_dotenv

WORKSPACE = pathlib.Path("/home/ubuntu/.openclaw/workspace")
STATE = WORKSPACE / "secrets" / "hansung_info_storage.json"
INDEX = "https://info.hansung.ac.kr/jsp_21/index.jsp"


def cookies_from_state() -> httpx.Cookies:
    data = json.loads(STATE.read_text(encoding="utf-8"))
    jar = httpx.Cookies()
    for c in data.get("cookies", []):
        jar.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path") or "/")
    return jar


def is_expired(html: str) -> bool:
    return ("로그인 정보를 잃었습니다" in html) or ("로그인" in html and "info.hansung.ac.kr" in html and "lost" in html)


def auto_refresh_if_possible() -> bool:
    """Try to refresh cookies once. Returns True if attempted+success, False otherwise."""
    load_dotenv()
    try:
        # Local import to avoid import cycles for scripts that import _session.
        from login_refresh import main as refresh_main  # type: ignore

        refresh_main()
        return True
    except SystemExit:
        # Missing env var etc.
        return False
    except Exception:
        return False


def with_client() -> httpx.Client:
    if not STATE.exists():
        raise SystemExit("Missing secrets/hansung_info_storage.json (run login_refresh first)")
    jar = cookies_from_state()
    return httpx.Client(
        timeout=25,
        follow_redirects=True,
        cookies=jar,
        headers={"User-Agent": "Mozilla/5.0", "Referer": INDEX},
    )


def get_with_auto_refresh(fetch_fn: Callable[[httpx.Client], str]) -> str:
    """Run fetch_fn(client)->html. If expired and creds exist, refresh once then retry."""
    with with_client() as client:
        client.get(INDEX)
        html = fetch_fn(client)

    if not is_expired(html):
        return html

    if auto_refresh_if_possible():
        with with_client() as client2:
            client2.get(INDEX)
            html2 = fetch_fn(client2)
        return html2

    # still expired or couldn't refresh
    return html
