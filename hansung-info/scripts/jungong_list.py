#!/usr/bin/env python3
"""Fetch Hansung Info '전공/트랙' dropdown options (sjungong list).

This corresponds to the dropdown used by the timetable/offering pages.

Endpoint:
- https://info.hansung.ac.kr/jsp_21/student/kyomu/siganpyo_aui_data.jsp?gubun=jungonglist
  POST: syearhakgi=<term>

Outputs:
- table (default)
- json (with --format json)

Usage:
  python3 hansung-info/scripts/jungong_list.py --term 20261
  python3 hansung-info/scripts/jungong_list.py --term 20261 --format json --out .tmp/jungonglist_20261.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Dict, List

import httpx

WORKSPACE = pathlib.Path("/home/ubuntu/.openclaw/workspace")
STATE = WORKSPACE / "secrets" / "hansung_info_storage.json"
INDEX = "https://info.hansung.ac.kr/jsp_21/index.jsp"
JUNGONGLIST = "https://info.hansung.ac.kr/jsp_21/student/kyomu/siganpyo_aui_data.jsp?gubun=jungonglist"


def cookies_from_state() -> httpx.Cookies:
    data = json.loads(STATE.read_text(encoding="utf-8"))
    jar = httpx.Cookies()
    for c in data.get("cookies", []):
        jar.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path") or "/")
    return jar


def _get(tag: str, chunk: str) -> str:
    m = re.search(fr"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", chunk)
    return (m.group(1) if m else "").strip()


def fetch_jungong_list(client: httpx.Client, *, term: str) -> List[Dict[str, str]]:
    xml = client.post(JUNGONGLIST, data={"syearhakgi": term}).text
    if "로그인 정보를 잃었습니다" in xml:
        raise SystemExit("Session expired. Run login_refresh.py")

    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    out: List[Dict[str, str]] = []
    for it in items:
        code = _get("tcd", it)
        name = _get("tnm", it)
        if code and name:
            out.append({"code": code, "name": name})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", required=True, help="Term code, e.g. 20261")
    ap.add_argument("--format", choices=["table", "json"], default="table")
    ap.add_argument("--out", help="Write output to a file")
    args = ap.parse_args()

    jar = cookies_from_state()
    client = httpx.Client(
        timeout=25,
        follow_redirects=True,
        cookies=jar,
        headers={"User-Agent": "Mozilla/5.0", "Referer": INDEX},
    )
    client.get(INDEX)

    items = fetch_jungong_list(client, term=str(args.term))

    if args.format == "json":
        text = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    else:
        text = "\n".join([f"{x['code']}\t{x['name']}" for x in items]) + "\n"

    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")

    client.close()


if __name__ == "__main__":
    main()
