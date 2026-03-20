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
import secrets
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import httpx

# Repo-root relative paths (better first-run UX when cloning)
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Cookie/session state (prefer repo-local secrets/, but keep OpenClaw fallback)
STATE = REPO_ROOT / "secrets" / "hansung_info_storage.json"
OPENCLAW_STATE_FALLBACK = pathlib.Path("/home/ubuntu/.openclaw/workspace/secrets/hansung_info_storage.json")

INDEX = "https://info.hansung.ac.kr/jsp_21/index.jsp"
BASE = "https://info.hansung.ac.kr/jsp_21/student/kyomu/"
HISTORY = BASE + "siganpyo_aui_data.jsp"

# Publish config for static HTML serving (e.g. docker volume mounted into nginx)
PUBLISH_CFG = pathlib.Path.home() / ".config" / "hansung-info-course-recommender" / "publish.json"
DEFAULT_PUBLISH_DIR = pathlib.Path.home() / "docker_volumes" / "hansung-info-static" / "html"


def cookies_from_state() -> httpx.Cookies:
    state_path = STATE
    if not state_path.exists() and OPENCLAW_STATE_FALLBACK.exists():
        state_path = OPENCLAW_STATE_FALLBACK

    if not state_path.exists():
        raise SystemExit(
            "No session state found. Run login_refresh.py first (it should create secrets/hansung_info_storage.json)."
        )

    data = json.loads(state_path.read_text(encoding="utf-8"))
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
    start_suffix: str = ""  # e.g. "M" (break slot)
    end_suffix: str = ""  # e.g. "M" (include break after end_period)

    @property
    def day_ko(self) -> str:
        return DAY_EN_TO_KO.get(self.day_en, self.day_en)


def _iter_korean_day_spans(text: str) -> Iterable[Tuple[str, int, str, int, str]]:
    """Yield (day_kr, start_period, start_suffix, end_period, end_suffix) from a classroom string.

    Hansung uses period numbers for class time, and "M" to indicate the *break slot*.
    Examples:
    - "금6~8M"      (include the break after 8교시)
    - "월2M~3M"     (from break after 2교시 to break after 3교시)
    - "수5M~6M"     (from break after 5교시 to break after 6교시)
    - "월2M~3"      (from break after 2교시 to end of 3교시)
    - "월2~3"       (pure class periods)
    """

    if not text:
        return
    for part in text.split("/"):
        part = part.strip()
        m = re.search(r"([월화수목금토일])\s*(\d+)\s*([A-Z]?)\s*~\s*(\d+)\s*([A-Z]?)", part)
        if not m:
            continue
        day_kr = m.group(1)
        start_p = int(m.group(2))
        start_suf = (m.group(3) or "").strip()
        end_p = int(m.group(4))
        end_suf = (m.group(5) or "").strip()
        yield day_kr, start_p, start_suf, end_p, end_suf


def parse_slots(classroom: str) -> List[Slot]:
    slots: List[Slot] = []
    for day_kr, start_p, start_suf, end_p, end_suf in _iter_korean_day_spans(classroom):
        day_en = DAY_KO_TO_EN.get(day_kr, day_kr)
        if start_p > 0 and end_p > 0 and end_p >= start_p:
            slots.append(
                Slot(
                    day_en=day_en,
                    start_period=start_p,
                    end_period=end_p,
                    start_suffix=start_suf,
                    end_suffix=end_suf,
                )
            )
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


def _parse_hhmm(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _period_hour(period: int) -> int:
    """Map Hansung period number to an hour boundary.

    User rule: treat all boundaries as :00 / :30 only (ignore 50-min model).
    We use a simple boundary mapping: 1 -> 09:00, 2 -> 10:00, ...

    This matches the two rules:
    - n: boundary at hour of period n
    - nM: boundary at +30 minutes (start) or next hour (end)
    """

    return 8 + period


# 30-minute boundary mapping
# We render the timetable on a 30-min grid. The key is: boundaries depend on day-pattern.
# - Tue/Fri: simple hour boundaries (n->(n+8):00, nM->(n+8):30)
# - Mon/Wed/Thu: Hansung's 75-min pattern, snapped to 30-min boundaries (provided by user)
MWT_BOUNDARIES: Dict[Tuple[int, str], str] = {
    # class starts
    (1, ""): "09:00",
    (3, ""): "10:30",
    (4, ""): "12:00",
    (6, ""): "13:30",
    (7, ""): "15:00",
    (9, ""): "16:30",
    # aliases observed in 종정시 strings
    (2, "M"): "10:30",
    (5, "M"): "13:30",
    (8, ""): "16:30",
    (8, "M"): "16:30",
    # ends/break boundaries
    (1, "M"): "10:30",
    (3, "M"): "12:00",
    (4, "M"): "13:30",
    (6, "M"): "15:00",
    (7, "M"): "16:30",
    (9, "M"): "18:00",
}


def _boundary_minutes(day_en: str, period: int, suffix: str) -> int:
    suf = (suffix or "").upper()

    # Mon/Wed/Thu special mapping
    if day_en in {"Mon", "Wed", "Thu"}:
        hhmm = MWT_BOUNDARIES.get((period, suf))
        if hhmm:
            return _parse_hhmm(hhmm)
        # fallback to simple mapping if unknown marker shows up

    # Tue/Fri (and fallback): n -> (n+8):00, nM -> (n+8):30
    base = _period_hour(period) * 60
    return base + (30 if suf == "M" else 0)


def slot_to_minutes(s: Slot) -> Tuple[int, int]:
    """Convert Slot to (start_min, end_min) minutes in day on a 30-min grid."""

    start_min = _boundary_minutes(s.day_en, s.start_period, s.start_suffix)
    end_min = _boundary_minutes(s.day_en, s.end_period, s.end_suffix)
    return start_min, end_min


def _overlap(a: Slot, b: Slot) -> bool:
    if a.day_en != b.day_en:
        return False
    a0, a1 = slot_to_minutes(a)
    b0, b1 = slot_to_minutes(b)
    # Treat as half-open intervals.
    return (a0 < b1) and (b0 < a1)


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


# Period boundary labels for display (per user rule: everything ends at :00 or :30)
# We treat period numbers as hour boundaries: 1->09:00, 2->10:00, ...
PERIOD_TIME_SLOTS: Dict[int, Dict[str, str]] = {
    p: {"start": f"{8+p:02d}:00", "end": f"{9+p:02d}:00"} for p in range(1, 15)
}


def period_time(period: int) -> Tuple[str, str]:
    """Return (start, end) time label for a given Hansung period."""

    slot = PERIOD_TIME_SLOTS.get(period)
    if slot:
        return slot["start"], slot["end"]

    # Fallback: keep the old behavior (1교시=09:00, +1h) for out-of-range periods.
    hour = 9 + (period - 1)
    return f"{hour:02d}:00", f"{(hour + 1):02d}:00"


def period_to_time_label(period: int) -> str:
    start, _end = period_time(period)
    return start


def slot_to_timerange(s: Slot) -> str:
    start, _ = period_time(s.start_period)
    _, end = period_time(s.end_period)
    start_min, end_min = slot_to_minutes(s)
    # If M modifies boundaries, show exact minutes.
    if (s.start_suffix or "").upper() == "M" or (s.end_suffix or "").upper() == "M":
        sh, sm = divmod(start_min, 60)
        eh, em = divmod(end_min, 60)
        return f"{sh:02d}:{sm:02d}~{eh:02d}:{em:02d}"
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
        start, end = period_time(p)
        time_label = f"{start}~{end}"
        cells = [grid.get((p, d), "") for d in days]
        rows.append("| " + " | ".join([time_label] + cells) + " |")
    return "\n".join(rows)


def _load_publish_config_interactive() -> Dict[str, str]:
    """Load publish config, or ask once and persist.

    First-time UX:
    - Ask for publish_dir (where nginx serves static HTML)
    - Ask for base_url (so we can print clickable links)

    Stored at: ~/.config/hansung-info-course-recommender/publish.json
    """

    cfg: Dict[str, str] = {}
    if PUBLISH_CFG.exists():
        try:
            cfg = json.loads(PUBLISH_CFG.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    default_dir = str(DEFAULT_PUBLISH_DIR)
    publish_dir = (cfg.get("publish_dir") or "").strip()
    base_url = (cfg.get("base_url") or "").strip()

    if not publish_dir:
        try:
            ans = input(f"[publish] 정적 HTML을 저장할 폴더를 입력하세요 (default: {default_dir})\n> ").strip()
        except EOFError:
            ans = ""
        publish_dir = ans or default_dir

    if not base_url:
        try:
            ans = input("[publish] 브라우저로 볼 base URL을 입력하세요 (예: http://localhost:8282)\n> ").strip()
        except EOFError:
            ans = ""
        base_url = ans

    p = pathlib.Path(publish_dir).expanduser()
    p.mkdir(parents=True, exist_ok=True)

    PUBLISH_CFG.parent.mkdir(parents=True, exist_ok=True)
    PUBLISH_CFG.write_text(
        json.dumps({"publish_dir": str(p), "base_url": base_url}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"publish_dir": str(p), "base_url": base_url}


def publish_html(html: str, *, publish_dir: pathlib.Path, slug: Optional[str] = None) -> pathlib.Path:
    """Write a generated HTML timetable to a static-serving directory.

    - Writes to: <publish_dir>/timetables/<slug>/index.html
    - Updates: <publish_dir>/latest/index.html
    - Updates: <publish_dir>/index.html  (so `/` always shows the latest)

    Returns the written index.html path.
    """

    slug = slug or (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_urlsafe(4))
    base = publish_dir / "timetables" / slug
    base.mkdir(parents=True, exist_ok=True)

    out = base / "index.html"
    out.write_text(html, encoding="utf-8")

    latest = publish_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    (latest / "index.html").write_text(html, encoding="utf-8")

    # Convenience: root index points to latest content.
    (publish_dir / "index.html").write_text(html, encoding="utf-8")

    return out


def render_html_timetable(picked: List[Course]) -> str:
    """Render a simple HTML weekly timetable similar to the Hansung personal timetable view.

    - 30-minute grid on the left.
    - Mon..Fri columns.
    - Each offline class becomes a positioned block with its exact (minute) time range.

    Note: This is a self-contained HTML (inline CSS) so it can be hosted anywhere as a static file.
    """

    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    day_labels = {"Mon": "월", "Tue": "화", "Wed": "수", "Thu": "목", "Fri": "금"}

    # Build events
    events: List[Dict[str, object]] = []
    for c in picked:
        if not c.slots:
            continue
        for s in c.slots:
            if s.day_en not in days:
                continue
            start_min, end_min = slot_to_minutes(s)
            events.append(
                {
                    "day": s.day_en,
                    "start": start_min,
                    "end": end_min,
                    "title": c.name,
                    "meta": f"{slot_to_timerange(s)} | {c.prof}".strip(" |"),
                }
            )

    if not events:
        return "<p>(표시할 오프라인 시간표 슬롯이 없습니다. 온라인 강좌만 선택된 상태일 수 있습니다.)</p>"

    # Visual range
    day_start = _parse_hhmm("08:00")
    day_end = _parse_hhmm("22:30")

    # Expand range to fit events
    day_start = min(day_start, min(e["start"] for e in events))
    day_end = max(day_end, max(e["end"] for e in events))

    # Pixel scale
    px_per_min = 1.2  # 50min ~ 60px
    total_h = int((day_end - day_start) * px_per_min)

    def fmt(mins: int) -> str:
        h, m = divmod(mins, 60)
        return f"{h:02d}:{m:02d}"

    # Time ticks every 30 minutes
    ticks = list(range((day_start // 30) * 30, day_end + 1, 30))

    # Layout constants
    time_col_w = 72
    day_col_w = 210
    header_h = 36

    # Render blocks
    blocks: List[str] = []
    for e in events:
        top = int((int(e["start"]) - day_start) * px_per_min) + header_h
        height = max(18, int((int(e["end"]) - int(e["start"])) * px_per_min) - 2)
        day_idx = days.index(str(e["day"]))
        # Align block to the column borders (flush with right edge)
        left = time_col_w + day_idx * day_col_w + 1
        width = day_col_w - 2
        blocks.append(
            "\n".join(
                [
                    f"<div class='event' style='top:{top}px;left:{left}px;height:{height}px;width:{width}px'>",
                    f"  <div class='event-time'>{fmt(int(e['start']))}~{fmt(int(e['end']))}</div>",
                    f"  <div class='event-title'>{e['title']}</div>",
                    (f"  <div class='event-meta'>{e['meta']}</div>" if e.get("meta") else ""),
                    "</div>",
                ]
            )
        )

    # Grid lines
    grid_lines: List[str] = []
    for t in ticks:
        y = int((t - day_start) * px_per_min) + header_h
        label = fmt(t)
        mm = t % 60
        cls = "hline hour" if mm == 0 else "hline half"
        grid_lines.append(f"<div class='{cls}' style='top:{y}px'></div>")
        grid_lines.append(f"<div class='tlabel' style='top:{y-8}px'>{label}</div>")

    # Day headers
    day_headers = "".join(
        [
            f"<div class='dayhead' style='left:{time_col_w + i*day_col_w}px;width:{day_col_w}px'>{day_labels[d]}</div>"
            for i, d in enumerate(days)
        ]
    )

    html = f"""<!doctype html>
<html lang='ko'>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width, initial-scale=1'/>
  <title>Hansung Timetable</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; margin: 16px; }}
    .wrap {{ position: relative; width: {time_col_w + day_col_w*5}px; border: 1px solid #ddd; overflow: hidden; }}
    .header {{ position: sticky; top: 0; background: #fff; border-bottom: 1px solid #ddd; height: {header_h}px; z-index: 5; }}
    .timehead {{ position:absolute; left:0; top:0; width:{time_col_w}px; height:{header_h}px; border-right:1px solid #eee; }}
    .dayhead {{ position:absolute; top:0; height:{header_h}px; display:flex; align-items:center; justify-content:center; border-right:1px solid #eee; font-weight: 700; text-align:center; }}
    .grid {{ position: relative; height: {total_h + header_h}px; }}
    .hline {{ position:absolute; left:0; right:0; background:#f1f1f1; z-index: 1; }}
    .hline.half {{ height: 1px; opacity: 0.9; }}
    .hline.hour {{ height: 2px; background:#d9d9d9; }}
    .tlabel {{ position:absolute; left:0; width:{time_col_w-8}px; text-align:center; font-size: 12px; color:#555; padding-right: 8px; z-index: 2; }}
    .vline {{ position:absolute; top:{header_h}px; bottom:0; width:1px; background:#eee; z-index: 1; }}
    .event {{ position:absolute; background: #E7F0FF; border: 1px solid #9EC1FF; border-radius: 6px; padding: 6px 8px; box-sizing: border-box; z-index: 3; overflow: hidden; text-align: center; display:flex; flex-direction:column; justify-content:center; }}
    .event-time {{ font-size: 11px; color: #1f3b7a; margin-bottom: 2px; }}
    .event-title {{ font-size: 13px; font-weight: 800; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    .event-meta {{ font-size: 11px; color: #334; margin-top: 2px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
  </style>
</head>
<body>
  <div class='wrap'>
    <div class='header'>
      <div class='timehead'></div>
      {day_headers}
    </div>
    <div class='grid'>
      {''.join(grid_lines)}
      {''.join([f"<div class='vline' style='left:{time_col_w + i*day_col_w}px'></div>" for i in range(6)])}
      {''.join(blocks)}
    </div>
  </div>
</body>
</html>
"""
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
    ap.add_argument("--format", choices=["md", "ascii", "both", "html"], default="md", help="Timetable output format")
    ap.add_argument("--out", help="Write output to a file instead of stdout (useful for --format html)")
    ap.add_argument(
        "--publish",
        action="store_true",
        help="If set with --format html, save the HTML into a preconfigured static directory (first run prompts).",
    )
    ap.add_argument(
        "--publish-dir",
        help="Override publish dir (otherwise uses persisted config under ~/.config/hansung-info-course-recommender/publish.json)",
    )
    ap.add_argument(
        "--publish-base-url",
        help="If set, also print clickable URLs (e.g. http://localhost:8282).",
    )
    ap.add_argument("--no-timetable", action="store_true", help="Do not print timetable")
    ap.add_argument("--max-period", type=int, default=12, help="Max period rows for ASCII timetable")
    ap.add_argument(
        "--fill-ge",
        action="store_true",
        help="If set, fill remaining credits with 교양(교필/선필교/일교/일선) offerings (default: off)",
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
    raw_count = len(raw)

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
    dedup_count = len(courses)

    # Filter to known buckets (major + GE)
    before_bucket = len(courses)
    courses = [
        c
        for c in courses
        if c.isu
        in {"전필", "전지", "전공필수", "전공지정", "전기", "전선", "교필", "선필교", "일교", "일선"}
    ]
    bucket_count = len(courses)

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
    picked_online: List[Course] = []

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
            if not cand.slots:
                picked_online.append(cand)
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

    # Explainable rationale (what data + what constraints were applied)
    lines.append("## 🔎 근거(데이터/제약/니즈 반영)")
    lines.append(f"- 데이터 소스: 종정시 개설과목 API(siganpyo_aui_data.jsp history) 조회")
    lines.append(f"- 원본 행 수: {raw_count} → 과목코드 기준 중복 제거 후: {dedup_count} → 분류(전필/전기/전선/교필/선필교/일교/일선) 필터 후: {bucket_count}")
    lines.append(f"- 사용자 니즈(옵션): target={args.target}학점, {args.year}학년 우선, max-days={args.max_days}, fill-ge={'on' if args.fill_ge else 'off'}, allow-other-years={'on' if args.allow_other_years else 'off'}")
    lines.append("- 추천 로직: (1) 전필/전기/전선 우선순위 점수화 (2) 시간표 충돌 제외 (3) 등교 요일 추가 패널티로 요일 수 최소화")
    lines.append(
        "- 주의: 개인의 '미이수 전필/교양요건 충족 여부'는 현재 자동 판정하지 않습니다(개설과목 기반 추천)."
    )
    lines.append("")

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

    if picked_online:
        lines.append("")
        lines.append("## 🌐 온라인/비대면(시간 미표기) 과목")
        lines.append("- 종정시 응답에서 시간 슬롯 파싱이 안 되는 과목은 여기로 분리합니다(충돌 검사 제외).")
        for c in picked_online:
            extra = ""
            if c.grade:
                extra += f" | {c.grade}"
            if c.prof:
                extra += f" | {c.prof}"
            # classroom may contain hints like 'e-러닝' etc.
            if c.classroom:
                extra += f" | {c.classroom}"
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
            lines.append("- 시간표는 30분 그리드로 렌더링하며, 월/수/목은 75분 패턴을 30분 경계로 스냅한 테이블을 사용합니다.")

        if args.format in {"ascii", "both"}:
            lines.append("")
            lines.append("## 🗓️ 시간표(ASCII, 교시)")
            lines.append("```")
            lines.append(_render_ascii_timetable(picked, max_period=args.max_period))
            lines.append("```")

        if args.format == "html":
            lines.append("")
            lines.append("## 🗓️ 시간표(HTML)")
            lines.append("- `--format html --out timetable.html` 로 파일로 저장해서 브라우저로 열어보세요")

    output_text = "\n".join(lines).strip() + "\n"

    # HTML timetable mode: emit ONLY the HTML document (no markdown header/list).
    published_path: Optional[pathlib.Path] = None
    if args.format == "html" and not args.no_timetable:
        output_text = render_html_timetable(picked)
        if args.publish:
            if args.publish_dir:
                publish_dir = pathlib.Path(args.publish_dir).expanduser()
                base_url = args.publish_base_url
            else:
                cfg = _load_publish_config_interactive()
                publish_dir = pathlib.Path(cfg["publish_dir"]).expanduser()
                base_url = args.publish_base_url or (cfg.get("base_url") or "")

            publish_dir.mkdir(parents=True, exist_ok=True)
            published_path = publish_html(output_text, publish_dir=publish_dir)
            # If base_url is available, print URLs even if --publish-base-url wasn't passed.
            if base_url and not args.publish_base_url:
                args.publish_base_url = base_url

    if args.out:
        pathlib.Path(args.out).write_text(output_text, encoding="utf-8")
    else:
        print(output_text)

    if published_path is not None:
        # Print paths for convenience (useful when the directory is volume-mounted into nginx).
        publish_root = published_path.parents[2] if len(published_path.parents) >= 3 else published_path.parent
        print(f"\n[publish] wrote: {published_path}")
        print(f"[publish] latest: {publish_root / 'latest' / 'index.html'}")

        if args.publish_base_url:
            base = args.publish_base_url.strip()
            if not base.startswith("http://") and not base.startswith("https://"):
                # Default to https when scheme is omitted.
                base = "https://" + base
            base = base.rstrip("/")
            # We always publish both a unique slug path and a stable latest path.
            slug = published_path.parent.name
            print(f"[publish] url (latest): {base}/latest/")
            print(f"[publish] url (this):   {base}/timetables/{slug}/")

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

    def _wcswidth(text: str) -> int:
        try:
            from wcwidth import wcswidth as _wcs

            w = _wcs(text)
            return w if w >= 0 else len(text)
        except Exception:
            import unicodedata

            w = 0
            for ch in text:
                w += 2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1
            return w

    def _center(text: str, width: int) -> str:
        w = _wcswidth(text)
        if w >= width:
            return text
        pad = width - w
        left = pad // 2
        right = pad - left
        return (" " * left) + text + (" " * right)

    col_w = 10
    header = " " * 4 + "".join(_center(d, col_w) for d in days)
    lines = [header]
    for p in range(1, max_period + 1):
        row = f"{p:>2}  "
        for d in days:
            row += _center(grid.get((p, d), "·"), col_w)
        lines.append(row)
    return "\n".join(lines)


if __name__ == "__main__":
    main()
