# Hansung Info Course Recommender (한성대 종정시 교과목 추천 시스템)

이 프로젝트는 **OpenClaw만 사용해서 만든 테스트용 프로젝트**입니다.
처음 아이디어부터 현재 형태(스킬/스크립트/자동화)까지 정리하는 데 **약 2시간** 정도 걸렸습니다.

## 공개/사용에 대한 안내(중요)
- 이 레포는 **누구나 바로 실행**할 수 있도록 공개합니다.
- 다만 학교 시스템/정책(이용약관)이나 트래픽 정책에 따라 **차단/변경**이 발생할 수 있습니다.
- 과도한 호출은 지양하시고, 본인 계정으로만 사용하세요.
- 문제가 생기면 레포는 **즉시 비공개 전환 또는 삭제**할 수 있습니다.

한성대학교 종합정보시스템(종정시, info.hansung.ac.kr)에서 **조회 가능한 범위(개설과목/교육과정)** 를 기반으로
- 이번 학기 개설 과목 조회
- 전공필수(전필) 후보(교육과정) 수집
- **시간표 충돌 방지 교과목 추천 + ASCII 시간표 출력**
- **전공필수는 체크리스트가 아니라 ‘학점 기준’** 로드맵 초안 생성
을 자동화하는 스크립트 묶음입니다.

> ⚠️ 주의: 계정/쿠키는 로컬 `secrets/`에만 저장되며 레포에는 커밋하지 않습니다.
> 이 프로젝트는 **조회/추천/플래닝(read-only)** 용도입니다. (수강신청 등 write 작업 없음)

---

## 기술
- Python 3.10+ 기반의 스크립트형 자동화입니다.
- HTTP 클라이언트로 `httpx`를 사용해 종정시 AUIGrid 엔드포인트를 호출합니다.
- 출력은 사람이 읽기 좋은 텍스트(Markdown/ASCII) 중심으로 설계했습니다.
- 현재는 OpenClaw **스킬 형태로 운영**하며, 외부 패키징/설치형 CLI 승격은 보류 상태입니다.

---

## 기능
- 로그인 세션(쿠키) 갱신 자동화
- 이번 학기 **실제 개설 과목**(시간표/수업계획서 조회) 수집
- 교육과정(카탈로그) 기반으로 전공필수(전필) 후보 과목 풀 수집
- 시간표 충돌을 피하면서 목표 학점(예: 18학점)에 맞춘 교과목 추천
- 최종 시간표를 **ASCII 도식**으로 출력
- 전공필수는 “체크리스트”가 아니라 **학점 기준**으로 로드맵 초안을 생성

---

## 과정
- 1) 종정시 로그인 후 쿠키를 로컬에 저장합니다.
- 2) 개설 과목(시간표) 데이터를 가져와 과목 목록을 정규화합니다.
- 3) 교육과정(카탈로그)에서 전필 후보 풀을 스캔해 기준 데이터를 확보합니다.
- 4) 점수(전필/전기/전선 우선순위) + 충돌 검사(요일/교시 범위)로 추천 조합을 고릅니다.
- 5) 결과를 리스트/ASCII 시간표/로드맵 텍스트로 출력합니다.

---

## 실행 예시

### 0) 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1) 환경변수 설정

`~/.openclaw/.env` 또는 쉘 환경변수로 아래를 준비합니다.

- `HANSUNG_INFO_ID`
- `HANSUNG_INFO_PASSWORD`

### 2) 실행

```bash
# (1) 로그인 쿠키 갱신
set -a && source ~/.openclaw/.env && set +a
python3 hansung-info/scripts/login_refresh.py

# (2) 이번 학기 교과목 추천 + ASCII 시간표
python3 hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18

# (3) 전공필수 학점 기준 로드맵
python3 hansung-info/scripts/roadmap_generator.py --start 20261 --grad 20282 --major Y030 --required-credits 21
```

## Requirements
- Python 3.10+
- `httpx` (see `requirements.txt`)

## License
- MIT (see `LICENSE`)
