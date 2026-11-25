# test-radar

**바뀐 코드에 도달하는 테스트만 고른다 — 근거가 없으면 전체를 돌린다.**

커밋 하나에 테스트 300개를 다 돌리는 대신, diff 를 import 그래프에 얹어
`tests/test_x.py` 4개만 돌려도 되는지, 아니면 이번엔 전체를 돌려야 하는지를
**이유와 함께** 답하는 읽기 전용 MCP 서버입니다.

```bash
test-radar scan . --base origin/main          # git diff 로 바로
test-radar scan . --diff change.patch         # 패치 파일
test-radar scan . --diff - --json < x.patch   # 표준입력 · 기계용
```

```text
🎯 test-radar · 변경 2개 파일 +15/-1
   저장소 모듈 50 · 테스트 27파일/391항목 · 해석 못 한 import 82

선택: 6파일 · 159/391항목 (41%)
   ◆ tests/test_testing.py  L0 테스트 자체  테스트 파일 자체가 바뀜  (26항목)
   ● tests/test_appctx.py  L1 직접  바뀐 심볼 `FlaskClient` 를 직접 import  (15항목)
   ● tests/test_basic.py  L1 직접  바뀐 심볼 `FlaskClient` 를 직접 import  (90항목)
   ...
테스트 근거 없는 변경: 없음
위험 규칙: 해당 없음
계획: 선택 실행 · 예상 9.45초(모델)
   python -m pytest tests/test_testing.py tests/test_reqctx.py tests/test_request.py tests/test_views.py
   python -m pytest tests/test_appctx.py tests/test_basic.py
판정: 선택 실행
```

---

## 원본 2개 — 코드는 한 줄도 복사하지 않았습니다

| | 저장소 | 라이선스 | 규모 | 마지막 푸시 | 가져온 **설계·태도** |
|---|---|---|---|---|---|
| ① | [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) | **MIT** | ★49,168 · MCP 툴 17개 · C/tree-sitter/SQLite | 2026-11-23 | **변경→영향 테스트**: diff 를 심볼에 매핑하고, `detect_changes` 로 위험 분류·테스트 영향(`scope: "tests"`)을 낸다. **"증거가 부족하면 넓게 돌린다"** 는 Smart CI 의 폴백 태도 |
| ② | [github/github-mcp-server](https://github.com/github/github-mcp-server) | **MIT** | ★34,757 · 툴 96개/툴셋 23개 | 2026-11-25 | **범위를 좁혀 읽기**: 툴셋을 골라 켜고, `--read-only` 로 쓰기를 빼고, 결과를 작은 DTO 로 줄인다. **PR 의 diff 만** 다루고 저장소 전체를 컨텍스트에 넣지 않는 태도 |

- ①은 C 로 쓰인 로컬 코드 인텔리전스(지속 그래프 + CBM Lens)입니다. 이 툴은 그 그래프를 만들지 않고,
  **diff → 심볼 → import 역방향 → 테스트** 라는 같은 질문을 파이썬 ast 만으로 다시 구현했습니다.
- ②는 GitHub 의 공식 MCP 로, 23개 툴셋 중 필요한 것만 켜는 구조입니다. 이 툴은 그 구조를 따라
  **툴 10개**로 쪼개고, 쓰기 툴은 하나도 두지 않았습니다(읽기 전용).
- 두 원본의 코드·프롬프트·스키마를 복사하지 않았습니다. README 에 적힌 **관점**만 가져왔습니다.

---

## 어떻게 고르나 — 근거 4단계

| 단계 | 근거 | 표시 | 필수? |
|---|---|---|---|
| 0 | 테스트 파일이 diff 에 있음 / conftest 가 바뀐 범위 | `◆` | ✅ |
| 1 | 바뀐 모듈·심볼을 **직접** import 하거나 문자열로 참조(monkeypatch 대상) | `●` | ✅ |
| 2 | 중간 모듈을 거쳐 **2단계 안**에 도달 | `◐` | ✅ |
| 3 | 같은 디렉터리 · 3단계 이상 (`depth` 로 늘릴 때만) | `○` | ❌ 참고 |

**같은 디렉터리라는 이유만으로는 고르지 않습니다.** 그건 근거가 아니라 추측이기 때문입니다.
`depth` 기본값은 2입니다 — 저장소가 촘촘하면 3단계는 거의 모든 테스트를 끌어옵니다
(flask 에서 depth 3 으로 돌리면 391항목 중 374개가 선택됩니다. 그래서 기본값을 2로 두었습니다).

### 고르지 않을 때 — 폴백 6조건

하나라도 걸리면 `판정: 전체 실행` 으로 바뀝니다.

1. `pytest.ini` · `tox.ini` · `setup.cfg` · `pyproject.toml` 의 pytest 설정 · `conftest.py` 변경
2. 바뀐 파일을 파싱하지 못함(문법 오류·인코딩)
3. 바뀐 파일에 동적 import (`importlib.import_module`, `__import__`, 변수 `require`)
4. 테스트 파일을 하나도 찾지 못함
5. 선택이 전체 항목의 **60% 이상** — 줄이는 의미가 없음
6. (`depth` 를 늘렸을 때만) 3단계 이상 선택이 섞임 — 참고로만 표시

---

## 툴 10개

| 툴 | 하는 일 |
|---|---|
| `open_repo` | 저장소를 읽어 모듈·테스트·import 그래프를 만들고 `repo-N` 을 준다 |
| `read_diff` | unified diff → 바뀐 파일·심볼·변경집합 `cs-N` |
| `list_changes` | 파일별 증감·바뀐 심볼·사라진 정의·인자 변경 (덩어리 원문 옵션) |
| `map_tests` | 도달하는 테스트를 근거(L0~L3)·이유·항목 수와 함께 |
| `impact_report` | 선택 + 구멍 + 위험 + 계획 + 판정을 한 장으로 |
| `untested_surface` | 테스트가 아무 근거도 대지 못하는 파일·공개 심볼만 |
| `ci_plan` | 조각·순서가 있는 pytest/jest 명령 + 전체 실행 대체안 |
| `compare_selections` | 두 변경(PR 을 쪼갤 때)의 선택을 비교 — 겹침·합집합 |
| `rule_catalog` | 규칙 23종과 각 규칙이 보는 것 |
| `overview` | 무엇을 하고 무엇을 판정하지 않는지 |

## 규칙 23종

| 심각 | 규칙 | 보는 것 |
|---|---|---|
| 치명 | `test-config-changed` | 테스트 실행 방식 자체가 바뀜 → 전체 실행 |
| 치명 | `unparseable-change` | 바뀐 파일 파싱 실패 → 그래프 불완전 |
| 치명 | `deleted-module-still-imported` | 지운 모듈을 아직 import (이름으로 추적) |
| 치명 | `no-tests-in-repo` | 테스트가 없음 |
| 심각 | `dynamic-import` | importlib·`__import__`·변수 require |
| 심각 | `no-test-reaches` | 바뀐 모듈에 (전이로) 도달하는 테스트 0 |
| 심각 | `renamed-module-stale-import` | 이름 바꾼 모듈의 옛 경로 import |
| 심각 | `public-symbol-removed` | 공개 함수·클래스 삭제 |
| 심각 | `test-weakened` | assert 삭제 · skip/xfail 추가 |
| 심각 | `test-deleted` | 테스트 파일 삭제 |
| 주의 | `signature-changed` | def 인자 변경 (주석·기본값 표기는 무시) |
| 주의 | `public-symbol-no-test` | 바뀐 공개 심볼을 이름으로 대는 테스트 없음 |
| 주의 | `high-fan-in` | 프로덕션 모듈 5개 이상이 import |
| 주의 | `fixture-changed` | conftest 변경 — 영향 범위 확정 불가 |
| 주의 | `new-file-no-test` | 테스트 없는 새 코드 파일 |
| 주의 | `entrypoint-changed` | CLI/main 진입점 변경 |
| 참고 | `module-level-code` | import 만으로 실행되는 줄 변경 |
| 참고 | `broad-except` | `except:` / `except Exception:` 로 삼킴 |
| 참고 | `nondeterminism` | `time.sleep` · `datetime.now` · `random` 추가 |
| 참고 | `env-or-network` | `os.environ` · `requests` 추가 |
| 참고 | `selection-too-broad` | 선택 60% 이상 |
| 참고 | `broad-test` | 저장소 모듈 8개 이상 import 하는 통합 테스트 — 시간이 안 줄 수 있음 |
| 참고 | `constant-condition` | `if True:` 같은 상수 조건 |

---

## 실측 (2026-11-26, 이 저장소의 도구로 직접 돌린 값)

### ① 실제 공개 저장소 — flask 의 IPv6 세션 수정 커밋 `de8429ff`

`src/flask/testing.py` 한 줄 + 회귀 테스트 `test_session_transaction_ipv6` 추가 (2파일 +15/-1).

- 저장소: 모듈 50 · 테스트 27파일/391항목 (수집 시 485개 — 파라미터화로 늘어남)
- **선택 6파일 / 159항목 (41%)** · 위험 규칙 0 · `판정: 선택 실행`
- 수정을 되돌린 사본에서:
  - **선택한 6파일 실행 → `test_session_transaction_ipv6` 실패** (200 passed, 1 failed, **1.14s**)
  - 전체 실행 → 같은 테스트 실패 + 환경 문제 2건(`test_get_version`, asgiref 없는 async) (478 passed, 3 failed, **3.38s**)
- 즉 선택이 회귀 테스트를 **빠뜨리지 않았고**, 전체의 1/3 시간에 같은 결론에 도달했습니다.

### ② 릴리스 전체 diff — flask `3.0.2` → `3.0.3`

- 44파일 +754/-634 · **선택 22파일 / 358항목 (93%)**
- `pyproject.toml`·`tox.ini` 변경 → `치명 2` → **`판정: 전체 실행`**
- 이런 diff 는 줄이는 게 맞지 않습니다. 도구가 그렇게 말합니다.

### ③ 변이 시험 — day-09 `log-triage` (테스트 파일 13개 · 항목 283 · 수집 304개, `tools/probe.py`)

소스에 변이 5개를 넣고, **선택한 테스트만** 돌렸을 때 잡히는지 / 전체와 비교했습니다.

| 변이 | 선택 | 항목(283) | 선택 실행 | 전체 실행 | 결과 |
|---|---|---|---|---|---|
| `levels`: SEVERE→WARN | 3파일 | 80 | **실패 2.65s** | 실패 9.42s | 선택이 잡음 |
| `signature`: 공백 접기 제거 | 8파일 | 181 | 통과 9.41s | 통과 8.96s | **전체도 못 잡음(테스트 구멍)** |
| `rates`: 오류를 CRITICAL 만 셈 | 4파일 | 113 | **실패 8.83s** | 실패 9.38s | 선택이 잡음 |
| `redact`: Luhn 무력화 | 4파일 | 116 | **실패 8.80s** | 실패 9.89s | 선택이 잡음 |
| `stack`: Python 안쪽 프레임 반대 | 4파일 | 117 | **실패 8.80s** | 실패 9.67s | 선택이 잡음 |

- **선택이 잡은 변이 4/5 · 선택은 놓치고 전체가 잡은 변이 0/5 · 전체도 못 잡은 변이 1/5**
- 선택이 못 잡은 1건은 **전체 실행도 못 잡습니다** — 선택 실패가 아니라 테스트가 그 동작을 안 보는 것입니다.
- 시간이 항상 줄지 않는 이유도 그대로 보입니다: `tests/test_server.py`(stdio 통합, 약 6초)가
  선택에 들어오면 항목이 1/3이어도 시간은 8.8초입니다. 그래서 `broad-test` 규칙으로 표시하고,
  시간은 **모델**로만 제시합니다.

---

## 설치

```bash
pip install -e ".[dev]"
```

MCP 클라이언트 설정:

```json
{"mcpServers": {"test-radar": {
  "command": "python", "args": ["-m", "test_radar.server"],
  "env": {"TEST_RADAR_ROOT": "/path/to/your/repo"}}}}
```

## 실행

```bash
test-radar scan . --base origin/main --changes --hunks   # 사람이 읽는 보고서
test-radar scan . --diff change.patch --json            # 기계가 읽는 JSON
test-radar scan . --base HEAD --staged                  # 스테이징된 것만
test-radar rules                                        # 규칙 23종
```

종료 코드: `0` 통과 · `1` 사용 오류 · `2` 치명 규칙 있음(전체 실행 권고).
`examples/shop/` 에 13개 파일짜리 작은 상점 저장소가 있습니다.

```bash
python -m pytest                       # 308 passed
python tools/probe.py --json out.json  # 변이 시험(약 60초)
```

## 한계 — 이 툴이 판정하지 않는 것

- **테스트가 통과하는지** — 선택만 합니다. 실행은 하지 않습니다(명령도 문자열로만 만듭니다).
- **실행 시간** — 항목 수 × 가정값(기본 50ms) 모델입니다. 실측 시간이 아닙니다.
- **커버리지 %** — line coverage 를 계산하지 않습니다. "그 테스트가 이 줄을 실행했다"를 모릅니다.
- **동적 import 뒤의 간선** — `importlib`, 문자열 경로, 설정 기반 로딩은 보이지 않습니다(규칙으로 표시).
- **네이티브 확장·설정 파일의 의미** — YAML/INI 값이 코드에 어떤 영향을 주는지 모릅니다.
- **같은 이름의 다른 심볼** — `from a import f` 와 `from b import f` 를 구분하지 못하는 자리가 있습니다.
- **JS/TS** — 정규식 기반이라 `export *` 재export 체인, path alias 일부, 조건부 로딩은 놓칩니다.
- **테스트 실행 순서 의존성** — 순서를 바꿔도 되는지는 알 수 없습니다.

이 한계는 README·`overview`·모든 보고서 하단에 같은 문장으로 나옵니다.

## 구조

```text
test_radar/
  types.py      자료형(diff·모듈·심볼·선택·위험·계획)
  diffparse.py  unified diff 읽기(git · diff -u · rename · binary · 모드)
  pyast.py      Python 파일 → 모듈(import·심볼·최상위 실행 줄·문자열 참조)
  jsimports.py  JS/TS import·export·테스트 선언(정규식)
  graph.py      저장소 그래프(정방향·역방향·전이·테스트 수집)
  select.py      근거 4단계 선택 + 구멍 + 폴백
  risk.py        규칙 23종
  plan.py        CI 명령·조각·시간 모델
  report.py      사람이 읽는 보고서
  store.py       ref 저장소(메모리)
  server.py      MCP 10툴(stdio)
  cli.py         명령줄
tests/          pytest 308개
tools/probe.py  변이 실측
examples/shop/  예제 저장소(13파일)
```

## 라이선스

이 구현은 **MIT**. 원본 두 저장소의 라이선스는 위 표에 적었고(MIT · MIT),
코드는 복사하지 않았습니다.
