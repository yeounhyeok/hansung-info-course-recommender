#!/usr/bin/env python3
"""Fetch current-term course offerings (시간표 및 수업계획서조회) for a given major.

This uses the AUIGrid XML endpoints shown in the siganpyo_aui.jsp page.

Endpoints (relative to /jsp_21/student/kyomu/):
- siganpyo_aui_data.jsp?gubun=yearhakgilist
- siganpyo_aui_data.jsp?gubun=jungonglist  (POST syearhakgi)
- siganpyo_aui_data.jsp  (POST gubun=history, syearhakgi, sjungong)

Usage:
  python3 skills/hansung-info/scripts/timetable_offerings.py --term 20261 --major Y030
  python3 skills/hansung-info/scripts/timetable_offerings.py --term 20261 --major Y030 --only-required

Note: '전공지정(전공필수) 21학점' is a graduation aggregation. Here we fetch actual offerings.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import OrderedDict
from typing import Dict, List

import httpx

WORKSPACE = pathlib.Path("/home/ubuntu/.openclaw/workspace")
STATE = WORKSPACE / "secrets" / "hansung_info_storage.json"

INDEX = "https://info.hansung.ac.kr/jsp_21/index.jsp"
BASE = "https://info.hansung.ac.kr/jsp_21/student/kyomu/"

YEAR_LIST = BASE + "siganpyo_aui_data.jsp?gubun=yearhakgilist"
MAJOR_LIST = BASE + "siganpyo_aui_data.jsp?gubun=jungonglist"
HISTORY = BASE + "siganpyo_aui_data.jsp"


def cookies_from_state() -> httpx.Cookies:
    data = json.loads(STATE.read_text(encoding="utf-8"))
    jar = httpx.Cookies()
    for c in data.get("cookies", []):
        jar.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path") or "/")
    return jar


def get_tag(tag: str, chunk: str) -> str:
    m = re.search(fr"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", chunk)
    return (m.group(1) or "").strip() if m else ""


def parse_rows(xml: str) -> List[Dict[str, str]]:
    rows = re.findall(r"<row>(.*?)</row>", xml, re.S)
    out = []
    for ch in rows:
        out.append(
            {
                "code": get_tag("kwamokcode", ch),
                "name": get_tag("kwamokname", ch),
                "isu": get_tag("isugubun", ch),
                "credit": get_tag("hakjum", ch),
                "grade": get_tag("haknean", ch),
                "prof": get_tag("prof", ch),
                "classroom": get_tag("classroom", ch),
                "juya": get_tag("juya", ch),
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", required=True, help="term like 20261")
    ap.add_argument("--major", default="Y030", help="major code (default: Y030)")
    ap.add_argument("--only-required", action="store_true", help="only 전필/전공필수-like buckets")
    args = ap.parse_args()

    jar = cookies_from_state()
    with httpx.Client(timeout=25, follow_redirects=True, cookies=jar, headers={"User-Agent": "Mozilla/5.0", "Referer": INDEX}) as c:
        c.get(INDEX)
        xml = c.post(HISTORY, data={"gubun": "history", "syearhakgi": args.term, "sjungong": args.major}).text

    if "로그인 정보를 잃었습니다" in xml:
        raise SystemExit("Session expired. Run login_refresh.py")

    rows = parse_rows(xml)

    dedup: "OrderedDict[str, Dict[str, str]]" = OrderedDict()
    for r in rows:
        if not r.get("code"):
            continue
        if args.only_required and r.get("isu") not in {"전필", "전지", "전공필수", "전공지정"}:
            continue
        # keep first occurrence
        dedup.setdefault(r["code"], r)

    out = list(dedup.values())
    print(f"count={len(out)} term={args.term} major={args.major}")
    for r in out:
        where = (r.get("classroom") or "").strip()
        prof = (r.get("prof") or "").strip()
        extra = ""
        if where:
            extra += f" | {where}"
        if prof:
            extra += f" | {prof}"
        print(f"- {r.get('isu')} {r.get('code')} {r.get('name')} ({r.get('credit')}학점){extra}")


if __name__ == "__main__":
    main()
