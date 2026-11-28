# chart-guard — 차트를 올리기 전에, 축이 숫자를 왜곡하는지 잰다

**공개 MCP/스킬 2개를 섞어 만든 새 MCP 서버 (Day 12).**
차트 스펙(Vega-Lite · Chart.js · guard JSON)을 읽어, **축 하한이 만드는 화면 비율**을 실제 값 비율과
맞대어 배수로 말하고, **규칙 41종**으로 형식·색·글을 검사한 뒤, 고친 스펙과 **125자 대체 텍스트 + 데이터 표**를 만듭니다.

```
y축 하한 180 · 세종 210 → 서울 1,240 이 화면에서 35.33배, 실제 5.90배 (과장 6.0배)
```

> 읽는 것은 스펙의 선언이다. 차트 이미지의 픽셀은 읽지 않는다 — 대신 픽셀이 어떻게 될지를 계산하고,
> 그 계산이 matplotlib 렌더와 같은 비율을 말하는지 직접 재서 확인한다(`tools/render_check.py`).

---

## 원본 2개

| 원본 | 라이선스 | 규모 (2026-11-28 확인) | 무엇을 가져왔나 |
|---|---|---|---|
| [antvis/mcp-server-chart](https://github.com/antvis/mcp-server-chart) | **MIT** | ★ 4,424 · 마지막 푸시 2026-08-27 · 차트 툴 **27개** | 차트를 **스펙(스키마)으로** 다루는 태도: 종류마다 입력 스키마를 정하고, `category·value·group` 처럼 값의 역할을 고정하며, `dual-axes` 처럼 위험한 형식도 툴 하나로 제공한다는 사실. 그 27개가 **그리는** 데 쓰는 자리 옆에 **재는** 자리를 하나 둔다. |
| [holtzy/dataviz-skills 의 `roast-my-chart`](https://github.com/holtzy/dataviz-skills/tree/main/roast-my-chart) | **MIT** | ★ 199 · 마지막 푸시 2026-11-10 · 카베아트 **61종 / 8장** | 검사의 태도: **모든 항목을 순서대로** 보고, 항목마다 `Look for / Why / Fix / Fine when`(문제가 아닌 때)을 붙이고, **"확인할 수 없었던 것"** 을 따로 적고, 심각도(🔴 왜곡 → 🟠 읽기 어려움 → 🟡 다듬기)로 줄을 세운다. |

원본 코드는 **한 줄도 복사하지 않았습니다.** 위 표의 두 번째 열은 설계 아이디어이고,
규칙 41종의 문장·판정식·계산은 이 저장소에서 새로 썼습니다(`chart_guard/rules.py`).
`roast-my-chart` 는 61종 카베아트를 **읽고 판단하는** 스킬이지만, 이 도구는 **스펙의 숫자로 계산**합니다 —
`Fine when`(예외) 개념만 가져와 규칙마다 `fine_when` 필드로 옮겼습니다.

### 원본과 다른 점 (왜 새로 만들었나)

- 원본 1은 차트를 **그립니다**(27개 툴, 0개가 "이 그림이 정직한가"를 묻습니다). 원본 2는 사람이/모델이 **보고** 평합니다(이미지·코드 대상, 계산 없음).
- 이 도구는 **계산**합니다: 축 하한에서 나오는 화면 길이비, 원 조각의 각도, 로그축의 거리, 크기 인코딩의 넓이,
  색 대비·색각 이상 거리, 라벨 자리. 그래서 "축이 잘렸다"가 아니라 **"4.00배로 보인다, 실제 1.12배다"** 라고 말합니다.
- 그리고 **고친 스펙**을 같은 형식으로 돌려줍니다 — 지적에서 끝나지 않고 다음 그림을 만듭니다.

---

## 툴 10개 · 규칙 41종 (원본 27 + 스킬 1 → 10)

| 툴 | 하는 일 |
|---|---|
| `read_chart` | 스펙(JSON 문자열 또는 파일)을 읽어 형식·범주·계열·축·값 범위·색을 사실로 돌려주고 ref 를 준다 |
| `describe_chart` | 판정 전에 **무엇이 무엇을 나타내는지** 적는다 — 인코딩·계열·형식, 그리고 한 줄 요약 |
| `distortion_report` | 축·각도가 만드는 화면 비율과 실제 값 비율을 **배수**로 계산한다 |
| `find_problems` | 규칙 41종을 걸어 걸린 것만 (severity 필터) |
| `chart_check` | 한 번에 — 점수·판정·고치기 순서·고치면 달라지는 숫자 |
| `fix_plan` | 고치기 항목 + **고친 스펙(guard JSON)** — 파일에 쓰지 않는다 |
| `alt_text` | 125자 alt + 긴 설명 + 데이터 표 |
| `compare_charts` | 고치기 전·후 — 점수 변화, 고쳐진 규칙, 남은 규칙, **잃은 범주·값** |
| `rule_catalog` | 규칙 목록과 각 규칙의 `보는 것`·`문제 아닌 때` |
| `overview` | 무엇을 하고 무엇을 **판정하지 않는지** |

### 규칙 41종 — 막음 8 · 주의 20 · 참고 13

| 장 | 수 | 예 |
|---|---|---|
| 왜곡 | 12 | `bar-truncated-baseline` · `area-truncated-baseline` · `dual-axis` · `log-axis-unlabeled` · `broken-axis` · `three-d` · `size-radius-linear` · `pie-shares-not-100` · `domain-hides-values` · `unequal-bins` · `time-interval-uneven` · `baseline-undeclared` |
| 형식 | 9 | `pie-too-many` · `pie-tiny-slice` · `line-for-categorical` · `radar-many-axes` · `stacked-compare` · `too-many-bars` · `too-many-series` · `scatter-overplot` · `stacked-not-100` |
| 색 | 7 | `too-many-colors` · `rainbow-palette` · `red-green-only` · `low-contrast-mark` · `gradient-for-groups` · `pure-color` · `color-reused` |
| 읽기 | 10 | `missing-axis-title` · `missing-unit` · `label-overlap` · `tiny-font` · `thousands-separator` · `decimal-noise` · `unsorted-bars` · `zero-height-bar` · `fraction-as-percent` · `weak-title` |
| 발행 | 3 | `no-source` · `no-alt` · `alt-too-long` |

규칙마다 **`fine_when`(문제가 아닌 때)** 이 있습니다. 예를 들어 잘린 축은
**섭씨 온도·pH·연도**(0이 의미 없는 양), 제목에 **'확대'** 라고 적은 그림, **horizon(접어 그리기)** 에서는 경고하지 않습니다.
좋은 검사기는 예외를 압니다 — 그래서 공식 예제 665개에서 **거짓 양성 0건**(0에서 시작한 차트를 잘렸다고 한 경우)이었습니다.

### 점수

`100 − Σ(막음 15 · 주의 8 · 참고 3)`, 판정은 **막음 → 보류 / 주의 → 주의 / 그 외 → 통과**.
점수는 편의이고, 판단은 **"본 것"(evidence)** 문장이 합니다 — 모든 항목에 이 차트의 숫자가 들어갑니다.

---

## 설치 · 실행

```bash
pip install -e ".[dev]"

chart-guard check examples/before.json         # 65/100 · 보류 (종료 코드 2)
chart-guard distortion examples/before.json    # 화면 길이비 35.33배 vs 실제 5.90배
chart-guard fix examples/before.json           # 고친 guard JSON
chart-guard alt examples/after.json            # 125자 alt + 표
chart-guard compare examples/before.json examples/after.json
chart-guard rules | chart-guard rules dual-axis
```

MCP 클라이언트 설정:

```json
{"mcpServers": {"chart-guard": {
  "command": "python", "args": ["-m", "chart_guard.server"],
  "env": {"CHART_GUARD_ROOT": "/path/to/specs"}}}}
```

읽기 전용입니다. 스펙 파일을 고치지 않고, 차트를 그리지 않고, 어디로도 보내지 않습니다.
`fix_plan` 이 돌려주는 스펙은 **문자열**이고, 적용은 사람이 합니다.

---

## 테스트 — 432 passed

| 파일 | 수 | 무엇을 |
|---|---|---|
| `test_rules.py` | 108 | 규칙 41종 각각의 **걸리는 경우**와 **예외라서 걸리지 않아야 하는 경우**, 깨끗한 차트의 거짓 양성 0 |
| `test_normalize.py` | 66 | guard · Vega-Lite(레이어·원·산점도·기본값) · Chart.js(y1·doughnut·indexAxis), 읽지 못한 값의 기록 |
| `test_geometry.py` | 41 | 화면 비율·픽셀 높이·로그 거리·원 각도·라벨 자리 |
| `test_color.py` | 38 | 대비(WCAG)·색각 이상 시뮬레이션·팔레트 성격 |
| `test_types.py` | 32 | 단위·범위·숨긴 계열·보고서 정렬 |
| `test_server.py` | 29 | **in-memory + stdio 서브프로세스** MCP 실행, 툴 10개 이름·호출 |
| `test_fix.py` | 28 | 고친 스펙이 값·범주를 잃지 않는지, 고친 스펙이 스스로 100점인지 |
| `test_alttext.py` | 23 | 125자 상한, 표 잘라내기, 축 하한 표기 |
| `test_check.py` | 18 | 점수·판정·깨진 규칙이 검사를 멈추지 않는지 |
| `test_cli.py` | 17 | 종료 코드(0/1/2/3)와 출력 |
| `test_compare.py` | 10 | 점수 변화·잃은 값 |

```bash
python3 -m pytest -q      # 432 passed
```

---

## 실측 — 실제 데이터·실제 표본·실제 렌더

### ① 공개 Vega-Lite 예제 820개 (`tools/corpus_probe.py`)

저장소 파일은 내려받아 **읽기만** 하고 저장소에 넣지 않았습니다.

```
파일 820 · 읽음 665 · 읽지 못함 155(concat/repeat/mark 없는 스펙)
판정: pass 534 · warn 129 · hold 2      (출처·alt·제목 규칙은 집계에서 제외)
형식: bar 277 · line 100 · scatter 88 · area 39 · pie 13 · histogram 3 · unknown 145
거짓 양성(0에서 시작한 차트를 '잘렸다'고 한 경우): 0
```

많이 걸린 것: `missing-axis-title` 108 · `baseline-undeclared` 73 · `low-contrast-mark` 40 ·
`line-for-categorical` 31 · `unsorted-bars` 28 · `pie-too-many` 6 · `dual-axis` 2.

**보류 2건은 둘 다 Vega-Lite 공식 듀얼축 예제**(`layer_dual_axis.vl.json` · 정규화본)입니다. 잡아야 할 것을 잡았습니다.
반대로 **`bar-truncated-baseline` 은 820개에서 0건** — Vega-Lite 는 막대의 기본값이 `zero:true` 라서
잘린 축은 **사람이 손으로 만들 때** 생깁니다. 그래서 실측 ③은 손으로 자른 축을 씁니다.

**표본이 가르쳐 준 것**: 처음엔 `area_horizon.vl.json` 을 "축 밖의 값이 있다"(막음)로 잡았습니다.
horizon 차트는 **일부러** 값을 접어 그리는 형식이었습니다 → `folded` 판정을 넣고
`bar-truncated-baseline`·`area-truncated-baseline`·`domain-hides-values` 에서 제외했습니다.
규칙을 늘리는 것보다 **예외를 아는 것**이 정확도를 올렸습니다.

### ② 렌더 교차 검증 (`tools/render_check.py`)

우리 계산이 "화면에서 이만큼 보인다"고 말하는 값을, **matplotlib 으로 실제로 그린 PNG 의 픽셀**에서 다시 쟀습니다.

| 케이스 | 축 하한 | 계산 | 픽셀 | 오차 |
|---|---|---|---|---|
| `truncated-20` | 20 | 5.0000배 | 5.0952배 | 1.90% (허용 3.67%) |
| `truncated-1150` | 1,150 | 3.0000배 | 3.0294배 | 0.98% (허용 3.44%) |
| `zero-baseline` | 0 | 1.8000배 | 1.8000배 | 0.00% (허용 1.58%) |

허용치는 1px 양자화에서 오는 몫입니다. **계산과 렌더가 같은 비율을 말합니다.**

### ③ 실제 공개 데이터 — IBM 12개월 종가 (`tools/real_data.py`)

`vega-datasets/stocks.csv`(원본 NOAA/공개 시세)에서 2009-04 ~ 2010-03 종가 12개(101.29 ~ 130.32 USD).
같은 값으로 두 그림을 만들어 검사했습니다.

| 그림 | 판정 | 걸린 것 |
|---|---|---|
| 막대 · y축 하한 **101** | **85/100 · 보류** | `bar-truncated-baseline` — "화면에서 **101.10배**, 실제 **1.29배** (과장 **78.6배**)" |
| 막대 · y축 하한 **0** | **100/100 · 통과** | 없음 · 잃은 범주 0 · 잃은 값 0 |

주가처럼 0이 의미 없는 값의 정직한 대안은 **선 차트 + '확대' 표기**이기도 합니다 — 규칙의 `fine_when` 에 그렇게 적혀 있습니다.

### ④ 예제 before → after (`tools/demo.py`)

```
① examples/before.json        65/100 · 보류 — 막음 1(잘린 축) · 주의 1(저대비) · 참고 4
② fix_plan 이 만든 스펙       100/100 · 통과 — 축 0 · 색 대비 보정 · 글자 14px · 값 순 정렬
③ examples/after.json         100/100 · 통과 — 잃은 범주 0 · 잃은 값 0
④ examples/pie-before.json    42/100 · 보류 → 상위 4 + 기타, 합계 93.0 → 93.0 (값 보존)
```

---

## 한계 — 이 도구가 **판정하지 않는** 것

모든 툴 출력 하단과 `overview` 에 같은 문장이 붙습니다.

- **차트 이미지의 픽셀** — 스크린샷·PNG 는 읽지 못합니다. 스펙(JSON)만 읽습니다.
- **데이터가 사실인지** — 값이 맞는지, 표본이 대표성 있는지는 모릅니다.
- **색의 의도** — 브랜드 색인지 강조인지 모릅니다. 대비·색각 거리만 계산합니다.
- **글자가 실제로 겹쳤는지** — 폭을 **추정**합니다(한글 1.0em·라틴 0.55em).
- **렌더러가 축을 다시 계산한 결과** — 라이브러리가 `nice()` 로 축을 늘리면 화면은 조금 달라집니다.
- **독자의 배경지식**, 재미, 설득력.
- 읽지 못하는 스펙: `concat`/`repeat`, `mark` 없는 스펙, `url` 로 데이터를 가리키는 스펙(값 없이 축·형식만 봅니다), 여러 겹 레이어는 **첫 겹만**.

선언이 없는 값은 **추측하지 않고 비워 둡니다.** 축 하한이 선언되지 않았으면 "선언되지 않았다"고 적고,
어떤 기본값으로 계산했는지(`Vega-Lite 기본값 true` 등)를 함께 남깁니다 — 그게 `baseline-undeclared` 규칙입니다.

---

## 구조

```
chart_guard/
  normalize.py   스펙 → Chart (Vega-Lite · Chart.js · guard JSON)
  geometry.py    축 하한의 화면 비율, 픽셀 높이, 원 각도, 로그 거리, 라벨 자리
  color.py       sRGB→Lab, WCAG 대비, 적록/녹색약 시뮬레이션, 팔레트 성격
  rules.py       규칙 41종 (doc · fine_when · check · fix)
  check.py       규칙 실행 · 점수 · 판정 · 건너뛴 것
  fix.py         고치기 순서 + 고친 스펙(JSON) — 색 대비 보정·글자 크기·값 순 정렬
  alttext.py     125자 alt · 긴 설명 · 데이터 표
  compare.py     전후 비교 — 잃은 범주·값
  report.py / cli.py / server.py / store.py
tools/           corpus_probe(820 스펙) · render_check(픽셀 교차검증) · real_data(IBM) · demo
examples/        before·after·pie·dual-axis·vega-lite·chartjs
tests/           432 tests
```

## 라이선스

MIT. 원본 2개도 MIT 이며, 코드는 복사하지 않고 설계만 참고했습니다(위 표).
