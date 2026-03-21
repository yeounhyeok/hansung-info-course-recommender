---
name: hansung-info
description: "Read-only automation for Hansung Univ 종정시(info.hansung.ac.kr): login cookie refresh, offerings/curriculum fetch, and conflict-free course recommendations with copy-paste-friendly ASCII/Markdown timetable output."
---

# Hansung Info (종정시) — OpenClaw Skill

## 이 스킬이 하는 일(요약)
- 종정시 **로그인 쿠키 갱신** (no 2FA 가정)
- 이번 학기 **개설 과목(시간표) 조회**
- 교육과정 기반 **전필 후보 풀** 조회
- 목표 학점에 맞춰 **충돌 없는 추천 조합** 생성
- 결과를 **텍스트(ASCII/Markdown) 시간표**로 출력 (디스코드/메모 복붙용)

## 🧭 한성대 관련 작업 지침(중요)
이 스킬을 설치하면 **기본 동작 원칙**이 아래처럼 고정됩니다: 한성대 데이터가 필요할 때는 **아래 2가지 중 하나로만** 근거를 잡습니다.

1) **한성대 홈페이지(hansung.ac.kr) 크롤링**
- 대상: 공지/모집/장학/행사/학사일정 등 공개 정보
- 예: `/home/ubuntu/.openclaw/workspace/scripts/hsu_notice_fetch.py` 같은 방식으로 스냅샷을 만들고, 링크를 근거로 추천/요약

2) **종정시(info.hansung.ac.kr) 로그인 스킬 사용(쿠키 기반)**
- 대상: 성적/이수/수강내역/개설시간표 등 개인 계정 기반 정보
- 원칙: read-only, 쿠키 만료 시 `~/.openclaw/.env`로 자동 갱신을 1회 시도

> 즉, “추측”으로 말하지 않고 **홈페이지 원문 링크** 또는 **종정시 조회 결과**를 레퍼런스로 삼습니다.

### 기본 엔트리포인트(권장)
아래 라우터 스크립트를 쓰면, 작업이 자동으로 **홈페이지 크롤링 vs 종정시 조회**로 분기됩니다.

```bash
bash skills/hansung-info/openclaw/hsu_ref.sh --help

# 공개정보(공지/장학 등)
bash skills/hansung-info/openclaw/hsu_ref.sh notice
bash skills/hansung-info/openclaw/hsu_ref.sh scholarship --max 10

# 개인정보(성적/수강내역 등)
bash skills/hansung-info/openclaw/hsu_ref.sh grade-summary
bash skills/hansung-info/openclaw/hsu_ref.sh semester-courses --term 20261
```

> 원칙: **read-only**. 수강신청/변경 같은 write 작업은 하지 않습니다.

---

## 설치(레포 URL만으로 끝내기)

```bash
cd ~/.openclaw/workspace/skills
# 폴더명을 hansung-info 로 맞추면 OpenClaw가 스킬로 바로 잡습니다.
git clone https://github.com/yeounhyeok/hansung-info-course-recommender.git hansung-info
```

> 이제 `~/.openclaw/workspace/skills/hansung-info/SKILL.md`만 보고 그대로 따라가면 세팅됩니다.

## 설치 → 세팅 → 사용(가장 짧은 루트)

### 1) 설치(venv)

스킬 폴더에서 venv를 만들고 의존성을 설치합니다. **처음 설치한 직후부터 바로 실행 가능**하도록 이 단계는 필수입니다.

```bash
cd ~/.openclaw/workspace/skills/hansung-info
bash openclaw/setup.sh
```

### 2) 자격증명 세팅

`~/.openclaw/.env`에 아래 2개를 넣습니다.

```bash
HANSUNG_INFO_ID=학번
HANSUNG_INFO_PASSWORD='비밀번호'
```

권한 잠그기:

```bash
chmod 600 ~/.openclaw/.env
```

### 3) 로그인 쿠키 갱신

**처음 실행 전 1회** 쿠키를 만들고 진행합니다.

- ✅ 이제 주요 스크립트들은 쿠키가 만료되면 **~/.openclaw/.env**의 `HANSUNG_INFO_ID/PASSWORD`를 읽어서 **자동으로 1회 갱신을 시도**합니다.
- 그래도 실패하면(자격증명 누락/변경 등) 아래 스크립트로 수동 갱신하세요.

```bash
cd ~/.openclaw/workspace/skills/hansung-info
bash openclaw/login_refresh.sh
```

저장 위치:
- `~/.openclaw/workspace/secrets/hansung_info_storage.json`

### 4) 추천 + 시간표 출력(텍스트)

```bash
bash openclaw/recommend_this_term.sh \
  --term 20261 --major Y030 --target 18 \
  --year 2 --max-days 3 \
  --format md --fill-ge
```

- `--fill-ge`: 남는 학점을 교양으로 채워서 target을 맞춥니다.
- `--allow-other-years`: 타 학년 전공까지 섞어 18학점 꽉 채우고 싶을 때.

---

## 출력 예시(복붙용 텍스트 시간표)

```
[20261 / Y030] 18학점 시간표 (등교: 월·수·목)

월
  10:30-12:00  오픈소스 HW (노광현)  미래관B107  [월2M~3M]
  13:30-15:00  웹프로그래밍 (지준)   공학관407   [월5M~6M]

수
  13:30-15:00  디지털 논리 및 회로 (정성훈)  상상관705  [수5M~6M]
  15:00-16:30  C프로그래밍 (정성훈)          상상관305  [수7~8]
  17:00-18:30  인공지능 수학 (조혜경)        상상관306  [수8M~9M]

목
  16:30-18:00  디지털마케팅의 이해와 활용(캡스톤디자인) (이승준)  상상관703  [목8M~9M]
```

---

## 개별 스크립트(고급)

> 아래는 디버깅/확장용입니다. 평소엔 `openclaw/*.sh`만 써도 됩니다.

```bash
python3 scripts/login_refresh.py
python3 scripts/timetable_offerings.py --term 20261 --major Y030
python3 scripts/major_curriculum.py --term 20261 --major Y030
python3 scripts/recommend_this_term.py --term 20261 --major Y030 --target 18 --year 2 --format md

# ✅ 수강과목 리스트(학기별) — "내 종정시" 기준으로 과거 학기 과목을 뽑을 때
python3 scripts/semester_courses.py --term 20252

python3 scripts/roadmap_generator.py --start 20261 --grad 20282 --major Y030 --required-credits 21
```

## 시간 매핑 규칙(충돌검사/표시 핵심)
- 시간표는 **30분 그리드**로 렌더링합니다.
- 월/수/목은 75분 패턴 때문에 종정시 표기(`n/nM`)를 30분 경계로 스냅한 매핑 테이블을 사용합니다.
- 따라서 **같은 `n/nM`라도 요일에 따라 실제 시간이 달라질 수 있고**, 충돌검사도 이 규칙을 그대로 따릅니다.

## 학기별 수강과목 리스트(내 종정시 기반)
- 누적 성적 화면(`total_grade.jsp`)에서 **학기 카드(YYYY 학년도 N 학기)** 를 파싱해 그 학기 수강과목을 뽑습니다.
- 일부 학기는 학적 상태(휴학/군휴학 등) 때문에 화면에 카드가 없을 수 있습니다. 그 경우 "해당 학기 데이터 없음"으로 반환합니다.

## References
- `references/endpoints.md`
