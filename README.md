# Hansung Info Course Recommender

한성대 종정시(info.hansung.ac.kr)에서 **개설 과목을 조회(READ-ONLY)** 해서,
**시간표 충돌 없이** 목표 학점에 맞춘 조합을 추천하고 결과를 **복붙용 텍스트 시간표**로 출력합니다.

- 원칙: **read-only** (수강신청/변경 같은 write 작업 없음)
- 설치/세팅/사용법: `hansung-info/SKILL.md`

## 주요 기능
- 전공(Y030 등) 개설과목 기반 추천(전필/전기/전선 우선)
- 교양(L11*) 포함 채우기 옵션
- **이미 이수한 과목 자동 제외**: `--exclude-taken`
- **원치 않는 과목 제외**: `--exclude-code`, `--exclude-name`
- 출력: Markdown / ASCII / **요일별(day-wise) 리스트**(`--format day`)

## 설치

OpenClaw 워크스페이스 기준으로, 아래처럼 **폴더명을 `hansung-info`로 클론**하면 바로 스킬로 인식됩니다.

```bash
cd ~/.openclaw/workspace/skills
git clone https://github.com/yeounhyeok/hansung-info-course-recommender.git hansung-info
# 이후 세팅/사용은 hansung-info/SKILL.md 그대로 따라가면 됩니다.
```

또는(운영 방식): OpenClaw에게 그냥 이렇게 말해도 됩니다.

> "https://github.com/yeounhyeok/hansung-info-course-recommender 이 레포 클론해서 스킬로 만들어줘"

그러면 OpenClaw가 `skills/`에 클론/배치까지 해주고, 이후는 SKILL.md대로 따라서 세팅하면 끝입니다.

## 파이프라인
1) 로그인 쿠키 갱신 → `secrets/hansung_info_storage.json`
2) 종정시 개설과목 조회(전공/교양)
3) 충돌 제거 + 우선순위/제약 기반으로 조합 선택
4) 텍스트 시간표 출력

## 출력 예시(요일별 / `--format day`)

```
월
  - 10:30~12:00  오픈소스 HW (3학점) | 미래관B107 | 노광현

수
  - 13:30~15:00  디지털 논리 및 회로 (3학점) | 상상관705 | 정성훈
  - 15:00~16:30  C프로그래밍 (3학점) | 상상관305 | 정성훈
```

## 주의
- 계정/쿠키는 로컬에만 저장하고 커밋하지 마세요.
- 과도한 호출은 지양하고 본인 계정으로만 사용하세요.

## License
- MIT (see `LICENSE`)
