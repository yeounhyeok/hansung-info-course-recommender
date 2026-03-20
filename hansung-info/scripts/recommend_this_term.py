#!/usr/bin/env python3
"""Recommend courses for the current term based on offerings + major buckets.

Inputs:
- term (e.g. 20261)
- major (e.g. Y030)
- target credits (default 18)

Strategy (v1 → v1.1):
- Prioritize 전필/전공필수-like courses.
- Avoid time conflicts by parsing day + period ranges from the classroom/time string.
- Fill remaining credits with 전기/전선 until reaching target.
- Print an explainable list and a human-readable timetable grid (ASCII).

Usage:
  python3 skills/hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18
  python3 skills/hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 21
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import httpx

WORKSPACE = pathlib.Path("/home/ubuntu/.openclaw/workspace")
STATE = WORKSPACE / "secrets" / "hansung_info_storage.json"
INDEX = "https://info.hansung.ac.kr/jsp_21/index.jsp"
BASE = "https://info.hansung.ac.kr/jsp_21/student/kyomu/"
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
    out: List[Dict[str, str]] = []
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
            }
        )
    return out


DAY_MAP = {
    "월": "Mon",
    "화": "Tue",
    "수": "Wed",
    "목": "Thu",
    "금": "Fri",
    "토": "Sat",
    "일": "Sun",
}


@dataclass(frozen=True)
class Slot:
    day: str
    start: int
    end: int
    suffix: str = ""  # e.g. "M"; we keep it but don't rely on it.


def _iter_korean_day_spans(text: str) -> Iterable[Tuple[str, str]]:
    """Yield (day_kr, span_text) pairs from a classroom string.

    Examples encountered:
      "상상관306 금6~8M"
      "상상관306 금 6~8"
      "상상관306/상상관306 금6~8M"

    We intentionally ignore building/room tokens.
    """

    if not text:
        return
    # Often separated by '/'
    for part in text.split("/"):
        part = part.strip()
        # Find patterns like "금6~8M" or "금 6~8".
        m = re.search(r"([월화수목금토일])\s*(\d+)\s*~\s*(\d+)\s*([A-Z]?)", part)
        if not m:
            continue
        day_kr = m.group(1)
        span = f"{m.group(2)}~{m.group(3)}{m.group(4) or ''}".strip()
        yield day_kr, span


def parse_slots(classroom: str) -> List[Slot]:
    """Parse day+period ranges from classroom field.

    Returns coarse but overlap-checkable slots.
    """

    slots: List[Slot] = []
    for day_kr, span in _iter_korean_day_spans(classroom):
        day = DAY_MAP.get(day_kr, day_kr)
        m = re.match(r"(\d+)~(\d+)([A-Z]?)", span)
        if not m:
            continue
        start = int(m.group(1))
        end = int(m.group(2))
        suffix = m.group(3) or ""
        if start > 0 and end > 0 and end >= start:
            slots.append(Slot(day=day, start=start, end=end, suffix=suffix))
    return slots


@dataclass
class Course:
    code: str
    name: str
    isu: str
    credit: int
    prof: str
    classroom: str

    @property
    def slots(self) -> List[Slot]:
        return parse_slots(self.classroom)


def _overlap(a: Slot, b: Slot) -> bool:
    if a.day != b.day:
        return False
    return not (a.end < b.start or b.end < a.start)


def conflict(a: Course, b: Course) -> bool:
    sa = a.slots
    sb = b.slots
    if not sa or not sb:
        # If either has no parsable time, be conservative: treat as conflict-unknown.
        # v1.1 behavior: allow it, but it won't be placed on the grid.
        return False
    for xa in sa:
        for xb in sb:
            if _overlap(xa, xb):
                return True
    return False


def score(c: Course) -> int:
    s = 0
    if c.isu in {"전필", "전공지정", "전공필수", "전지"}:
        s += 100
    elif c.isu == "전기":
        s += 70
    elif c.isu == "전선":
        s += 50
    if "캡스톤" in c.name:
        s += 10
    if "기업연계" in c.name or "산학" in c.name:
        s += 8
    return s


def _short_name(name: str, max_len: int = 6) -> str:
    # Keep Korean readable; just hard-truncate.
    n = re.sub(r"\s+", "", name)
    return n[:max_len]


def render_ascii_timetable(courses: List[Course], days: Optional[List[str]] = None, max_period: int = 12) -> str:
    """Render a simple ASCII grid timetable.

    - Rows: period 1..max_period
    - Columns: Mon..Fri (default)
    - Cells: course short name or "·"

    Note: If a course has multiple slots, we paint all.
    """

    if days is None:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    grid: Dict[Tuple[int, str], str] = {}
    for c in courses:
        label = _short_name(c.name)
        for sl in c.slots:
            if sl.day not in days:
                continue
            for p in range(sl.start, sl.end + 1):
                if p > max_period:
                    continue
                key = (p, sl.day)
                # If collision happens despite our checks, mark it.
                if key in grid and grid[key] != label:
                    grid[key] = "!!"
                else:
                    grid[key] = label

    col_w = 8
    header = " " * 4 + "".join(d.center(col_w) for d in days)
    lines = [header]
    for p in range(1, max_period + 1):
        row = f"{p:>2}  "
        for d in days:
            row += (grid.get((p, d), "·")).center(col_w)
        lines.append(row)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", required=True)
    ap.add_argument("--major", default="Y030")
    ap.add_argument("--target", type=int, default=18, help="Target credits (default: 18)")
    ap.add_argument("--no-grid", action="store_true", help="Do not print ASCII timetable grid")
    ap.add_argument("--max-period", type=int, default=12, help="Max period rows for the grid (default: 12)")
    args = ap.parse_args()

    jar = cookies_from_state()
    with httpx.Client(
        timeout=25,
        follow_redirects=True,
        cookies=jar,
        headers={"User-Agent": "Mozilla/5.0", "Referer": INDEX},
    ) as c:
        c.get(INDEX)
        xml = c.post(HISTORY, data={"gubun": "history", "syearhakgi": args.term, "sjungong": args.major}).text

    if "로그인 정보를 잃었습니다" in xml:
        raise SystemExit("Session expired. Run login_refresh.py")

    raw = parse_rows(xml)
    courses: List[Course] = []
    for r in raw:
        if not r.get("code"):
            continue
        try:
            credit = int(r.get("credit") or 0)
        except ValueError:
            credit = 0
        courses.append(
            Course(
                code=r.get("code") or "",
                name=r.get("name") or "",
                isu=r.get("isu") or "",
                credit=credit,
                prof=r.get("prof") or "",
                classroom=r.get("classroom") or "",
            )
        )

    # Dedup by code (keep first)
    dedup: "OrderedDict[str, Course]" = OrderedDict()
    for c in courses:
        dedup.setdefault(c.code, c)
    courses = list(dedup.values())

    ranked = sorted(courses, key=lambda x: score(x), reverse=True)

    picked: List[Course] = []
    total = 0

    for cand in ranked:
        if total >= args.target:
            break
        if cand.credit <= 0:
            continue
        if cand.isu not in {"전필", "전지", "전공필수", "전공지정", "전기", "전선"}:
            continue
        if any(conflict(cand, p) for p in picked):
            continue
        picked.append(cand)
        total += cand.credit

    # Output
    lines: List[str] = [f"# 📚 이번 학기 추천 ({args.term}, {args.major})", ""]
    lines.append(f"- 목표 학점: {args.target} (현재 추천 합: {total})")
    lines.append("- 시간표 충돌 방지: 요일+교시 범위 파싱 후 겹치면 제외")
    lines.append("")

    for c in picked:
        extra = ""
        if c.classroom:
            extra = f" | {c.classroom}"
        if c.prof:
            extra += f" | {c.prof}"
        lines.append(f"- {c.isu} {c.name} ({c.credit}학점){extra}")

    req = [c for c in ranked if c.isu == "전필"]
    lines.append("")
    lines.append(f"- 이번 학기 전필 개설 수: {len(req)}")

    if not args.no_grid:
        lines.append("")
        lines.append("## 🗓️ 최종 시간표(ASCII)")
        lines.append("```")
        lines.append(render_ascii_timetable(picked, max_period=args.max_period))
        lines.append("```")
        lines.append("")
        lines.append("- 표기 규칙: 셀=과목명(축약), ·=비어있음, !!=충돌(비정상)")

    print("\n".join(lines).strip() + "\n")


if __name__ == "__main__":
    main()
