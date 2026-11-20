# design-spec — 디자인 파일에서 색·간격·글자를 세고 DESIGN.md 를 뽑는다

**1일 1스킬 Day 05.** 공개된 MCP·에이전트 스킬 두 개를 골라 하나로 섞는 시리즈의 다섯 번째입니다.

> 구현이 끝난 화면을 재는 도구는 많습니다. **디자인 단계**에서 "색이 몇 종인지,
> 간격이 4의 배수인지, 글자 단계가 몇 개인지"를 세어 주는 도구는 드물죠.
> Figma 응답 모양의 JSON 하나로 **점수 · 고치는 값 · DESIGN.md** 까지 한 번에 뽑습니다.

```bash
design-spec audit examples/demo/before.json
```

```text
# design-spec · 예제몰 – 주문/결제 (before)  (examples/demo/before.json)

- 화면 1개 · 노드 34개 · 글자 14개 · 색 10종 · 크기 6단계 · 간격 값 7종 (기준 4px)
- 점수 **0/100** (심각) · 위반 **17건** (치명 6 · 심각 2 · 보통 9) · 규칙 12종

1. **contrast-text** 글자 대비 2.53:1 (필요 4.5:1) — 치명
   - `e12` Body > Card/Order > 금액 안내
     근거: #9AA0A6 on #F9FAFB · 13.0px
     고치기: #6F7378 로 바꾸면 4.56:1
2. **layout-collision** 글자 "무선 이어폰" 와 "품절" 가 91% 겹칩니다 — 치명
   - `e19` List/Items > Item/이어폰 > 무선 이어폰
     고치기: 한쪽을 옮기거나 폭을 줄이세요. 겹친 글자는 둘 다 읽을 수 없습니다
3. **touch-target** 누를 수 있는 요소가 250×32 — 최소 44×44 — 치명
   …
```

```bash
design-spec design-md examples/demo/after.json
```

```markdown
# Design System: 예제몰 – 주문/결제 (after)

## 2. Color Palette & Roles
| 이름 | 값 | 역할 | 쓰인 곳 | 최악 대비 |
|---|---|---|---|---|
| Pure White | `#FFFFFF` | 배경·카드 | 6곳 | 5.52:1 |
| Slate Gray | `#6B7280` | 보조 글자 | 5곳 | 4.83:1 |
| Ink Black | `#111827` | 본문 글자 | 8곳 | 17.74:1 |
| Vivid Blue | `#0057FF` | 주요 동작 | 4곳 | 4.96:1 |
```

---

## 오늘 섞은 두 가지

| 원본 | 라이선스 | 무엇을 가져왔나 |
|---|---|---|
| [GLips/Figma-Context-MCP](https://github.com/GLips/Figma-Context-MCP) (Framelink MCP for Figma) | **MIT** | **파이프라인 설계** — ① Figma 응답을 그대로 주지 않고 에이전트에 필요한 레이아웃·스타일만 남기기, ② **한 번만 트리를 훑는 extractor**(layout/text/visual/component 로 조합, `maxDepth`·필터), ③ 전부 훑은 뒤에야 알 수 있는 것을 **finalize 단계**에서 처리 — 두 노드 이상이 쓰는 스타일만 전역 표로 올리고 한 번 쓰는 스타일은 노드에 인라인, ④ 자식까지 같은 부분 트리는 **template 하나로 접기** |
| [google-labs-code/stitch-skills](https://github.com/google-labs-code/stitch-skills) 의 [`design-md` 스킬](https://github.com/google-labs-code/stitch-skills/tree/main/plugins/stitch-utilities/skills/design-md) | **Apache-2.0** | **DESIGN.md 의 구조와 태도** — 다섯 칸(Visual Theme & Atmosphere / Color Palette & Roles / Typography Rules / Component Stylings / Layout Principles), 색은 **서술형 이름 + 정확한 hex + 기능적 역할** 세트로, "무엇"보다 **"왜"**를 적기, 분위기는 형용사로(airy, dense, pill-shaped, whisper-soft shadow) |

- 두 저장소의 라이선스는 `gh api` 로 실제 확인했습니다 — Figma-Context-MCP **MIT**(stars 16.3k, 마지막 푸시 2026-11-15), stitch-skills **Apache-2.0**(stars 11.0k, 마지막 푸시 2026-11-20).
- 두 프로젝트의 **코드는 한 줄도 복사하지 않았습니다.** 위에 적은 설계와 문서 구조만 가져와 Python 표준 라이브러리로 새로 구현했습니다.
- 툴 수: Figma-Context-MCP **2개**(`get_figma_data`, `download_figma_images`) + 스킬 1개 → 이 서버 **8개**.

### 원본과 이 서버는 무엇이 다른가

| | Figma-Context-MCP | stitch `design-md` | **design-spec** |
|---|---|---|---|
| 입력 | Figma API (**토큰 필요**) | Stitch 화면 + HTML 코드 | **파일 하나** (Figma 응답 모양 JSON) |
| 출력 | 에이전트용 YAML 트리 | DESIGN.md | 트리 + 색/간격/글자 보고 + DESIGN.md |
| 색 역할 추정 | ✗ (사람이 판단) | 사람이 판단 | **✓ 면적·빈도·이름으로 추정** |
| 글자 대비 계산 | ✗ | ✗ | **✓ WCAG 2.2** (반투명 합성 포함) |
| 간격 기준 단위 | ✗ | ✗ | **✓ 데이터에서 추정** |
| 점수·종료 코드 | ✗ | ✗ | **✓ `audit` exit 1** |
| Figma 계정 없이 | ✗ | ✗ | **✓** |

브라우저도 Figma 토큰도 없이 도는 자리(CI, 커밋 훅, 오프라인 리뷰)를 맡고,
"지금 화면이 어떻게 보이는가"는 원본 두 도구의 몫으로 남겨 둡니다.

---

## 툴 8개

| 툴 | 하는 일 |
|---|---|
| `read_design` | 디자인 JSON → 읽을 수 있는 트리. `ref`·크기·색·글자, 반복 스타일은 표로, 같은 모양은 접어서. `mode=all\|layout\|text\|visual`, `depth`, `ref`, 토큰 예산 |
| `find_in_design` | 이름·글자·타입으로 노드 찾기 (`ref` + 경로) |
| `palette_report` | 색 사용량·역할 추정·**거의 같은 색**·최악 대비·토큰 커버리지 |
| `scale_report` | `kind=spacing\|type\|radius` — 기준 단위, 분포(막대), 스케일 밖 값 |
| `audit_design` | 규칙 17종 검사 → 점수·위반·**고치는 값**(제안 색 hex 까지). `format=json` |
| `fix_order` | 고치는 순서 — 무거운 것부터, 같은 등급이면 여러 번 나온 것부터 |
| `write_design_md` | **DESIGN.md** 생성 (`save_to` 로 저장, 루트 밖은 거부) |
| `overview` | 규칙 목록과 **판정하지 않는 것** |

## 규칙 17종

| 규칙 | 내용 | 근거 | 등급 |
|---|---|---|---|
| `contrast-text` | 글자와 실제 배경의 대비가 4.5:1(큰 글자 3:1) 미만 | WCAG 2.2 1.4.3 | **치명** |
| `touch-target` | 누를 요소가 44×44 미만 | Apple HIG 44pt · Material 48dp | **치명** |
| `layout-collision` | 같은 부모의 두 글자가 25% 이상 겹침 | 레이아웃 | **치명** |
| `layout-overflow` | 자식이 부모 상자를 1px 넘게 벗어남 | 레이아웃 | 심각 |
| `type-too-small` | 글자 크기 11px 미만 | 최소 11px | 심각 |
| `type-line-cramped` | 20자 이상 글자의 줄 높이/크기 < 1.15 | 줄 높이 ≥ 1.15 | 심각 |
| `spacing-off-scale` | 간격·여백이 기준 단위의 배수가 아님 | 기준 단위 | 보통 |
| `spacing-too-many` | 서로 다른 간격 값이 8종류 초과 | ≤ 8종 | 보통 |
| `palette-near-duplicate` | 눈으로 구분 안 되는 두 색(거리 ≤ 10)이 따로 쓰임 | 색 거리 | 보통 |
| `palette-too-wide` | 한 파일에 색이 12종류 초과 | ≤ 12종 | 보통 |
| `color-hardcoded` | 칠한 노드의 70% 미만만 색 스타일(토큰)을 씀 | 토큰 커버리지 | 보통 |
| `radius-too-many` | 모서리 반경 3종류 초과 | ≤ 3종 | 보통 |
| `type-too-many-sizes` | 글자 크기 5단계 초과 | ≤ 5단계 | 보통 |
| `type-one-off` | 한 화면에서 한 번만 쓰인 크기 | 단계로 묶기 | 보통 |
| `type-many-families` | 글꼴 2종 이상 | 1종 | 보통 |
| `layout-misaligned` | 같은 크기 형제가 같은 축에서 1~3px 어긋남 | auto-layout | 보통 |
| `naming-default` | `Frame 12` 같은 기본 이름이 3개 이상 | 역할 이름 | 보통 |

### 점수는 "몇 종류가 잘못됐나"

```text
점수 = 100 − Σ(규칙별 감점)      치명 25 · 심각 12 · 보통 4
```

같은 규칙이 9번 나와도 **한 번만** 깎습니다. 반복은 "고칠 곳 하나(패턴)"라는 신호이고,
점수는 "얼마나 여러 종류가 어긋났는가"를 말해야 하기 때문입니다.
90+ 양호 · 70+ 주의 · 40+ 위험 · 그 아래 심각.

### 근거가 약한 규칙은 약하게

`layout-misaligned` 는 **같은 크기(±1px) 형제끼리만** 비교합니다.
아이콘(44×44)과 글자(120×28)는 원래 높이가 달라서 세로 위치가 다른 게 정상이니까요.
`touch-target` 은 **글자 노드를 제외**합니다 — 라벨은 누르는 상자가 아닙니다.
`color-hardcoded` 는 칠한 노드가 10개 미만이면 아예 판정하지 않습니다(표본 부족).

## 트리 읽기 — 토큰을 아끼는 세 가지

```text
frame "Checkout / Mobile" 390×844 · s3 · ref=e3
  frame "Header" 390×64 · ref=e4
    instance "Icon/Back" 24×24 · stroke #111827 2 · r4 · ref=e5
    text "주문/결제" 20px/700/lh 24 · 120×24 · fill #111827 · “주문/결제” · ref=e6

## 반복 스타일 (두 노드 이상에서 쓰임 — 숫자가 쓰인 횟수)
s1 ×3 · fill #111827 · 글자 15px/400/Pretendard/lh 22
s2 ×2 · fill #6B7280 · 글자 13px/400/Pretendard/lh 18
```

1. **`ref` 는 문서 순서로 고정** — `depth`·`mode`·`max_nodes` 를 바꿔도 같은 파일이면 같은 번호.
   "아까 그 버튼(`e29`)만 다시 보여 줘"가 성립합니다.
2. **스타일 세기** — 같은 겉모습이 두 노드 이상이면 `s1` 로 올리고 노드엔 참조만.
   한 번만 쓰는 스타일은 올리지 않습니다(간접 참조 비용 > 이득) — 원본의 "count-gated" 생각.
3. **같은 모양 접기** — 자식까지 같은 부분 트리는 두 번째부터 `↺ e12` 로 첫 번째를 가리키고
   다시 찍지 않습니다. 글자 내용은 서명에서 빼서, **카드 12장이 글자만 달라도 한 모양**으로 접힙니다.

## 실제 결과 (2026-11-21 실행)

| 파일 | 점수 | 위반 | 색 | 크기 | 간격 값 | 반경 | 토큰 커버리지 |
|---|---|---|---|---|---|---|---|
| `examples/demo/before.json` (일부러 만든 문제 파일) | **0/100** 심각 | 17건 · 규칙 12종 | 10종 | 6단계 | 7종 (기준 4px, 85%) | 5종 | 40% |
| `examples/demo/after.json` (고친 파일) | **100/100** 양호 | 0건 | 6종 | 4단계 | 4종 (기준 4px, 100%) | 2종 | 100% |

- before 가 잡은 것: #9AA0A6 on #F9FAFB **2.53:1** · 아이콘 24×24 · 버튼 높이 32 ·
  "무선 이어폰" 위에 "품절" **91% 겹침** · 쿠폰 설명이 카드 밖으로 **62px** · 13px 글자의 줄 높이 **1.08** ·
  간격 13/10px · #0057FF ↔ #0A5CFF · 반경 5종 · `Frame 12`/`Rectangle 5`.
- after 는 같은 항목이 모두 사라졌고, 색은 10 → 6종, 크기는 6 → 4단계, 반경은 5 → 2종이 됐습니다.
- 전체 실행 로그: [examples/sample_output.md](examples/sample_output.md) (읽기·색·간격·글자·검사·고치기 순서·DESIGN.md 9개)

---

## 설치·실행

```bash
cd day-05-design-spec
pip install -e ".[dev]"

design-spec read    examples/demo/before.json --mode layout --depth 3
design-spec find    examples/demo/before.json --text 쿠폰
design-spec palette examples/demo/before.json
design-spec scale   examples/demo/before.json --kind spacing
design-spec audit   examples/demo/before.json
design-spec plan    examples/demo/before.json
design-spec design-md examples/demo/after.json --out DESIGN.md
design-spec rules   contrast-text
```

### MCP 서버 (stdio)

```json
{
  "mcpServers": {
    "design-spec": {
      "command": "python",
      "args": ["-m", "design_spec.server"],
      "env": { "DESIGN_SPEC_ROOT": "/Users/me/project/designs" }
    }
  }
}
```

- `mcp>=2.3,<3` 만 있으면 됩니다. 파서·색 계산·규칙·보고는 전부 표준 라이브러리.
- `DESIGN_SPEC_ROOT` 를 주면 상대 경로가 그 폴더 기준이 되고, `write_design_md` 의 저장도 그 안으로 제한됩니다.

### CI 에서

```bash
design-spec audit designs/checkout.json || echo "치명·심각 위반이 있습니다"   # exit 1
```

종료 코드: `0` 통과 · `1` 치명 또는 심각 있음 · `2` 파일·인자 오류.

### 입력 형식

Figma REST 응답 모양이면 그대로 읽습니다.

```json
{ "name": "예제몰", "document": { "type": "DOCUMENT", "children": [
  { "type": "FRAME", "name": "Checkout", "absoluteBoundingBox": {"x":0,"y":0,"width":390,"height":844},
    "fills": [{"type":"SOLID","color":{"r":1,"g":1,"b":1,"a":1}}],
    "styles": {"fills": "S:surface"},
    "children": [
      { "type":"TEXT", "characters":"주문/결제",
        "style":{"fontFamily":"Pretendard","fontSize":20,"fontWeight":700,"lineHeightPx":28},
        "fills":[{"type":"SOLID","color":{"r":0.067,"g":0.094,"b":0.153,"a":1}}] }
    ] } ] } }
```

- 받는 모양: `{"document": …}` · `{"nodes": {"1:2": {"document": …}}}` · 노드 하나 · 노드 배열 · JSON 문자열.
- 칠은 0~1 실수(Figma)와 `#RRGGBB`·`rgb()`·`rgba()` 문자열 둘 다. 여러 겹이면 아래부터 합성합니다.
- `absoluteBoundingBox` 가 없으면 자식들의 상자로 **추정**하고 `box_estimated` 로 표시합니다(0으로 채우지 않습니다).

## 한계 (계산한 척하지 않는 것)

1. **Figma 에 붙어 있지 않습니다.** 토큰·네트워크 없이 파일만 읽습니다. 자동으로 최신 파일을 가져오지는 않습니다.
2. **그라디언트·이미지 위 글자의 대비는 계산하지 않습니다.** 몇 곳인지 세어서 보고합니다(모르는 것을 0으로 두지 않음).
3. **`lineHeight` 가 '자동'이면 줄 높이를 판정하지 않습니다.** 추측하지 않습니다.
4. 렌더링하지 않으므로 **폰트 폴백·실제 줄바꿈·글자 잘림**은 모릅니다. 넘침은 **상자 기준**입니다.
5. 색 이름은 **색상·채도·밝기로 지은 것**입니다. 브랜드 이름(예: "Pickle Green")은 사람이 붙여야 합니다.
6. 역할 추정은 휴리스틱입니다 — 이름에 `button`·`btn`·`버튼` 이 없으면 주요 색을 놓칠 수 있습니다.
7. **상태(hover/disabled/다크 모드)** 는 파일에 따로 있으면 따로 검사해야 합니다. 한 파일 안의 변형은 구분하지 않습니다.
8. 점수는 이 서버의 척도입니다. 다른 디자인 린트와 같은 숫자가 아닙니다.
9. `read_design` 은 **1토큰 ≈ 2.8자** 어림으로 자릅니다. 정확한 토크나이저가 아닙니다.

## 파일

```text
design_spec/
  color.py       파싱 · 알파 합성 · WCAG 대비 · 색 거리 · 서술형 이름 · 제안 색
  nodes.py       관대한 Figma 응답 파서 (칠·선·효과·글자·레이아웃·이름 있는 스타일, 상자 추정)
  walk.py        한 번 훑는 extractor + 스타일 세기 + 같은 모양 접기 + ref 고정
  spacing.py     기준 단위 추정, 간격·여백 분포, 스케일 밖, 반경·알약형
  typography.py  크기 단계, 일회용 크기, 붙어 있는 단계, 줄 높이 비율
  palette.py     사용량·면적·역할 추정, 거의 같은 색, 토큰 커버리지, 배경 합성
  rules.py       규칙 17종 + 등급 + 고치는 값
  audit.py       점수 · 보고 · 고치기 순서 · JSON
  designmd.py    DESIGN.md 다섯 칸 합성
  server.py      MCP 8툴 (stdio)
  cli.py         같은 일을 명령줄로 (종료 코드 포함)
  tokens.py      토큰 예산 어림
tests/           321 tests
examples/        demo before/after JSON + 실행 로그
reels/           릴스 생성기 (Pillow + ffmpeg) + 오디오
```

## 테스트

```bash
python -m pytest        # 321 passed
```

| 파일 | 개수 | 무엇을 못 박았나 |
|---|---|---|
| `test_color.py` | 54 | 13가지 색 표기, WCAG 대비 기준값(#777 = 4.48), 알파 합성, 색 이름 밴드(#EFF3FA 는 '선명'이 아니다), 제안 색 |
| `test_nodes.py` | 30 | 4가지 입력 모양, 상자 추정, 투명 칠, 그라디언트, 여러 겹 합성, 글자 스타일, 깨진 JSON |
| `test_walk.py` | 22 | ref 고정, 스타일 승격/인라인 경계, 같은 모양 접기, depth·max_nodes 고지, 모드별 출력 |
| `test_spacing.py` | 25 | 기준 단위 8가지 경우, 2보다 4를 고르는 이유, 여백 포함, 반경·알약형 경계 |
| `test_typography.py` | 11 | 크기 세기, 일회용, 붙어 있는 단계, 줄 높이 없음(추측 금지) |
| `test_palette.py` | 15 | 배경 조상 합성, 이미지 위 판정 불가, 역할 추정 4종, 거의 같은 색 조건, 토큰 커버리지 |
| `test_rules.py` | 65 | 규칙 17종 × **잡는 경우 + 놓아주는 경우**(거짓 양성 방지) |
| `test_audit.py` | 27 | 점수 공식(규칙당 한 번), 등급 경계, 정렬, 자르기, JSON, 고치기 순서 |
| `test_designmd.py` | 17 | 다섯 칸 구조, 색 표, 크기 사다리, 부품 3종, 기준 단위, 생성 표시 |
| `test_server.py` | 34 | 진짜 MCP 클라이언트(in-memory + **stdio 서브프로세스**)로 8툴, 경로 탈출 거부 |
| `test_cli.py` | 21 | 종료 코드 계약(0/1/2), 모든 하위 명령 |

## 라이선스

이 코드는 **MIT**. 원본 두 프로젝트는 **MIT**(Figma-Context-MCP)와 **Apache-2.0**(stitch-skills) 이며,
코드를 복사하지 않고 파이프라인 설계와 DESIGN.md 구조만 참고했습니다.
WCAG 조항 번호와 등급은 [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) 표기를 따릅니다.
