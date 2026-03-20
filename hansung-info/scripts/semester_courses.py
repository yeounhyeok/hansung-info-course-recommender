#!/usr/bin/env python3
"""List enrolled courses by semester from Hansung Info (종정시) cumulative grade page.

- Uses stored cookies: workspace/secrets/hansung_info_storage.json
- Fetches: https://info.hansung.ac.kr/jsp_21/student/grade/total_grade.jsp?viewMode=oc
- Parses per-semester cards ("YYYY 학년도 N 학기") and extracts course rows.

This is useful for:
- Checking what you actually took in a past term (e.g., 20252)
- Building future timetables based on your historical preferences

Note: Some terms may be missing on the page depending on academic status (leave, etc.).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

WORKSPACE = pathlib.Path("/home/ubuntu/.openclaw/workspace")
STATE = WORKSPACE / "secrets" / "hansung_info_storage.json"

INDEX = "https://info.hansung.ac.kr/jsp_21/index.jsp"
TOTAL_GRADE = "https://info.hansung.ac.kr/jsp_21/student/grade/total_grade.jsp?viewMode=oc"
MARK_LOST = "로그인 정보를 잃었습니다"

SEM_RE = re.compile(r"(?P<year>20\d{2})\s*학년도\s*(?P<term>[12])\s*학기")


def cookies_from_state() -> httpx.Cookies:
    data = json.loads(STATE.read_text(encoding="utf-8"))
    jar = httpx.Cookies()
    for c in data.get("cookies", []):
        jar.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path") or "/")
    return jar


def fetch_total_grade_html() -> str:
    if not STATE.exists():
        raise SystemExit("Missing secrets/hansung_info_storage.json (run openclaw/login_refresh.sh)")

    jar = cookies_from_state()
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        cookies=jar,
        headers={"User-Agent": "Mozilla/5.0", "Referer": INDEX},
    ) as client:
        client.get(INDEX)
        r = client.get(TOTAL_GRADE)
        r.raise_for_status()
        if MARK_LOST in r.text:
            raise SystemExit("Session expired: please re-login (bash openclaw/login_refresh.sh)")
        return r.text


def parse_term_cards(html: str) -> Dict[str, List[Dict[str, Any]]]:
    soup = BeautifulSoup(html, "html.parser")

    out: Dict[str, List[Dict[str, Any]]] = {}

    # The page contains cards with headings like "2023 학년도 2 학기".
    for span in soup.find_all("span"):
        title = span.get_text(" ", strip=True)
        mm = SEM_RE.search(title)
        if not mm:
            continue

        year = int(mm.group("year"))
        term = int(mm.group("term"))
        term_key = f"{year}{term}"

        card = span.find_parent("div", class_=re.compile(r"\bdivSbox\b"))
        if not card:
            continue

        # Find the per-semester course table.
        table = None
        for t in card.find_all("table"):
            th = [x.get_text(" ", strip=True) for x in t.find_all("th")]
            if not th:
                continue
            if "교과명" in "".join(th) and "교과코드" in "".join(th):
                table = t
                break

        if not table:
            out[term_key] = []
            continue

        rows: List[Dict[str, Any]] = []
        for tr in table.find_all("tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if not tds:
                continue
            if len(tds) < 5:
                continue
            # columns: 구분, 교과명, 교과코드, 학점, 성적, (현재트랙...)
            rows.append(
                {
                    "isu": tds[0],
                    "name": tds[1],
                    "code": tds[2],
                    "credits": tds[3],
                    "grade": tds[4],
                    "track": tds[5] if len(tds) > 5 else "",
                }
            )

        out[term_key] = rows

    return out


def print_md(term_key: str, courses: List[Dict[str, Any]]) -> None:
    year = term_key[:4]
    term = term_key[4:]
    print(f"# 📘 수강과목 리스트 ({year}학년도 {term}학기 / {term_key})\n")
    if not courses:
        print("- 해당 학기 데이터가 페이지에서 발견되지 않았습니다. (휴학/군휴학/표시 제한일 수 있음)\n")
        return

    total = 0
    for c in courses:
        try:
            total += int(str(c.get("credits", "0")).strip())
        except Exception:
            pass

    print(f"- 과목 수: {len(courses)}")
    print(f"- 학점 합계(표기 기준): {total}\n")
    for c in courses:
        isu = c.get("isu", "")
        name = c.get("name", "")
        code = c.get("code", "")
        credits = c.get("credits", "")
        grade = c.get("grade", "")
        print(f"- {isu} {name} ({code}) | {credits}학점 | {grade}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--term", required=True, help="Semester key like 20261, 20252")
    args = p.parse_args()

    term_key = str(args.term).strip()
    if not re.fullmatch(r"20\d{2}[12]", term_key):
        raise SystemExit("--term must be like 20261 or 20252")

    html = fetch_total_grade_html()
    cards = parse_term_cards(html)
    courses = cards.get(term_key, [])
    print_md(term_key, courses)


if __name__ == "__main__":
    main()
