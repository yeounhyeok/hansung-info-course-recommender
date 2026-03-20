# Hansung Info Course Recommender (OpenClaw skill)

한성대학교 종합정보시스템(종정시, info.hansung.ac.kr)에서 **조회 가능한 범위(개설과목/교육과정)** 를 기반으로,
- 이번 학기 개설 과목 조회
- 전공필수(전필) 후보(교육과정) 수집
- **시간표 충돌 방지 기반 교과목 추천**
- 결과를 **텍스트(ASCII/Markdown) 시간표로 출력**
하는 **OpenClaw 스킬용 스크립트 묶음**입니다.

> 이 프로젝트는 **read-only** 자동화입니다. (수강신청/변경 등 write 작업은 하지 않습니다)

## 주의(중요)
- 계정/쿠키는 로컬 `~/.openclaw/.env` 및 OpenClaw workspace의 `secrets/`에만 저장하세요.
- 과도한 호출은 지양하고 **본인 계정으로만** 사용하세요.
- 학교 시스템/정책 변경으로 동작이 깨질 수 있습니다.

---

## 설치(OpenClaw 스킬로 쓰는 기준)

### 0) 레포 클론

```bash
cd ~/.openclaw/workspace/skills
git clone https://github.com/yeounhyeok/hansung-info-course-recommender.git
```

### 1) 스킬 디렉토리로 배치

OpenClaw가 읽는 스킬 경로는 `~/.openclaw/workspace/skills/<skill-name>/SKILL.md` 형태입니다.

가장 간단한 방법은, 이 레포의 `hansung-info/`를 스킬 폴더로 복사(또는 심링크)하는 겁니다.

```bash
cd ~/.openclaw/workspace/skills
# 기존 hansung-info 스킬이 있으면 백업(선택)
mv hansung-info hansung-info.bak-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true

# 스킬 설치(복사)
cp -a hansung-info-course-recommender/hansung-info ./hansung-info

# (선택) 고정 루틴 래퍼도 같이 복사
cp -a hansung-info-course-recommender/openclaw ./hansung-info/
cp -a hansung-info-course-recommender/requirements.txt ./hansung-info/
```

### 2) 자격증명(환경변수) 세팅

`~/.openclaw/.env`에 아래 2개를 넣습니다.

```bash
HANSUNG_INFO_ID=학번
HANSUNG_INFO_PASSWORD='비밀번호'
```

권한 잠그기:

```bash
chmod 600 ~/.openclaw/.env
```

### 3) 의존성 설치(venv)

```bash
cd ~/.openclaw/workspace/skills/hansung-info
bash openclaw/setup.sh
```

---

## 사용법(스킬 루틴)

### 1) 로그인 쿠키 갱신

```bash
cd ~/.openclaw/workspace/skills/hansung-info
bash openclaw/login_refresh.sh
```

### 2) 이번 학기 추천 + 시간표 출력(ASCII/Markdown)

```bash
bash openclaw/recommend_this_term.sh --term 20261 --major Y030 --target 18 --year 2 --max-days 3 --format md --fill-ge
```

- `--term`: 학기 (예: 20261)
- `--major`: 전공 코드 (예: AI응용학과 `Y030`)
- `--target`: 목표 학점
- `--year`: 우선 학년
- `--max-days`: 등교 요일 수 제한
- `--fill-ge`: 남는 학점을 교양으로 채우기

---

## 출력 예시(텍스트 시간표)

실제 출력은 아래처럼 **바로 복붙 가능한 텍스트**가 목표입니다.

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

## Requirements
- Python 3.10+
- dependencies: `requirements.txt`

## License
- MIT (see `LICENSE`)
