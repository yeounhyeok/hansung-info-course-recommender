#!/usr/bin/env python3
"""Extract grade + credit bucket summary from 종정시.

Reads:
  secrets/hansung_info_storage.json

Tip:
  Run login_refresh.py first if session expired.
"""

from __future__ import annotations

import pathlib
import re

import httpx
from bs4 import BeautifulSoup

from _session import get_with_auto_refresh

WORKSPACE = pathlib.Path("/home/ubuntu/.openclaw/workspace")
STATE = WORKSPACE / "secrets" / "hansung_info_storage.json"

GRADE_TOTAL = "https://info.hansung.ac.kr/jsp_21/student/grade/total_grade.jsp?viewMode=oc"


def extract(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())

    metrics = {}
    for key in ["신청학점", "취득학점", "평점총계", "평균평점", "백분위"]:
        mm = re.search(key + r"\s*(\d+(?:\.\d+)?)", text)
        if mm:
            metrics[key] = mm.group(1)

    buckets = {}
    for k in ["기초(필수)", "선필교", "자율"]:
        mm = re.search(re.escape(k) + r"\s*(\d+)", text)
        if mm:
            buckets[k] = mm.group(1)

    for k in ["전기", "전선", "전지(전필)"]:
        mm = re.search(re.escape(k) + r".*?(\d+)\(", text)
        if mm:
            buckets[k] = mm.group(1)

    return metrics, buckets


def main() -> None:
    if not STATE.exists():
        raise SystemExit("Missing secrets/hansung_info_storage.json")

    def _fetch(client: httpx.Client) -> str:
        return client.get(GRADE_TOTAL).text

    html = get_with_auto_refresh(_fetch)

    if "로그인 정보를 잃었습니다" in html:
        raise SystemExit("Session expired (auto-refresh failed). Ensure HANSUNG_INFO_ID/PASSWORD are set in ~/.openclaw/.env")

    metrics, buckets = extract(html)

    lines = ["# 🎓 종정시 성적 요약", ""]
    lines.append(f"- GPA(평균평점): {metrics.get('평균평점','?')}")
    lines.append(f"- 백분위: {metrics.get('백분위','?')}")
    lines.append(f"- 신청/취득학점: {metrics.get('신청학점','?')} / {metrics.get('취득학점','?')}")
    lines.append("")
    lines.append("## 이수구분(요약)")
    for k in ["기초(필수)", "선필교", "전기", "전지(전필)", "전선", "자율"]:
        if k in buckets:
            lines.append(f"- {k}: {buckets[k]}")

    print("\n".join(lines).strip() + "\n")


if __name__ == "__main__":
    main()
