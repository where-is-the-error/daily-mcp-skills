# a11y-lens — 브라우저 없이 접근성 트리와 위반을 본다

**1일 1스킬 Day 04.** 공개된 MCP·에이전트 스킬 두 개를 골라 하나로 섞는 시리즈의 네 번째입니다.

> HTML 을 **접근성 트리**로 바꿔 보여 주고, **WCAG 조항**에 붙여 위반을 짚고,
> 고치는 순서와 **고친 뒤 확인**까지 한 줄로 잇습니다. 브라우저는 쓰지 않습니다.

```text
document "예제몰 – 로그인"
  link href="/"                    · ref=e1 · L10
    image                          · ref=e2 · L10      ← alt 없음
  heading "로그인" level=1         · ref=e4 · L14
  heading "회원" level=4           · ref=e5 · L15      ← h2 단계가 없다
  textbox type=email               · ref=e6 · L17      ← 이름이 없다
  button                           · ref=e8 · L20      ← 이름이 없다
```

```text
- 점수 **0/100** (심각) · 위반 **17건** (치명 6 · 심각 7 · 보통 4)

1. **image-alt** 이미지에 대체텍스트가 없습니다 — WCAG 1.1.1 (A)
   - 위치: `#top > a > img` · examples/demo/before.html:10
   - 마크업: `<img src="/img/logo.png">`
   - 왜: 화면 낭독기는 파일 이름을 읽거나 아무것도 읽지 않습니다. 정보가 담긴 이미지면 내용이 통째로 사라집니다.
   - 고치기: `<img src="logo.png" alt="회사 이름">   또는 장식이면  <img src="line.png" alt="">`
```

---

## 오늘 섞은 두 가지

| 원본 | 라이선스 | 무엇을 가져왔나 |
|---|---|---|
| [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) 의 [`a11y-debugging` 스킬](https://github.com/ChromeDevTools/chrome-devtools-mcp/tree/main/skills/a11y-debugging) | Apache-2.0 | **검사 항목과 순서** — "접근성 트리가 DOM 보다 정확한 기준", 제목 단계, 고아 입력(input↔label), 이름 없는 버튼·링크, 문서 수준 전역 점검, 그리고 *접근성 트리에 안 보이는 것(크기·색)은 별도로 재야 한다*는 구분 |
| [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | Apache-2.0 | **스냅샷 형식** — 접근성 트리를 글자로, 모든 노드에 `ref=e12`, `depth` 로 자르기, 스냅샷 안에서 글자·정규식으로 찾기(`browser_find`) |

- 두 저장소의 라이선스는 `gh repo view` 로 실제 확인했습니다(둘 다 `Apache License 2.0`, 2026-11-20 기준 각각 58.4k / 39.9k stars, 마지막 푸시 11-19 / 11-18).
- 두 프로젝트의 **코드는 한 줄도 복사하지 않았습니다.** 설계와 검사 항목만 가져와 Python 표준 라이브러리(`html.parser`)로 새로 구현했습니다.
- 툴 수: DevTools MCP 공개 툴 레퍼런스 **63개**, Playwright MCP **72개** → 이 서버 **7개**.

### 공개 툴은 브라우저에서, 이 서버는 파일에서

| | chrome-devtools-mcp | playwright-mcp | **a11y-lens** |
|---|---|---|---|
| 무엇을 보나 | 살아 있는 Chrome | 살아 있는 브라우저 | **파일·문자열 (정적)** |
| 기준 | DevTools a11y 트리 | Playwright a11y 스냅샷 | 같은 생각의 축약 트리 |
| 노드 참조 | `uid` | `ref=e12` | `ref=e12` (문서 순서 고정) |
| 색 대비·터치 크기 | 계산 가능 | 계산 가능 | **못 함 (한계에 명시)** |
| 원본 파일 줄 번호 | ✗ | ✗ | **✓ `L18`** |
| CI 종료 코드 | ✗ | ✗ | **✓ `audit` 1 / `verify` 1** |
| 다중 페이지 중복 묶기 | ✗ | ✗ | **✓ 지문(fingerprint)** |

브라우저가 필요한 일(색 대비, 탭 순서, 키보드 함정, JS 렌더링)은 원본 두 도구의 몫으로 남겨 두고,
이 서버는 **브라우저를 못 쓰는 자리**(CI, 커밋 훅, 서버 없는 편집기, 오프라인)를 맡습니다.

---

## 툴 7개

| 툴 | 하는 일 |
|---|---|
| `snapshot_page` | HTML → 접근성 트리 텍스트. `ref`·줄 번호·`depth`·`ref=eN` 하위 보기 |
| `find_in_snapshot` | 스냅샷에서 글자·정규식으로 노드 찾기 (`ref` + 루트부터의 경로) |
| `audit_page` | 한 페이지 검사 — WCAG 조항·등급·선택자·줄·마크업·고치는 법. `format="json"` |
| `audit_site` | 폴더 전체. 같은 템플릿의 반복 위반을 하나로 묶어 **몇 쪽에서 나는지** |
| `fix_plan` | 고치는 순서 — 치명 → 심각 → 보통, 같은 등급이면 여러 번 나온 것부터 |
| `verify_fixes` | `mode="save"` 로 기준선 저장 → 고친 뒤 `check` 로 **없어짐/남음/새로 생김** |
| `overview` | 규칙 목록과 **판정하지 않는 것** |

## 규칙 20종 (WCAG 2.2 A·AA)

| 규칙 | 내용 | WCAG | 등급 |
|---|---|---|---|
| `html-lang` | 문서 언어 없음·형식 오류 | 3.1.1 | A |
| `document-title` | 제목 없음/빈 제목 | 2.4.2 | A |
| `image-alt` | `img`·`input type=image`·`svg[role=img]` 이름 없음 | 1.1.1 | A |
| `button-name` | 버튼 이름 없음 (`title` 만이면 보통으로 낮춤) | 4.1.2 | A |
| `link-name` | 링크 이름 없음 | 2.4.4 | A |
| `link-vague` | "여기"·"더 보기" 만 있는 링크 | 2.4.4 | A |
| `form-label` | input·select·textarea 레이블 없음 (**placeholder 는 레이블이 아니다**) | 3.3.2 | A |
| `label-orphan` | `label for` 가 없는 id 를 가리킴 | 1.3.1 | A |
| `heading-skip` | 제목 단계 건너뜀 (h1 → h4) | 1.3.1 | A |
| `heading-empty` | 빈 제목 | 1.3.1 | A |
| `duplicate-id` | id 중복 | 4.1.1 | A |
| `aria-hidden-focus` | `aria-hidden` 안에 포커스 가능한 요소 | 4.1.2 | A |
| `tabindex-positive` | `tabindex > 0` | 2.4.3 | A |
| `iframe-title` | iframe `title` 없음 | 4.1.2 | A |
| `table-headers` | 데이터 표에 `th` 없음 (레이아웃 표면 힌트) | 1.3.1 | A |
| `viewport-zoom` | `user-scalable=no`·`maximum-scale=1` | 1.4.4 | **AA** |
| `main-landmark` | `main` 랜드마크 없음 | 1.3.1 | A |
| `bad-aria-ref` | `aria-labelledby`·`describedby` 가 없는 id | 4.1.2 | A |
| `bad-aria-controls` | `aria-controls` 가 없는 id (스크립트 생성 가능성 명시) | 4.1.2 | A |
| `invalid-role` | ARIA 표준에 없는 role 값 | 4.1.2 | A |

### 점수는 "몇 종류가 잘못됐나"

```
점수 = 100 − Σ(규칙별 감점)      치명 25 · 심각 12 · 보통 4
```

같은 규칙이 12번 나와도 **감점은 한 번**입니다. 반복은 "고칠 곳 하나"라는 신호이고,
점수는 "얼마나 여러 종류가 잘못됐는가"를 말해야 하기 때문입니다. 90+ 양호 · 70+ 주의 · 40+ 위험 · 그 아래 심각.

### 지문(fingerprint) — 페이지마다 다른 값은 무시한다

`id`·`class`·`href`·`src` 값은 지문에서 빼고, `role`·`type`·`scope`·`alt` 같은 **의미 있는 값과 글자**만 봅니다.
그래서 같은 템플릿에서 나온 위반은 12쪽에서 12번 나와도 **패턴 하나**로 묶입니다.
`verify_fixes` 도 이 지문으로 비교하므로, `src` 만 바뀐 이미지는 "새 위반"이 되지 않습니다.

## 스냅샷 형식

```text
document "제목" lang=ko          ← 문서 머리줄 (html 요소는 겹쳐 찍지 않는다)
  main
    heading "로그인" level=1 · ref=e4 · L14
      text "본문 글자"           ← 잎 노드가 아닌 컨테이너의 글자만 따로 (ref 없음)
    textbox "이메일" type=email required · ref=e6 · L17
```

- `ref` 는 **문서 순서로 고정** — `depth`·`max_nodes` 를 바꿔도 같은 파일이면 같은 번호가 나옵니다.
  그래서 "아까 그 버튼(`ref=e8`)을 고쳐서 다시 봐 줘"가 성립합니다.
- 이름이 곧 글자인 잎 노드(제목·링크·버튼·문단·셀)는 글자를 두 번 찍지 않습니다(토큰 절약).
- `aria-hidden`·`hidden`·`display:none` 은 트리에서 빠집니다 — 화면 낭독기가 보는 것과 같게.
- 이름 없는 `<form>`·`<section>` 은 랜드마크가 아니라서 트리에 안 나옵니다(자식만 올라옴). 이것이 DOM ≠ 접근성 트리.

## 실제 결과 (2026-11-20 실행)

| 페이지 | 점수 | 위반 | 눈에 띈 것 |
|---|---|---|---|
| [W3C WAI "Inaccessible" 데모](https://www.w3.org/WAI/demos/bad/before/home.html) | 0/100 | 51건 | alt 없음 · 아이콘 링크 이름 없음 · 표 머리글 없음 · lang 없음 |
| [W3C WAI "Accessible" 데모](https://www.w3.org/WAI/demos/bad/after/home.html) | 96/100 | 1건 | `main` 랜드마크만 없음 (HTML5 `main` 이전 문서라 사실과 맞음) |
| https://www.naver.com | 84/100 | 2건 | `<h1>` 이 배경 이미지라 비어 있음 · `aria-controls` 대상이 스크립트로 생김 |
| https://www.gov.kr/portal/main | 84/100 | 2건 | 자동 로그아웃 모달이 `aria-hidden` 인데 안에 포커스 요소 5개 |
| https://github.com/login | 100/100 | 0건 | 최신 페이지에서 거짓 양성 없음 |
| 예제 `before.html` → `after.html` | 0 → **100** | 17 → 0 | 고친 뒤 `verify`: 없어짐 17 · 남음 0 · 새로 생김 0 |

검사 시간은 페이지당 **0.08~0.23초**(1007요소 정부24 포함). 전체 로그: [examples/sample_output.md](examples/sample_output.md)

---

## 설치·실행

```bash
cd day-04-a11y-lens
pip install -e ".[dev]"

a11y-lens snapshot examples/demo/before.html --depth 3
a11y-lens audit    examples/demo/before.html --max-per-rule 2
a11y-lens audit    examples/demo                 # 폴더면 사이트 검사
a11y-lens plan     examples/demo/before.html    # 고치기 순서
a11y-lens rules    form-label                   # 규칙 하나 설명
```

### MCP 서버 (stdio)

```json
{
  "mcpServers": {
    "a11y-lens": {
      "command": "python",
      "args": ["-m", "a11y_lens.server"],
      "env": { "A11Y_LENS_ROOT": "/Users/me/project" }
    }
  }
}
```

- `mcp>=2.3,<3` 만 있으면 됩니다. 파서·규칙·보고는 전부 표준 라이브러리.
- `A11Y_LENS_ROOT` 를 주면 상대 경로가 그 폴더 기준이 됩니다.
- `A11Y_LENS_HOME` 은 기준선 JSON 을 두는 곳(기본 `~/.local/share/a11y-lens`).

### CI 에서

```bash
a11y-lens audit public/ || echo "치명·심각 위반이 있습니다"   # exit 1
a11y-lens verify index.html --baseline main                 # 새 위반이 생기면 exit 1
```

## 한계 (계산한 척하지 않는 것)

1. **색 대비·터치 타깃 크기·포커스 순서·키보드 함정은 판정하지 않습니다.** 레이아웃과 렌더링이 필요합니다.
   → 그 항목은 Chrome DevTools MCP / Playwright MCP 의 `a11y-debugging` 절차로 확인하세요.
2. **JS 로 그리는 내용은 정적 HTML 에 없으면 보이지 않습니다.** 빈 껍데기 SPA 는 "보이는 요소가 없습니다" 라고 말합니다.
3. `display:none` 은 **인라인 style·`hidden` 속성만** 알아봅니다. 외부 CSS 는 읽지 않습니다.
4. `::before`/`::after` 글자, shadow DOM, iframe 내부 문서, SVG 내부 구조는 보지 않습니다.
5. 접근성 이름은 **축약 accname** 입니다(`aria-labelledby` → `aria-label` → 네이티브 → `title`).
   `aria-labelledby` 계산에서 숨김 노드는 건너뜁니다.
6. 표 머리글 규칙은 `th` 의 **존재**만 봅니다. `scope`·`headers` 짝이 맞는지까지는 보지 않습니다.
7. 점수는 이 서버의 척도입니다. axe·Lighthouse 점수와 같은 숫자가 아닙니다.

## 파일

```text
a11y_lens/
  htmltree.py   관대한 HTML 파서 (+ euc-kr/cp949 자동 판별, 줄 번호)
  accname.py    축약 accname · 역할 · 포커스 가능 여부 · CSS 선택자
  snapshot.py   접근성 트리 → 텍스트 (ref 고정, depth, 잘림 고지)
  rules.py      규칙 20종 + 지문
  audit.py      점수 · 페이지/사이트 보고 · 고치기 순서
  store.py      기준선 저장·비교
  server.py     MCP 7툴 (stdio)
  cli.py        같은 일을 명령줄로 (종료 코드 포함)
tests/          308 tests
examples/       demo before/after + 실제 실행 로그
reels/          릴스 생성기 (Pillow + ffmpeg)
```

## 테스트

```bash
python -m pytest        # 308 passed
```

| 파일 | 개수 | 무엇을 못 박았나 |
|---|---|---|
| `test_htmltree.py` | 35 | 빈 요소·암묵적 닫힘·깨진 태그·엔티티·script 안의 `<div>`·줄 번호·cp949 |
| `test_accname.py` | 53 | 이름 계산 순서, 빈 alt, placeholder 는 이름이 아님, 랜드마크 조건, 포커스 판정 |
| `test_snapshot.py` | 26 | ref 고정, depth/max_nodes, 숨김 제외, 하위 보기, 잘림 고지 |
| `test_rules.py` | 89 | 규칙마다 **잡는 경우 + 놓아주는 경우**(거짓 양성 방지), 지문 규칙 |
| `test_audit.py` | 46 | 점수 공식, 사이트 묶음, 보고 형식, JSON |
| `test_store.py` | 18 | 기준선 저장·비교, 없어짐/남음/새로 생김, 경로 탈출 차단 |
| `test_server.py` | 24 | 진짜 MCP 클라이언트(in-memory + **stdio 서브프로세스**)로 7툴 호출 |
| `test_cli.py` | 18 | 종료 코드 계약(0/1/2) |

## 라이선스

이 코드는 **MIT**. 원본 두 프로젝트는 **Apache-2.0** 이며, 코드를 복사하지 않고 검사 항목·스냅샷 형식만 참고했습니다.
WCAG 조항 번호와 등급은 [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) 표기를 따릅니다.
