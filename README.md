# Hansung Info Major Recommender (한성대 종정시 전공 추천 시스템)

한성대학교 종합정보시스템(종정시, info.hansung.ac.kr)에서 **조회 가능한 범위(개설과목/교육과정)** 를 기반으로
- 이번 학기 개설 과목 조회
- 전공필수(전필) 후보(교육과정) 수집
- **시간표 충돌 방지 추천 + ASCII 시간표 출력**
- **전공필수는 체크리스트가 아니라 ‘학점 기준’** 로드맵 초안 생성
을 자동화하는 스크립트 묶음입니다.

## ⚠️ 주의
- 계정/쿠키는 `secrets/` 로컬 파일에 저장되며 **레포에는 커밋하지 않습니다**.
- 이 프로젝트는 **조회/추천/플래닝(read-only)** 용도입니다. (수강신청 등 write 작업 없음)

## 실행 예시

```bash
# (1) 로그인 쿠키 갱신
set -a && source ~/.openclaw/.env && set +a
python3 hansung-info/scripts/login_refresh.py

# (2) 이번 학기 추천 + ASCII 시간표
python3 hansung-info/scripts/recommend_this_term.py --term 20261 --major Y030 --target 18

# (3) 전공필수 학점 기준 로드맵
python3 hansung-info/scripts/roadmap_generator.py --start 20261 --grad 20282 --major Y030 --required-credits 21
```

## Requirements
- Python 3.10+
- `httpx`
