# Hansung Info Course Recommender (한성대 종정시 교과목 추천 시스템)
This project was built using **OpenClaw only** (skills + scripts + automation).

한성대학교 종합정보시스템(종정시, info.hansung.ac.kr)에서 **조회 가능한 범위(개설과목/교육과정)** 를 기반으로 교과목을 추천합니다.
It recommends courses based on what the Hansung “Info” system exposes (offerings + curriculum catalog).

> ⚠️ 주의: 계정/쿠키는 로컬 `secrets/`에만 저장되며 레포에는 커밋하지 않습니다.
> Note: Credentials/cookies are stored locally under `secrets/` and must never be committed.

---

## 기술 (Tech)
- Python 3.10+ 기반의 스크립트형 자동화입니다.
  It is a script-based automation toolchain built with Python 3.10+.
- HTTP 클라이언트로 `httpx`를 사용해 종정시 AUIGrid 엔드포인트를 호출합니다.
  It uses `httpx` to call Hansung Info AUIGrid endpoints.
- 출력은 사람이 읽기 좋은 텍스트(Markdown/ASCII) 중심으로 설계했습니다.
  Outputs are designed to be human-readable (Markdown/ASCII).
- OpenClaw 스킬 형태로 운영하며, 외부 패키징/설치형 CLI 승격은 보류 상태입니다.
  It runs as an OpenClaw skill; packaging into an installable CLI is intentionally deferred.

---

## 기능 (Features)
- 로그인 세션(쿠키) 갱신 자동화.
  Automatic login session (cookie) refresh.
- 이번 학기 **실제 개설 과목**(시간표/수업계획서 조회) 수집.
  Fetches **actual offered courses** for a given term.
- 교육과정(카탈로그) 기반으로 전공필수(전필) 후보 과목 풀 수집.
  Collects a major-required course candidate pool from the curriculum catalog.
- 시간표 충돌을 피하면서 목표 학점(예: 18학점)에 맞춘 교과목 추천.
  Recommends a course set for target credits (e.g., 18) while avoiding timetable conflicts.
- 최종 시간표를 ASCII 도식으로 출력.
  Prints the final timetable as an ASCII grid.
- 전공필수는 “체크리스트”가 아니라 **학점 기준**으로 로드맵 초안을 생성.
  Generates a roadmap draft using a **credit-based** policy (not a strict checklist).

---

## 과정 (Process)
- 1) 종정시 로그인 후 쿠키를 로컬에 저장합니다.
  1) Log in and store cookies locally.
- 2) 개설 과목(시간표) 데이터를 가져와 과목 목록을 정규화합니다.
  2) Fetch term offerings (timetable) and normalize course records.
- 3) 교육과정(카탈로그)에서 전필 후보 풀을 스캔해 기준 데이터를 확보합니다.
  3) Scan curriculum catalog to build the baseline required-course pool.
- 4) 점수(전필/전기/전선 우선순위) + 충돌 검사(요일/교시 범위)로 추천 조합을 고릅니다.
  4) Pick a set using scoring (bucket priority) + conflict checks (day/period ranges).
- 5) 결과를 리스트/ASCII 시간표/로드맵 텍스트로 출력합니다.
  5) Output results as lists, ASCII timetable, and roadmap text.

---

## 실행 예시 (Examples)

```bash
# (1) 로그인 쿠키 갱신
# (1) Refresh login cookies
set -a && source ~/.openclaw/.env && set +a
python3 hansung-info/scripts/login_refresh.py

# (2) 이번 학기 교과목 추천 + ASCII 시간표
# (2) Recommend courses + ASCII timetable
python3 hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18

# (3) 전공필수 학점 기준 로드맵
# (3) Credit-based roadmap
python3 hansung-info/scripts/roadmap_generator.py --start 20261 --grad 20282 --major Y030 --required-credits 21
```

## Requirements
- `httpx` (see `requirements.txt`)
