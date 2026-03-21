#!/usr/bin/env bash
set -euo pipefail

# Hansung reference router.
# Default policy: never guess. Always ground answers in either
# (A) hansung.ac.kr public pages crawl, or
# (B) info.hansung.ac.kr (종정시) cookie-authenticated reads.

WS="/home/ubuntu/.openclaw/workspace"
SKILL_DIR="${WS}/skills/hansung-info"

usage() {
  cat <<'EOF'
Usage:
  bash skills/hansung-info/openclaw/hsu_ref.sh <command> [args]

Commands (홈페이지 크롤링 / 공개정보):
  notice                         # 학교+학과 공지 스냅샷 갱신 + 새 공지 출력
  scholarship [--max N]           # 공지 스냅샷에서 장학/등록금/근로 키워드 후보 출력
  scholarship --pw [--max N]      # (권장) Playwright로 게시판 검색을 써서 '장학' 관련 최신 공지 탐색
  scholarship --pw --deep [--max N] # Playwright 검색 결과를 본문 딥 추출까지

Commands (종정시 / 개인정보, read-only):
  grade-summary         # GPA/백분위/학점 요약
  semester-courses --term 20261  # 해당 학기 수강과목 리스트
  offerings --term 20261 --major Y030  # 개설과목(시간표) 목록

Notes:
- 종정시 쿠키가 만료되면 ~/.openclaw/.env(HANSUNG_INFO_ID/PASSWORD)를 읽어 자동 갱신을 1회 시도합니다.
EOF
}

cmd="${1:-}"
shift || true

case "$cmd" in
  notice)
    python3 "${WS}/scripts/hsu_notice_fetch.py"
    ;;
  scholarship)
    # ensure snapshot exists/updated
    python3 "${WS}/scripts/hsu_notice_fetch.py" >/dev/null || true

    if [[ "${1:-}" == "--pw" ]]; then
      shift || true
      python3 "${WS}/scripts/hsu_scholarship_search_pw.py" "$@"
      exit 0
    fi

    if [[ "${1:-}" == "--deep" ]]; then
      shift || true
      python3 "${WS}/scripts/hsu_notice_deep_extract.py" "$@"
    else
      python3 "${WS}/scripts/hsu_scholarship_recommend.py" "$@"
    fi
    ;;
  grade-summary)
    python3 "${SKILL_DIR}/scripts/grade_summary.py"
    ;;
  semester-courses)
    python3 "${SKILL_DIR}/scripts/semester_courses.py" "$@"
    ;;
  offerings)
    python3 "${SKILL_DIR}/scripts/timetable_offerings.py" "$@"
    ;;
  -h|--help|help|"" )
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    echo >&2
    usage >&2
    exit 2
    ;;
esac
