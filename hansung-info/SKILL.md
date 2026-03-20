---
name: hansung-info
description: Automate Hansung University portals (종합정보시스템 info.hansung.ac.kr) and AI응용학과 graduation/major requirements. Use when the user asks to fetch grades, enrolled semesters, curriculum/전공필수(전필) lists, 졸업요건 요약, or to build cron-based DM digests from 종정시/학과 졸업요건 페이지. Includes automatic login (no 2FA) + cookie refresh and HTTP-based extraction; can optionally use Playwright click automation.
---

# Hansung Info (종정시) Automation

## What this skill provides

- **Auto login** to 종정시 (info.hansung.ac.kr) and refresh cookies.
- **Grade summary** + credit-bucket summary (GPA/percentile/earned vs required).
- **Major curriculum API extraction** for AI응용학과 (sjungong=`Y030`) including **전필 후보 과목 리스트**.
- **Dept graduation requirements** page fetch (public Hansung site) and key bullets.

## Security / guardrails

- Treat 종정시 credentials + cookies as secrets.
- Store cookie state under `workspace/secrets/` (chmod 600) and keep it gitignored.
- This skill is **read-only** automation. Do not perform write actions (수강신청/변경/제출).

## Setup (env)

In `~/.openclaw/.env`:

- `HANSUNG_INFO_ID`
- `HANSUNG_INFO_PASSWORD`

Optional (for DM send via OpenClaw):
- none (uses `openclaw message send` directly)

## Scripts

### 1) Refresh login cookies

```bash
cd /home/ubuntu/.openclaw/workspace
set -a && source /home/ubuntu/.openclaw/.env && set +a
python3 skills/hansung-info/scripts/login_refresh.py
```

Writes: `secrets/hansung_info_storage.json`

### 2) 성적 + 이수구분 요약

```bash
python3 skills/hansung-info/scripts/grade_summary.py
```

### 3) 전공/트랙 코드 목록(드롭다운) 조회

```bash
# term(학기) 기준으로 종정시 드롭다운(sjungong) 옵션을 그대로 가져옵니다.
python3 hansung-info/scripts/jungong_list.py --term 20261
python3 hansung-info/scripts/jungong_list.py --term 20261 --format json --out .tmp/jungonglist_20261.json
```

### 4) 이번 학기 개설 과목(시간표) 조회

```bash
python3 skills/hansung-info/scripts/timetable_offerings.py --term 20261 --major Y030
python3 skills/hansung-info/scripts/timetable_offerings.py --term 20261 --major Y030 --only-required
```

### 4) AI응용학과(Y030) 전필 후보 리스트(교육과정/카탈로그)

```bash
python3 skills/hansung-info/scripts/major_curriculum.py --term 20261 --major Y030
python3 skills/hansung-info/scripts/major_curriculum.py --scan-terms --major Y030 --only-required
```

### 5) 이번 학기 추천(학년 위주 + 충돌 방지 + 시간표 출력)

```bash
# 2학년 과목 위주로 전공을 채우고, 남는 학점은 교양으로 채우는 플랜(권장)
python3 hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18 --year 2 --max-days 3 --format md

# 개인시간표조회 스타일(웹처럼 보기): HTML 파일 생성
python3 hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18 --year 2 --max-days 3 --format html --out timetable.html

# (권장) 정적 서빙 폴더로 바로 publish (첫 실행 시 경로를 물어보고 저장합니다)
python3 hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18 --year 2 --max-days 3 --format html --publish --publish-base-url http://localhost:8282

# 전공+교양까지 포함해서 18학점 자동 채우기
python3 hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18 --year 2 --max-days 3 --format md --fill-ge

# 타 학년 전공까지 섞어서 18학점 꽉 채우고 싶으면
python3 hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18 --year 2 --allow-other-years --format md
```

> 참고: 시간 라벨/충돌 계산은 운혁 님 규칙대로 **`:00`/`:30` 경계 + `n`/`nM` 표기 해석** 기준으로 표시됩니다.

### 6) 졸업 로드맵(전공필수는 '체크리스트'가 아니라 '학점 기준'으로 플래닝)

```bash
python3 skills/hansung-info/scripts/roadmap_generator.py --start 20261 --grad 20282 --major Y030
# 전공필수 목표 학점 조정
python3 skills/hansung-info/scripts/roadmap_generator.py --start 20261 --grad 20282 --major Y030 --required-credits 21
```

### 7) 학과 ‘추가 졸업요건’(공인영어/캡스톤/산학협력) 요약

```bash
python3 skills/hansung-info/scripts/dept_grad_requirements.py
```

## Period/time mapping (Hansung) — important

운혁 님 규칙(현업용 단순화): **모든 과목은 `:00` 또는 `:30` 경계로만 시작/종료**한다고 가정합니다.

- 표기 규칙
  1) `n` 으로 시작/끝나면 → **n에 해당하는 시각 정시(:00)** 에 시작/종료
  2) `nM` 으로 시작하면 → **n 시각 + 30분(:30)** 에 시작
     `nM` 으로 끝나면 → **n 시각 + 30분(:30)** 에 종료

- 시간 경계(예시)
  - `2` = 10:00 경계
  - `2M` = 10:30 경계(시작), 또는 11:00 경계(끝)

이 규칙은 **시간표 충돌 검사**에 직접 영향이 있어요.

## References

- API endpoints / parsing notes: `references/endpoints.md`
