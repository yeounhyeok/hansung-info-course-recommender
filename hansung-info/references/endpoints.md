# Hansung Info endpoints (discovered)

## Login

- GET login page: `https://info.hansung.ac.kr/index.jsp`
- POST login:
  - `https://info.hansung.ac.kr/servlet/s_gong.gong_login_ssl`
  - form fields: `id`, `passwd`, `changePass`, `return_url`

## Main student portal

- Main: `https://info.hansung.ac.kr/jsp_21/index.jsp`

## Grade / cumulative

- Cumulative grade summary:
  - `https://info.hansung.ac.kr/jsp_21/student/grade/total_grade.jsp?viewMode=oc`

## Academic record (학적조회)

- Container page (tabs load partial JSP via jQuery `#ifhakjuk.load(page)`):
  - `https://info.hansung.ac.kr/jsp_21/student/hakjuk/collage_register_1_rwd.jsp?viewMode=oc`

- Example partial pages (require correct session + referer):
  - `collage_register_hakjuk_rwd.jsp`
  - `collage_register_history_rwd.jsp`
  - `collage_register_score.jsp`
  - `collage_register_fee_rwd.jsp`
  - `collage_register_jol_rwd.jsp`

## Timetable / offerings API (시간표 및 수업계획서조회)

The timetable page uses AUIGrid and loads XML via:

- `https://info.hansung.ac.kr/jsp_21/student/kyomu/siganpyo_aui_data.jsp?gubun=yearhakgilist`
- `https://info.hansung.ac.kr/jsp_21/student/kyomu/siganpyo_aui_data.jsp?gubun=jungonglist` with POST `syearhakgi`
- `https://info.hansung.ac.kr/jsp_21/student/kyomu/siganpyo_aui_data.jsp` with POST:
  - `gubun=history`
  - `syearhakgi`
  - `sjungong`

Response is XML `<rows><row>...` containing:
- `kwamokcode`, `kwamokname`, `isugubun`, `hakjum`, `haknean`, `prof`, `classroom`, ...

## Major curriculum API (교육과정조회)

The curriculum page uses AUIGrid and loads XML via:

- `https://info.hansung.ac.kr/jsp_21/student/kyomu/kyoyukgwajung_data_aui.jsp?gubun=yearhakgilist`
- `https://info.hansung.ac.kr/jsp_21/student/kyomu/kyoyukgwajung_data_aui.jsp?gubun=jungonglist` with POST `syearhakgi`
- `https://info.hansung.ac.kr/jsp_21/student/kyomu/kyoyukgwajung_data_aui.jsp` with POST:
  - `syearhakgi` (e.g. 20261)
  - `sjungong` (AI응용학과 = `Y030`)
  - and query param: `gubun=history`

Response is XML `<rows><row>...` containing:
- `kwamokcode`, `kwamokname`, `isugubun`, `hakjum`, `haknean`, ...

## Dept graduation requirements (public site)

- AI응용학과 졸업요건 page (public):
  - `https://www.hansung.ac.kr/CreCon/2781/subview.do`
