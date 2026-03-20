#!/usr/bin/env python3
"""Generate a lightweight graduation roadmap (AI응용학과) from now until target grad.

Shareable, explainable planner based on:
- 종정시 curriculum catalog (교육과정조회, 전필 후보)
- (optional) current-term offerings (시간표조회)

Key correction (reflecting reality):
- 종정시/학과 쪽에 '전필 체크리스트' 형태의 확정 API가 없는 경우가 많아서,
  로드맵은 '전공필수 과목 리스트를 1:1로 채운다'가 아니라
  **전공필수 학점(예: 21학점) 이상을 안전하게 채우는 시퀀싱 가이드**로 동작합니다.

Limitations:
- Future offerings unknown; roadmap is sequencing guidance.
- Exact substitution rules can vary by 학번/학과 공지.

Usage:
  python3 skills/hansung-info/scripts/roadmap_generator.py --start 20261 --grad 20282 --major Y030
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

CURR_BASE = "https://info.hansung.ac.kr/jsp_21/student/kyomu/"
YEAR_LIST = CURR_BASE + "kyoyukgwajung_data_aui.jsp?gubun=yearhakgilist"
HISTORY = CURR_BASE + "kyoyukgwajung_data_aui.jsp"

DEPT_REQ_URL = "https://www.hansung.ac.kr/CreCon/2781/subview.do"


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


def fetch_required_catalog(client: httpx.Client, major: str) -> List[Dict[str, str]]:
    """Fetch 전필 candidates from curriculum catalog across recent terms."""

    terms = fetch_terms(client)[:10]
    seen: Dict[str, Dict[str, str]] = {}
    for t in terms:
        xml = client.post(HISTORY, params={"gubun": "history"}, data={"syearhakgi": t, "sjungong": major}).text
        for row in parse_rows(xml):
            if not row.get("code"):
                continue
            if row.get("isu") != "전필":
                continue
            seen[row["code"]] = row
    return list(seen.values())


def term_range(start: str, end: str) -> List[str]:
    sy, ss = int(start[:4]), int(start[4])
    ey, es = int(end[:4]), int(end[4])
    out = []
    y, s = sy, ss
    while True:
        out.append(f"{y}{s}")
        if y == ey and s == es:
            break
        if s == 1:
            s = 2
        else:
            y += 1
            s = 1
    return out


def pick_core(req: List[Dict[str, str]], required_credits: int) -> List[Dict[str, str]]:
    """Pick a 'safe core' set that meets required_credits.

    We don't assume a strict checklist exists; we just build a conservative core
    with sensible prerequisite flow.
    """

    def by_kw(kw: str) -> List[Dict[str, str]]:
        return [r for r in req if kw in (r.get("name") or "")]

    selected: List[Dict[str, str]] = []
    for kw in ["인공지능 수학", "자료구조", "머신러닝", "딥러닝", "프리캡스톤"]:
        hits = by_kw(kw)
        if hits:
            selected.append(hits[0])

    cap = by_kw("인공지능 캡스톤")
    if cap:
        selected.append(cap[0])

    emb = by_kw("임베디드")
    if emb:
        selected.append(emb[0])
    else:
        corp = by_kw("기업연계")
        if corp:
            selected.append(corp[0])

    # Dedup by code
    seen = set()
    dedup: List[Dict[str, str]] = []
    for r in selected:
        code = r.get("code")
        if not code or code in seen:
            continue
        seen.add(code)
        dedup.append(r)

    # Fill with remaining candidates until credits reach required_credits
    def credit_of(x: Dict[str, str]) -> int:
        try:
            return int(x.get("credit") or 0)
        except ValueError:
            return 0

    total = sum(credit_of(x) for x in dedup)
    if total < required_credits:
        for r in req:
            code = r.get("code")
            if not code or code in seen:
                continue
            dedup.append(r)
            seen.add(code)
            total += credit_of(r)
            if total >= required_credits:
                break

    return dedup


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20261")
    ap.add_argument("--grad", default="20282")
    ap.add_argument("--major", default="Y030")
    ap.add_argument("--required-credits", type=int, default=21, help="전공필수 목표 학점 (default: 21)")
    args = ap.parse_args()

    jar = cookies_from_state()
    with httpx.Client(timeout=25, follow_redirects=True, cookies=jar, headers={"User-Agent": "Mozilla/5.0", "Referer": INDEX}) as c:
        c.get(INDEX)
        req = fetch_required_catalog(c, args.major)

    core = pick_core(req, args.required_credits)
    terms = term_range(args.start, args.grad)

    plan: Dict[str, List[Dict[str, str]]] = {t: [] for t in terms}

    def pop_kw(kw: str) -> List[Dict[str, str]]:
        out = [r for r in core if kw in (r.get("name") or "")]
        for r in out:
            core.remove(r)
        return out

    # Sequencing: foundation → ML/DL → (optional) embedded → pre-capstone → capstone
    if terms:
        plan[terms[0]] += pop_kw("인공지능 수학") + pop_kw("자료구조")
    if len(terms) > 1:
        plan[terms[1]] += pop_kw("머신러닝") + pop_kw("딥러닝")
    if len(terms) > 2:
        plan[terms[2]] += pop_kw("임베디드")
    if len(terms) > 3:
        plan[terms[-2]] += pop_kw("프리캡스톤")
        plan[terms[-1]] += pop_kw("캡스톤") + pop_kw("기업연계")

    # Distribute leftovers
    i = 0
    leftovers = list(core)
    for r in leftovers:
        plan[terms[i % len(terms)]].append(r)
        i += 1

    lines = [f"# 🗺️ 졸업 로드맵 초안 (major={args.major})", ""]
    lines.append("- 기본 정책: 학기당 18학점, 직전학기 GPA 4.0+면 21학점까지")
    lines.append(f"- 기간: {args.start} → {args.grad} (총 {len(terms)}학기)")
    lines.append(f"- 전공필수: '체크리스트'가 아니라 '학점 기준'으로 {args.required_credits}학점 이상을 안전하게 채우는 플랜")
    lines.append("")

    for t in terms:
        if not plan[t]:
            continue
        lines.append(f"## {t}")
        for r in plan[t]:
            lines.append(f"- 전필 {r.get('name')} ({r.get('credit')}학점)")
        lines.append("")

    lines.append("## 학과 추가 졸업요건(원문 확인)")
    lines.append(f"- 원문: <{DEPT_REQ_URL}>")
    lines.append("- 캡스톤/산학 조건은 학번/졸업예정에 따라 적용 범위가 달라서, 공지 기준으로 최종 확인 필요")

    print("\n".join(lines).strip() + "\n")


if __name__ == "__main__":
    main()
