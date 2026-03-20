#!/usr/bin/env python3
"""Fetch AI응용학과 dept graduation requirements (public Hansung site) and summarize.

Source page:
  https://www.hansung.ac.kr/CreCon/2781/subview.do
"""

from __future__ import annotations

import re

import httpx

URL = "https://www.hansung.ac.kr/CreCon/2781/subview.do"


def main() -> None:
    html = httpx.get(URL, follow_redirects=True, timeout=25, headers={"User-Agent": "Mozilla/5.0"}).text
    # crude extraction: keep key bullet lines
    text = re.sub(r"<[^>]+>", " ", html)
    text = " ".join(text.split())

    # Pull a compact block around "필수요건"
    idx = text.find("필수요건")
    block = text[idx : idx + 900] if idx != -1 else text[:900]

    lines = ["# 🧾 AI응용학과 졸업요건(학과)", f"- 원문: <{URL}>", "", block]
    print("\n".join(lines).strip() + "\n")


if __name__ == "__main__":
    main()
