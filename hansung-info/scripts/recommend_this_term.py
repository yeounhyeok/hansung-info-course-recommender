#!/usr/bin/env python3
"""Recommend courses for the current term based on Hansung Info offerings.

This script is designed to be used as an OpenClaw skill, but it can be run standalone.

Inputs:
- term (e.g. 20261)
- major (e.g. Y030)
- target credits (default 18)
- year filter (e.g. 2학년 과목 위주)

Strategy (explainable heuristic):
- Prioritize buckets: 전필/전공필수 > 전기 > 전선.
- Avoid time conflicts by parsing day + period ranges from the classroom string.
- Prefer fewer on-campus days by penalizing schedules that introduce new days.
- Output a Markdown timetable (time-based labels) and a pick list.

Limitations:
- 교양 과목은 현재 이 스킬이 조회하는 전공 시간표 API 범위 밖이라 자동 추천이 어렵습니다.
  (추후 '전체 개설 과목' 데이터 소스가 확보되면 자동 추천으로 확장 가능)

Usage:
  python3 hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18 --year 2
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


DAY_KO_TO_EN = {"월": "Mon", "화": "Tue", "수": "Wed", "목": "Thu", "금": "Fri", "토": "Sat", "일": "Sun"}
DAY_EN_TO_KO = {v: k for k, v in DAY_KO_TO_EN.items()}


@dataclass(frozen=True)
class Slot:
    day_en: str
    start_period: int
    end_period: int
    suffix: str = ""  # e.g. "M". Kept for display.

    @property
    def day_ko(self) -> str:
        return DAY_EN_TO_KO.get(self.day_en, self.day_en)


def _iter_korean_day_spans(text: str) -> Iterable[Tuple[str, int, int, str]]:
    """Yield (day_kr, start, end, suffix) from a classroom string.

    Handles patterns like:
    - "금6~8M"
    - "월2M~3M"
    - "수5M~6M"
    """

    if not text:
        return
    for part in text.split("/"):
        part = part.strip()
        m = re.search(r"([월화수목금토일])\s*(\d+)\s*([A-Z]?)\s*~\s*(\d+)\s*([A-Z]?)", part)
        if not m:
            continue
        day_kr = m.group(1)
        start = int(m.group(2))
        end = int(m.group(4))
        suffix = (m.group(5) or m.group(3) or "").strip()
        yield day_kr, start, end, suffix


def parse_slots(classroom: str) -> List[Slot]:
    slots: List[Slot] = []
    for day_kr, start, end, suffix in _iter_korean_day_spans(classroom):
        day_en = DAY_KO_TO_EN.get(day_kr, day_kr)
        if start > 0 and end > 0 and end >= start:
            slots.append(Slot(day_en=day_en, start_period=start, end_period=end, suffix=suffix))
    return slots


@dataclass
class Course:
    code: str
    name: str
    isu: str
    credit: int
    grade: str
    prof: str
    classroom: str

    @property
    def slots(self) -> List[Slot]:
        return parse_slots(self.classroom)


def _overlap(a: Slot, b: Slot) -> bool:
    if a.day_en != b.day_en:
        return False
    return not (a.end_period < b.start_period or b.end_period < a.start_period)


def conflict(a: Course, b: Course) -> bool:
    sa = a.slots
    sb = b.slots
    if not sa or not sb:
        # If either has no parsable time (e.g. online-only), allow.
        return False
    for xa in sa:
        for xb in sb:
            if _overlap(xa, xb):
                return True
    return False


def bucket_score(c: Course) -> int:
    if c.isu in {"전필", "전공지정", "전공필수", "전지"}:
        return 100
    if c.isu == "전기":
        return 70
    if c.isu == "전선":
        return 50
    return 0


def keyword_bonus(name: str) -> int:
    s = 0
    if "캡스톤" in name:
        s += 10
    if "기업연계" in name or "산학" in name:
        s += 8
    return s


def total_score(c: Course) -> int:
    return bucket_score(c) + keyword_bonus(c.name)


def parse_int_safe(x: str) -> Optional[int]:
    x = (x or "").strip()
    if not x:
        return None
    m = re.search(r"\d+", x)
    if not m:
        return None
    try:
        return int(m.group(0))
    except ValueError:
        return None


def course_days(c: Course) -> List[str]:
    # Return unique day_en values.
    days = []
    for s in c.slots:
        if s.day_en not in days:
            days.append(s.day_en)
    return days


def period_to_time_label(period: int) -> str:
    """Convert period number to a time label.

    NOTE: Hansung official period-to-time mapping can vary.
    We use a simple, readable default: 1교시=09:00, period=+1h.
    """

    hour = 9 + (period - 1)
    return f"{hour:02d}:00"


def slot_to_timerange(s: Slot) -> str:
    start = period_to_time_label(s.start_period)
    end = period_to_time_label(s.end_period + 1)
    return f"{start}~{end}"


def render_markdown_timetable(picked: List[Course]) -> str:
    """Render a Markdown table (time-based rows, Mon..Fri columns).

    We build time rows from the periods seen in picked courses.
    """

    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    # Determine min/max period from picked slots.
    periods: List[int] = []
    for c in picked:
        for s in c.slots:
            for p in range(s.start_period, s.end_period + 1):
                periods.append(p)
    if not periods:
        return "(표시할 오프라인 시간표 슬롯이 없습니다. 온라인 강좌만 선택된 상태일 수 있습니다.)"

    p_min, p_max = min(periods), max(periods)

    # Fill grid by period (row) and day (col)
    grid: Dict[Tuple[int, str], str] = {}

    def short(name: str, max_len: int = 10) -> str:
        n = re.sub(r"\s+", "", name)
        return n[:max_len]

    for c in picked:
        label = short(c.name)
        for s in c.slots:
            if s.day_en not in days:
                continue
            for p in range(s.start_period, s.end_period + 1):
                key = (p, s.day_en)
                if key in grid and grid[key] != label:
                    grid[key] = "(충돌)"
                else:
                    grid[key] = label

    header = "| 시간 | 월 | 화 | 수 | 목 | 금 |"
    sep = "|---|---|---|---|---|---|"
    rows = [header, sep]
    for p in range(p_min, p_max + 1):
        time_label = f"{period_to_time_label(p)}~{period_to_time_label(p+1)}"
        cells = [grid.get((p, d), "") for d in days]
        rows.append("| " + " | ".join([time_label] + cells) + " |")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", required=True)
    ap.add_argument("--major", default="Y030")
    ap.add_argument("--target", type=int, default=18, help="Target credits (default: 18)")
    ap.add_argument("--year", type=int, default=2, help="Prefer this year courses (default: 2)")
    ap.add_argument(
        "--allow-other-years",
        action="store_true",
        help="If set, allow non-matching year courses from the beginning (default: off = mostly year-only)",
    )
    ap.add_argument("--max-days", type=int, default=3, help="Prefer schedules within N on-campus days (default: 3)")
    ap.add_argument("--day-penalty", type=int, default=15, help="Penalty when adding a new on-campus day (default: 15)")
    ap.add_argument("--format", choices=["md", "ascii", "both"], default="md", help="Timetable output format")
    ap.add_argument("--no-timetable", action="store_true", help="Do not print timetable")
    ap.add_argument("--max-period", type=int, default=12, help="Max period rows for ASCII timetable")
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
                grade=r.get("grade") or "",
                prof=r.get("prof") or "",
                classroom=r.get("classroom") or "",
            )
        )

    # Dedup by code (keep first)
    dedup: "OrderedDict[str, Course]" = OrderedDict()
    for c in courses:
        dedup.setdefault(c.code, c)
    courses = list(dedup.values())

    # Filter to major buckets only
    courses = [c for c in courses if c.isu in {"전필", "전지", "전공필수", "전공지정", "전기", "전선"}]

    # Year handling
    def year_of(c: Course) -> Optional[int]:
        return parse_int_safe(c.grade)

    def is_target_year(c: Course) -> bool:
        y = year_of(c)
        return y is not None and y == args.year

    def year_match_rank(c: Course) -> int:
        # 1: exact match, 0: unknown, -1: other
        y = year_of(c)
        if y is None:
            return 0
        return 1 if y == args.year else -1

    # If user is year<=2, capstone is almost always not intended.
    # Keep it out unless other-years are allowed.
    if args.year <= 2 and not args.allow_other_years:
        courses = [c for c in courses if "캡스톤" not in c.name]

    # Two-pass ranking: (1) strict target-year, then (2) expand if credits are insufficient.
    primary = [c for c in courses if is_target_year(c)]
    secondary = [c for c in courses if c not in primary]

    def rank_key(c: Course) -> Tuple[int, int]:
        return (year_match_rank(c), total_score(c))

    if args.allow_other_years:
        ranked = sorted(courses, key=lambda x: rank_key(x), reverse=True)
    else:
        ranked = sorted(primary, key=lambda x: total_score(x), reverse=True)
        # secondary will be appended only if we can't reach target.

    picked: List[Course] = []
    total = 0
    used_days: List[str] = []

    def incremental_cost(cand: Course) -> int:
        new_days = [d for d in course_days(cand) if d not in used_days]
        penalty = args.day_penalty * len(new_days)
        if used_days and (len(used_days) + len(new_days) > args.max_days):
            penalty += args.day_penalty * 3
        return penalty

    def try_pick_from(cands: List[Course], *, non_year_penalty: int) -> None:
        nonlocal total
        for cand in cands:
            if total >= args.target:
                break
            if cand.credit <= 0:
                continue
            if any(conflict(cand, p) for p in picked):
                continue

            base = total_score(cand)
            net = base - incremental_cost(cand) - non_year_penalty
            # For target-year pass, be less strict so we can actually fill credits.
            min_net = 25 if non_year_penalty == 0 else 40
            if net < min_net and total < args.target - 3:
                continue

            picked.append(cand)
            total += cand.credit
            for d in course_days(cand):
                if d not in used_days:
                    used_days.append(d)

    # Pass 1: target-year only
    try_pick_from(ranked, non_year_penalty=0)

    # Pass 2: if still short
    # Default behavior (for "학년 맞춰 듣기"): do NOT auto-pick higher-year major courses.
    # Instead, leave remaining credits to 교양/자유선택.
    # If the user explicitly wants it, they can pass --allow-other-years.
    if total < args.target and args.allow_other_years:
        expanded = sorted(secondary, key=lambda x: rank_key(x), reverse=True)
        try_pick_from(expanded, non_year_penalty=25)

    # Output
    lines: List[str] = [f"# 📚 이번 학기 추천 ({args.term}, {args.major})", ""]
    lines.append(f"- 목표 학점: {args.target} (현재 추천 합: {total})")
    lines.append(f"- 우선: {args.year}학년 과목 위주 + 전필/전기/전선 우선순위")
    if not args.allow_other_years:
        lines.append("- 학년 필터: 기본은 해당 학년 과목 위주로 먼저 채우고, 부족할 때만 타 학년을 일부 섞습니다")
    lines.append("- 시간표 충돌 방지: 요일+교시 범위 파싱 후 겹치면 제외")
    lines.append(f"- 등교일 최소화: 새 요일이 추가되면 패널티 (max-days={args.max_days})")
    lines.append("")

    for c in picked:
        extra = ""
        if c.grade:
            extra += f" | {c.grade}"
        if c.classroom:
            extra += f" | {c.classroom}"
        if c.prof:
            extra += f" | {c.prof}"
        lines.append(f"- {c.isu} {c.name} ({c.credit}학점){extra}")

    lines.append("")
    lines.append(f"- 예상 등교 요일: {', '.join(DAY_EN_TO_KO.get(d, d) for d in used_days) if used_days else '(온라인만)'}")

    # 교양 안내(현재 한계)
    if total < args.target:
        lines.append("")
        lines.append("## ✅ 남은 학점은 교양으로 채우기")
        lines.append(
            "- 요청하신 대로 '학년(2학년) 과목 위주'로만 전공을 채우면, 남는 학점은 교양/자유선택으로 채우는 방식이 가장 자연스럽습니다."
        )
        lines.append(
            "- 현재 버전은 전공 시간표 API(major=Y030 등) 기반이라, 교양 전체 개설 과목을 자동으로 추천/충돌검사까지 하기는 어렵습니다."
        )
        lines.append(f"- 남은 학점: {args.target - total}학점 → 교양 2~3과목(각 2~3학점)으로 채우는 것을 권장")
        lines.append("- (옵션) 타 학년 전공까지 섞어서 18학점 꽉 채우고 싶으면 `--allow-other-years`를 켜세요")

    if not args.no_timetable:
        if args.format in {"md", "both"}:
            lines.append("")
            lines.append("## 🗓️ 시간표(마크다운, 시간 라벨)")
            lines.append(render_markdown_timetable(picked))
            lines.append("")
            lines.append("- 시간 라벨은 기본값(1교시=09:00, 교시당 1시간)으로 표시됩니다. 학교 공식 시간과 다를 수 있어요.")

        if args.format in {"ascii", "both"}:
            lines.append("")
            lines.append("## 🗓️ 시간표(ASCII, 교시)")
            lines.append("```")
            lines.append(_render_ascii_timetable(picked, max_period=args.max_period))
            lines.append("```")

    print("\n".join(lines).strip() + "\n")


def _short_name(name: str, max_len: int = 6) -> str:
    n = re.sub(r"\s+", "", name)
    return n[:max_len]


def _render_ascii_timetable(courses: List[Course], days: Optional[List[str]] = None, max_period: int = 12) -> str:
    if days is None:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    grid: Dict[Tuple[int, str], str] = {}
    for c in courses:
        label = _short_name(c.name)
        for sl in c.slots:
            if sl.day_en not in days:
                continue
            for p in range(sl.start_period, sl.end_period + 1):
                if p > max_period:
                    continue
                key = (p, sl.day_en)
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


if __name__ == "__main__":
    main()
