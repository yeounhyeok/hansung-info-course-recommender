#!/usr/bin/env python3
"""Fetch major curriculum (교육과정조회) rows and optionally filter required(전필).

Uses endpoints documented in references/endpoints.md.

Examples:
  python3 skills/hansung-info/scripts/major_curriculum.py --term 20261 --major Y030
  python3 skills/hansung-info/scripts/major_curriculum.py --scan-terms --major Y030 --only-required
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
YEAR_LIST = "https://info.hansung.ac.kr/jsp_21/student/kyomu/kyoyukgwajung_data_aui.jsp?gubun=yearhakgilist"
MAJOR_LIST = "https://info.hansung.ac.kr/jsp_21/student/kyomu/kyoyukgwajung_data_aui.jsp?gubun=jungonglist"
HISTORY = "https://info.hansung.ac.kr/jsp_21/student/kyomu/kyoyukgwajung_data_aui.jsp"


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
            }
        )
    return out


def fetch_terms(client: httpx.Client) -> List[str]:
    xml = client.post(YEAR_LIST).text
    return re.findall(r"<tcd><!\[CDATA\[(.*?)\]\]></tcd>", xml)


def fetch_history(client: httpx.Client, term: str, major: str) -> List[Dict[str, str]]:
    xml = client.post(HISTORY, params={"gubun": "history"}, data={"syearhakgi": term, "sjungong": major}).text
    return parse_rows(xml)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", help="term like 20261")
    ap.add_argument("--major", default="Y030", help="major code (default: Y030)")
    ap.add_argument("--scan-terms", action="store_true", help="scan multiple terms and dedupe")
    ap.add_argument("--only-required", action="store_true", help="only 전필/전공필수-like buckets")
    args = ap.parse_args()

    jar = cookies_from_state()
    with httpx.Client(timeout=25, follow_redirects=True, cookies=jar, headers={"User-Agent": "Mozilla/5.0", "Referer": INDEX}) as c:
        c.get(INDEX)
        terms = [args.term] if args.term and not args.scan_terms else fetch_terms(c)[:10]

        dedup: "OrderedDict[str, Dict[str, str]]" = OrderedDict()
        for t in terms:
            for row in fetch_history(c, t, args.major):
                if not row["code"]:
                    continue
                if args.only_required and row["isu"] not in {"전필", "전지", "전공필수", "전공지정"}:
                    continue
                dedup[row["code"]] = row | {"term": t}

    rows = list(dedup.values())
    print(f"count={len(rows)}")
    for r in rows:
        print(f"- {r['isu']} {r['code']} {r['name']} ({r.get('credit','?')}학점, {r.get('grade','?')}학년) [term {r.get('term')}]")


if __name__ == "__main__":
    main()
