#!/usr/bin/env python3
"""Discover network endpoints for major/graduation requirement details using Playwright.

Goal: find the API behind '전공지정(전공필수) 21학점' detailed course checklist.

It loads the graduation requirement page and records XHR/fetch requests.

Prereqs:
- Run login_refresh.py first (cookies in secrets/hansung_info_storage.json)
- Playwright chromium installed on server

Usage:
  python3 skills/hansung-info/scripts/discover_major_requirements.py
"""

from __future__ import annotations

import json
import pathlib
import re

from playwright.sync_api import sync_playwright

WORKSPACE = pathlib.Path("/home/ubuntu/.openclaw/workspace")
STATE = WORKSPACE / "secrets" / "hansung_info_storage.json"

INDEX = "https://info.hansung.ac.kr/jsp_21/index.jsp"
GRAD = "https://info.hansung.ac.kr/jsp_21/student/graduation/graduation_requirement.jsp?viewMode=oc"


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))

    urls: set[str] = set()

    def consider(url: str) -> None:
        if not url:
            return
        # keep only likely endpoints
        if any(k in url.lower() for k in ["gradu", "jol", "require", "isu", "track", "kyoyuk", "curr", "aui", "data", "servlet"]):
            urls.add(url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=state)
        page = ctx.new_page()

        def on_request(req):
            if req.resource_type in {"xhr", "fetch"}:
                consider(req.url)

        page.on("request", on_request)

        page.goto(INDEX, timeout=60000)
        page.goto(GRAD, timeout=60000)

        # Try clicking anything that looks like '전공지정' / '전공필수' / '상세' to trigger API calls
        for label in ["전공지정", "전공필수", "상세", "Click", "조회"]:
            try:
                loc = page.get_by_text(label, exact=False).first
                if loc:
                    loc.click(timeout=1500)
            except Exception:
                pass

        # Wait a moment for requests
        page.wait_for_timeout(1500)

        browser.close()

    # Print discovered endpoints
    for u in sorted(urls):
        print(u)


if __name__ == "__main__":
    main()
