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
- 교양 과목도 종정시 시간표 API에서 코드(L11E/L11F/L11G/L11H)로 조회 가능합니다.
  다만 졸업요건의 "교필/선필교" 정확한 학점 규칙은 학번/규정에 따라 달라질 수 있어,
  현재는 **개설 과목 기반 추천**만 수행하고, 요건 충족 판정은 추가 크롤링/연동이 필요합니다.

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


def fetch_offerings(client: httpx.Client, *, term: str, code: str) -> List[Dict[str, str]]:
    """Fetch offerings rows for a given term + 'sjungong' code.

    Notes:
    - Major example: Y030 (AI응용학과)
    - General education examples:
      - L11E 교양필수
      - L11F 선택필수교양(선필교)
      - L11G 일반교양
      - L11H 일반선택
    """

    xml = client.post(HISTORY, data={"gubun": "history", "syearhakgi": term, "sjungong": code}).text
    if "로그인 정보를 잃었습니다" in xml:
        raise SystemExit("Session expired. Run login_refresh.py")
    return parse_rows(xml)


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
    # Major buckets
    if c.isu in {"전필", "전공지정", "전공필수", "전지"}:
        return 100
    if c.isu == "전기":
        return 70
    if c.isu == "전선":
        return 50
    # General education buckets (observed)
    if c.isu in {"교필"}:
        return 65
    if c.isu in {"선필교"}:
        return 60
    if c.isu in {"일교"}:
        return 55
    if c.isu in {"일선"}:
        return 45
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


def render_html_timetable(*, term: str, major: str, target: int, picked: List[Course]) -> str:
    """Render a standalone HTML page for the timetable.

    Notes:
    - Uses a simple period->time mapping (1교시=09:00, +1h) for readability.
    - Shows a weekly grid (Mon..Fri) and a picked course list.
    """

    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    days_ko = {"Mon": "월", "Tue": "화", "Wed": "수", "Thu": "목", "Fri": "금"}

    # Determine grid range
    periods: List[int] = []
    for c in picked:
        for s in c.slots:
            for p in range(s.start_period, s.end_period + 1):
                periods.append(p)
    if periods:
        p_min, p_max = min(periods), max(periods)
    else:
        p_min, p_max = 1, 12

    # Build cell -> list of course labels
    cell: Dict[Tuple[int, str], List[str]] = {}

    def label(c: Course) -> str:
        # keep compact
        return re.sub(r"\s+", " ", c.name).strip()

    for c in picked:
        for s in c.slots:
            if s.day_en not in days:
                continue
            for p in range(s.start_period, s.end_period + 1):
                cell.setdefault((p, s.day_en), []).append(label(c))

    # Course list HTML
    li = []
    for c in picked:
        meta = []
        if c.isu:
            meta.append(c.isu)
        if c.credit:
            meta.append(f"{c.credit}학점")
        if c.grade:
            meta.append(f"{c.grade}학년")
        if c.prof:
            meta.append(c.prof)
        if c.classroom:
            meta.append(c.classroom)
        li.append(f"<li><b>{label(c)}</b><div class='meta'>{' · '.join(meta)}</div></li>")

    # Grid rows
    grid_rows = []
    for p in range(p_min, p_max + 1):
        t = f"{period_to_time_label(p)}~{period_to_time_label(p+1)}"
        tcell = f"<div class='time'>{t}</div>"
        cols = []
        for d in days:
            items = cell.get((p, d), [])
            if not items:
                cols.append("<div class='cell empty'></div>")
            else:
                # de-dup within cell
                uniq = []
                for x in items:
                    if x not in uniq:
                        uniq.append(x)
                cols.append("<div class='cell'><div class='course'>" + "<br>".join(uniq) + "</div></div>")
        grid_rows.append("<div class='row'>" + tcell + "".join(cols) + "</div>")

    title = f"{term} {major} 추천 시간표"
    html = f"""<!doctype html>
<html lang='ko'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>{title}</title>
  <style>
    :root {{ --bg:#0b0f17; --panel:#111827; --muted:#94a3b8; --line:#243042; --text:#e5e7eb; --accent:#60a5fa; }}
    body {{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, 'Noto Sans KR', Arial; background:var(--bg); color:var(--text); }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 22px; }}
    h1 {{ margin:0 0 8px; font-size: 20px; }}
    .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 18px; }}
    .grid {{ border:1px solid var(--line); border-radius: 10px; overflow:hidden; background:var(--panel); }}
    .head {{ display:grid; grid-template-columns: 120px repeat(5, 1fr); background:rgba(255,255,255,0.03); border-bottom:1px solid var(--line); }}
    .head div {{ padding:10px 12px; font-weight:600; color:var(--muted); }}
    .row {{ display:grid; grid-template-columns: 120px repeat(5, 1fr); border-bottom:1px solid var(--line); }}
    .row:last-child {{ border-bottom:none; }}
    .time {{ padding:10px 12px; color:var(--muted); font-variant-numeric: tabular-nums; border-right:1px solid var(--line); }}
    .cell {{ padding:8px 10px; border-right:1px solid var(--line); min-height:40px; }}
    .cell:last-child {{ border-right:none; }}
    .cell.empty {{ background: rgba(0,0,0,0.06); }}
    .course {{ background: rgba(96,165,250,0.12); border: 1px solid rgba(96,165,250,0.25); padding:6px 8px; border-radius: 8px; line-height:1.25; }}
    .cols {{ display:grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }}
    .card {{ border:1px solid var(--line); border-radius: 10px; background:var(--panel); padding: 12px 14px; }}
    .card h2 {{ margin:0 0 10px; font-size: 14px; color: var(--muted); }}
    ul {{ margin:0; padding-left: 18px; }}
    li {{ margin: 8px 0; }}
    .meta {{ margin-top:4px; color: var(--muted); font-size: 12px; }}
    .note {{ margin-top: 10px; color: var(--muted); font-size: 12px; }}
    a {{ color: var(--accent); }}
  </style>
</head>
<body>
  <div class='wrap'>
    <h1>{title}</h1>
    <div class='sub'>목표 {target}학점 · 생성 시각표시는 기본 매핑(1교시=09:00, 교시당 1시간) 기반입니다.</div>

    <div class='grid'>
      <div class='head'>
        <div>시간</div>
        <div>{days_ko['Mon']}</div>
        <div>{days_ko['Tue']}</div>
        <div>{days_ko['Wed']}</div>
        <div>{days_ko['Thu']}</div>
        <div>{days_ko['Fri']}</div>
      </div>
      {''.join(grid_rows)}
    </div>

    <div class='cols'>
      <div class='card'>
        <h2>선택 과목</h2>
        <ul>
          {''.join(li)}
        </ul>
        <div class='note'>※ 온라인강좌 시간(예: 1.5시간)은 오프라인 그리드에 표시되지 않을 수 있습니다.</div>
      </div>
      <div class='card'>
        <h2>공유</h2>
        <div class='note'>이 페이지는 스크립트 실행 결과로 생성된 정적 HTML입니다.</div>
        <div class='note'>GitHub Pages로 호스팅하면 링크 하나로 공유할 수 있습니다.</div>
      </div>
    </div>
  </div>
</body>
</html>"""
    return html


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
    ap.add_argument(
        "--fill-ge",
        action="store_true",
        help="If set, fill remaining credits with 교양(교필/선필교/일교/일선) offerings (default: off)",
    )
    ap.add_argument(
        "--out-html",
        default="",
        help="Write a standalone HTML timetable page to this path (e.g., docs/index.html)",
    )
    args = ap.parse_args()

    jar = cookies_from_state()
    client = httpx.Client(
        timeout=25,
        follow_redirects=True,
        cookies=jar,
        headers={"User-Agent": "Mozilla/5.0", "Referer": INDEX},
    )
    client.get(INDEX)
    raw = fetch_offerings(client, term=args.term, code=args.major)

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

    # Filter to known buckets (major + GE)
    courses = [
        c
        for c in courses
        if c.isu
        in {"전필", "전지", "전공필수", "전공지정", "전기", "전선", "교필", "선필교", "일교", "일선"}
    ]

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

    # Two-pass ranking for MAJOR courses: (1) strict target-year, then (2) optionally expand.
    # (GE filling is handled later via --fill-ge.)
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
    # If the user explicitly wants it, they can pass --allow-other-years.
    if total < args.target and args.allow_other_years:
        expanded = sorted(secondary, key=lambda x: rank_key(x), reverse=True)
        try_pick_from(expanded, non_year_penalty=25)

    # Pass 3 (optional): fill remaining credits with General Education offerings.
    if total < args.target and args.fill_ge:
        ge_codes = [
            ("교양필수", "L11E"),
            ("선택필수교양(선필교)", "L11F"),
            ("일반교양", "L11G"),
            ("일반선택", "L11H"),
        ]
        ge_courses: List[Course] = []
        for label, code in ge_codes:
            rows = fetch_offerings(client, term=args.term, code=code)
            for r in rows:
                if not r.get("code"):
                    continue
                try:
                    credit = int(r.get("credit") or 0)
                except ValueError:
                    credit = 0
                ge_courses.append(
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

        # Dedup GE by code
        ge_dedup: "OrderedDict[str, Course]" = OrderedDict()
        for gc in ge_courses:
            ge_dedup.setdefault(gc.code, gc)
        ge_courses = list(ge_dedup.values())

        # Rank: 교필 > 선필교 > 일교 > 일선, then prefer not adding new days
        ge_ranked = sorted(ge_courses, key=lambda x: total_score(x), reverse=True)
        try_pick_from(ge_ranked, non_year_penalty=0)

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

    # 교양 안내
    if total < args.target and not args.fill_ge:
        lines.append("")
        lines.append("## ✅ 남은 학점은 교양으로 채우기")
        lines.append(
            "- 요청하신 대로 '학년(2학년) 과목 위주'로만 전공을 채우면, 남는 학점은 교양/자유선택으로 채우는 방식이 가장 자연스럽습니다."
        )
        lines.append(
            "- 이 스킬은 교양도 코드(L11E/L11F/L11G/L11H)로 조회 가능하지만, 기본값은 전공 위주 추천만 수행합니다."
        )
        lines.append(f"- 남은 학점: {args.target - total}학점")
        lines.append("- 교양까지 자동으로 채우려면 `--fill-ge`를 켜세요")
        lines.append("- (옵션) 타 학년 전공까지 섞어서 18학점 꽉 채우고 싶으면 `--allow-other-years`를 켜세요")

    if args.fill_ge:
        lines.append("")
        lines.append("## ⚠️ 교양(교필/선필교) 규칙에 대한 안내")
        lines.append("- 현재 추천은 '개설 과목 + 시간표 충돌' 기반입니다.")
        lines.append("- 학번/졸업요건에 따른 교필/선필교 정확한 충족 판정은 추후 졸업요건 데이터 연동으로 보강 예정입니다.")

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

    # Optional HTML output (for GitHub Pages / sharing)
    if args.out_html:
        out = pathlib.Path(args.out_html)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            render_html_timetable(term=args.term, major=args.major, target=args.target, picked=picked),
            encoding="utf-8",
        )
        lines.append("")
        lines.append(f"- HTML 출력: {out}")

    print("\n".join(lines).strip() + "\n")
    client.close()


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
