# sheet-guard — 표를 LLM·엑셀에 넣기 전에 읽는다

공공데이터 CSV나 엑셀을 받아서 그대로 붙여 넣으면 조용히 틀린다. 한글이 깨지고, 소계 행이
데이터에 섞여 합계가 두 배가 되고, 우편번호 `00123`이 `123`이 되고, `2024.1.5`와
`2024-01-05`가 섞여 정렬이 글자 순서가 된다. **sheet-guard**는 그 표를 쓰기 전에 읽고,
어디가 어떻게 깨질지 행 번호와 함께 보여 준 뒤, 원본을 건드리지 않고 정리본·바뀐 곳
기록·격리 파일을 새로 만든다.

- MCP 서버(stdio) + CLI, 툴 9개, 규칙 35종, pytest **324 passed**
- CSV(CP949·EUC-KR·UTF-8·UTF-16·BOM)와 `.xlsx`(병합 칸 포함)
- 정리 전/후 대조로 **값이 사라진 칸 0** 을 확인하고 넘긴다

## 조합한 공개 소스 2개

| 원본 | 라이선스 | 규모 | 가져온 것 | 가져오지 않은 것 |
|---|---|---|---|---|
| [haris-musa/excel-mcp-server](https://github.com/haris-musa/excel-mcp-server) (Excel MCP Server) | **MIT** | ★4,322 · 마지막 푸시 2026-11-23 | 통합문서를 **맥락으로** 다루는 툴 설계 — 읽기와 쓰기를 나누고, 셀·범위 단위로 지목하며, 엑셀 없이도 값과 수식을 읽는다는 태도 | openpyxl 래퍼 코드, 수식 엔진(479 함수), 차트·피벗·슬라이서 기능 |
| [microsoft/markitdown](https://github.com/microsoft/markitdown) (MarkItDown) | **MIT** | ★198,099 · 마지막 푸시 2026-11-07 | "도구가 먹기 좋은 구조 보존 마크다운" — 표를 파이프 표로 옮기고, 형식이 제각각인 입력을 거부하지 않고 받아들이는 태도 | 변환기 코드, PDF·DOCX·이미지·오디오 변환, LLM 캡셔닝 |

두 원본의 코드를 복사하지 않았다. **설계와 태도만** 가져와 새로 썼다.

* Excel MCP Server → 표를 **툴의 맥락**으로 두고, 읽기(`read_table`·`profile_columns`)와
  쓰기(`apply_plan`)를 분리했다. 원본이 "엑셀 없이도 값과 수식을 읽는다"는 문제를
  푼 것처럼, 여기서는 "엑셀 없이도 이 표가 무엇인지 읽는다"를 푼다.
* MarkItDown → 표를 **구조가 남는 텍스트**(마크다운)로 넘긴다. 원본이 PDF·DOCX·CSV를
  모두 받아들이듯, 여기서는 CP949·탭·따옴표 사고·2줄 머리글을 거부하지 않고 받아들인 뒤
  무엇이 이상했는지 말한다.

## 무엇을 잡는가 (규칙 35종)

**구조** — 잘못 읽으면 뒤가 전부 틀어진다
`cp949-encoding` `bom-prefix` `line-ending-mixed` `preamble-rows`(제목·단위 줄)
`multi-row-header`(묶음 머리글) `ragged-row`(따옴표 없는 쉼표로 밀린 행) `stray-quote`
`duplicate-header` `unnamed-column` `no-rows`

**행 역할** — 값이 아니라 역할을 먼저 본다
`subtotal-row`(데이터 사이 소계·합계 = 치명) `trailing-total` `section-row`
`footnote-row` `blank-row`

**값** — 읽히지만 합계·정렬·조인에서 깨지는 것
`leading-zero-risk`(0이 사라진 우편번호·코드) `leading-zero-kept`
`phone-inconsistent` `date-format-mixed` `date-invalid` `thousands-separator`
`unit-in-cell`(12.5㎡) `percent-as-text` `accounting-negative`((1,234))
`fullwidth-digit`(１２３) `whitespace-padding` `mixed-type-column`
`text-in-numeric-column`(거의 숫자인 열의 글자 몇 개) `id-in-text`(이름 (1100000000))
`duplicate-rows` `duplicate-key` `empty-column` `constant-column`

**엑셀** — `merged-cell-gap`(병합 칸의 빈 자리) `formula-missing`(계산값 없는 수식)

## 툴 9개

| 툴 | 하는 일 |
|---|---|
| `read_table(path, sheet)` | 인코딩·머리글·열 요약 + `ref` (이후 호출은 ref로) |
| `profile_columns(ref)` | 열마다 종류·채움률·서로 다른 값·날짜 표기·자릿수·범위 |
| `find_problems(ref, key, severity)` | 규칙 위반 목록 — 행 참조·예시·고치기 종류 |
| `clean_plan(ref, only)` | 고칠 순서·확신도·이유 (쓰지는 않음) |
| `apply_plan(ref, out, changelog)` | 정리본 CSV + 바뀐 곳 기록 + 격리 파일 (원본 불변) |
| `to_markdown(ref, max_rows, clean)` | LLM에 넣기 좋은 마크다운 표 |
| `compare_tables(ref_a, ref_b, key)` | 행 참조(또는 키)로 짝지어 없어진 행·바뀐 칸·사라진 값 |
| `rule_catalog(rule)` | 규칙 목록 / 규칙 하나의 설명 |
| `overview()` | 이 서버가 무엇을 하고 무엇을 판정하지 않는지 |

CLI도 같은 일을 한다.

```bash
sheet-guard read examples/raw_population.csv      # 구조·열 요약
sheet-guard problems examples/raw_population.csv  # 위반 목록 (치명 있으면 exit 2)
sheet-guard plan examples/raw_population.csv      # 고칠 순서
sheet-guard clean examples/raw_population.csv --out out/clean.csv
sheet-guard md examples/raw_population.csv --clean
sheet-guard compare 원본.csv out/clean.csv --key 시군구
sheet-guard rules leading-zero-risk
```

## 실측 (2026-11-24)

`python3 tools/corpus_probe.py` — 실제 공개 CSV 2개 + 저장소 예제. 파일은 내려받아 분석만 하고
저장소에 넣지 않는다.

| 파일 | 크기 | 표 | 인코딩 | 읽기 | 규칙 | 적용 | 치명 | 주의 | 바뀐 칸 | 값 손실 |
|---|---|---|---|---|---|---|---|---|---|---|
| 행정안전부 주민등록 **연령별 인구**(2026-01~06) | 204,143 B | 298×79 (23,542칸) | CP949(0.75) | 144ms | 459ms | 217ms | **0** | 79 | 19,760 | **0** |
| 행정안전부 주민등록 **지역별 생활인구**(2026-01~03) | 15,296 B | 267×7 (1,869칸) | UTF-8 BOM(0.95) | 32ms | 34ms | 0ms | **0** | 0 | 0 | **0** |
| `examples/raw_population.csv` (오염 표시용 예제) | 3,935 B | 48×9 (486칸) | CP949(0.81) | 8ms | 9ms | 3ms | 2 | 9 | 157 | **0** |

* 연령별 인구 파일은 첫 열이 `서울특별시  (1100000000)` 처럼 **이름+코드**였고, 78개 인구 열이
  전부 `"9,299,701"` 천 단위 쉼표였다. `id-in-text` 298칸·`thousands-separator` 78열을 잡았고,
  정리 후 **19,760칸**이 숫자로 바뀌었지만 **값이 사라진 칸은 0**이었다.
* 생활인구 파일은 깨끗했다(참고 1건: BOM). **막는 문제는 하나도 만들지 않았다** — 거짓 양성 0.
* 예제 파일: 48행 중 소계 3·각주 2·빈 줄 1을 빼고, 완전 중복 1행과 칸이 밀린 1행을 격리해
  **46행**이 남았다. `㎡` 47칸은 숫자로 바꾸면서 `면적_단위` 열로 옮겨 단위를 잃지 않았다.

### 예제 하나를 끝까지

```
$ sheet-guard clean examples/raw_population.csv --out out/clean.csv
🧹 정리 계획 — 10단계 · 바뀌는 칸 210개
   a1 공백·전각 문자 정리 '시군구' 열 · 2개          (확신 1.00)
   a4 행 빼기          행 6개(r30, r45, r55, r52…)    (확신 1.00)
   a5 칸이 밀린 행 격리 행 1개(r38)                    (확신 1.00)
   a6 숫자로 바꾸기    '인구수' 열 · 50개              (확신 0.95)
   a8 숫자로 바꾸기    '면적' 열 · 47개 ↳ 단위 ㎡는 '면적_단위' 열로
   a9 날짜를 YYYY-MM-DD로 '기준일' 열 · 50개          (확신 0.90)
   a10 중복 행 합치기   완전히 같은 행 · 1개
사람이 봐야 함(자동으로 고치지 않음): text-in-numeric-column

✅ 적용 완료 — 값 157칸 · 뺀 행 8개 · 격리 1행 · 새 열 면적_단위
🔍 정리 전 48행 → 정리 후 46행 · 짝지은 행 46 (95.8% 유지)
   판정: 행 2개가 빠졌습니다(계획대로면 정상)
   ⚠️ 값이 사라진 칸 0개
```

## 안전 규칙

1. **원본을 고치지 않는다.** `apply_plan`은 `out` 경로에 새 파일을 쓴다.
2. **바꾼 곳을 전부 남긴다.** `*.changes.csv`에 `action,row,column,before,after`.
3. **단위를 버리지 않는다.** `12.5㎡` → `12.5` + `면적_단위=㎡` 열.
4. **칸이 밀린 행은 격리한다.** 잘라 버리면 값이 조용히 사라진다 → `*.ragged.csv`.
5. **확신 없는 변환은 표시한다.** 앞자리 0 복원(자릿수 추정)은 확신 0.55 + ⚠️확인.
6. **적용 뒤 대조한다.** `compare_tables`가 값이 사라진 칸을 세고, 있으면 "멈추고 확인"이라고 말한다.

## 판정하지 않는 것 (한계)

* 값의 **의미**와 통계적 이상값 — 100억 원짜리 매출도 숫자면 숫자다.
* 엑셀 **수식의 재계산** — 파일에 저장된 계산값만 읽는다(없으면 `formula-missing`으로 알린다).
* 셀 **서식**(색·굵기)·차트·피벗·틀 고정.
* **병합 칸의 의도** — 병합을 풀어 채우는 것은 제안이고, 채우기 전/후를 남긴다.
* **날짜 해석의 함정** — `03/04/2024`처럼 월·일이 뒤바뀔 수 있는 표기는 날짜로 읽지 않는다.
* `.xls`(구형 바이너리)는 지원하지 않는다 — `.xlsx`나 CSV로 저장해야 한다.
* 인코딩 **후보가 둘 다 말이 될 때**의 확신도는 낮게 표시된다(예: CP949 0.75). 글자가 깨져
  보이면 `read_table`의 `인코딩` 줄과 `profile_columns`의 예시를 먼저 보라.

## 설치·실행

```bash
pip install -e ".[xlsx,dev]"
python -m pytest -q            # 324 passed
python -m sheet_guard.cli read examples/raw_population.csv
```

MCP 클라이언트 설정(stdio):

```json
{"mcpServers": {"sheet-guard": {
  "command": "python", "args": ["-m", "sheet_guard.server"],
  "env": {"SHEET_GUARD_ROOT": "/Users/me/data"}}}}
```

MCP 프로토콜 버전은 `mcp` 파이썬 SDK를 따른다(`mcp>=2.3,<3`). 서버는 `mcp.run()`으로
stdio에서 돈다(테스트에서 in-memory와 **stdio 서브프로세스** 양쪽으로 확인).

## 구조

```
sheet_guard/
  decode.py    바이트 → 글자 (CP949·EUC-KR·UTF-16·BOM, 글자 모양 점수)
  csvlex.py    구분자 추정, 따옴표·줄바꿈, 어긴 자리 표시
  table.py     머리글 블록·앞머리 줄·병합 칸, CSV·XLSX 로더
  classify.py  행 역할(데이터/소계/구역/각주/빈 줄)
  types.py     칸 값 종류(날짜·전화·코드·단위·전각), 열 통계
  rules.py     규칙 35종 → Finding(심각도·행 참조·고치기)
  plan.py      고칠 순서·확신도 (값을 지어내지 않음)
  apply.py     적용 + 바뀐 곳 기록 + 격리 + 단위 열
  compare.py   정리 전후 대조(행 참조/키/순서)
  markdown.py  LLM용 마크다운 표
  store.py     세션 ref
  server.py    MCP 9툴 · cli.py CLI
examples/      오염을 표시한 예제 + 생성 스크립트
tools/         corpus_probe.py (실제 공개 데이터 실측)
reels/         릴스 생성기(영상·커버·오디오)
tests/         324 tests
```

## 라이선스

MIT (이 저장소). 원본 두 곳도 MIT이며, 코드를 복사하지 않고 설계만 참고했다.
