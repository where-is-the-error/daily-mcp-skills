# 실제 실행 로그 (a11y-lens 0.1.0)

아래 출력은 모두 실제 실행 결과를 그대로 붙인 것입니다. 예제 페이지는 `examples/demo/before.html`·`after.html`.

## 1. 스냅샷 — `a11y-lens snapshot examples/demo/before.html --depth 3`

```text
document "예제몰 – 로그인"
  link href="/" · ref=e1 · L10
    image · ref=e2 · L10
  link href="/cart" · ref=e3 · L11
  heading "로그인" level=1 · ref=e4 · L14
  heading "회원" level=4 · ref=e5 · L15
  textbox type=email · ref=e6 · L17
  text "비밀번호" · L18
  textbox type=password · ref=e7 · L19
  button · ref=e8 · L20
  paragraph "비밀번호를 잊으셨나요? 여기" · ref=e9 · L22
    text "비밀번호를 잊으셨나요?" · L22
    link "여기" href="/find" · ref=e10 · L22
  table · ref=e11 · L23
    row · ref=e12 · L24
      cell "상품" · ref=e13 · L24
      cell "가격" · ref=e14 · L24
    row · ref=e15 · L25
      cell "텀블러" · ref=e16 · L25
      cell "12,000원" · ref=e17 · L25
  iframe · ref=e18 · L27
  text "공지" · L29
  text "이벤트" · L30
  text "바로가기" · L31
```

## 2. 검사 — `a11y-lens audit examples/demo/before.html --max-per-rule 1`

```text
## a11y-lens · examples/demo/before.html
- 제목 "예제몰 – 로그인" · 요소 35개
- 점수 **0/100** (심각) · 위반 **15건** (치명 4 · 심각 7 · 보통 4)

### 치명
1. **button-name** 버튼에 이름이 없습니다 — WCAG 4.1.2 (A)
   - 위치: `#main > form > button` · examples/demo/before.html:20
   - 마크업: `<button type="submit">`
   - 내용: 접근성 이름이 없습니다 (아이콘만 있거나 빈 버튼).
   - 왜: 아이콘만 있는 버튼은 '버튼'이라고만 읽혀 무엇을 하는 버튼인지 알 수 없습니다.
   - 고치기: `<button type="button" aria-label="검색"><svg aria-hidden="true">…</svg></button>`
2. **form-label** 입력칸에 연결된 레이블이 없습니다 — WCAG 3.3.2 (A)
   - 위치: `#email` · examples/demo/before.html:17
   - 마크업: `<input id="email" placeholder="이메일" type="email">`
   - 내용: 레이블·aria-label·aria-labelledby 가 모두 없습니다. placeholder("이메일")만 있습니다 — placeholder 는 레이블이 아닙니다.
   - 왜: 이름이 없으면 화면 낭독기는 '편집'·'콤보 상자'라고만 읽습니다. placeholder 는 입력을 시작하면 사라지므로 레이블이 아닙니다.
   - 고치기: `<label for="email">이메일</label><input id="email" type="email" autocomplete="email">`
3. **image-alt** 이미지에 대체텍스트가 없습니다 — WCAG 1.1.1 (A)
   - 위치: `#top > a > img` · examples/demo/before.html:10
   - 마크업: `<img src="/img/logo.png">`
   - 내용: alt 속성이 아예 없습니다.
   - 왜: 화면 낭독기는 파일 이름을 읽거나 아무것도 읽지 않습니다. 정보가 담긴 이미지면 내용이 통째로 사라집니다.
   - 고치기: `<img src="logo.png" alt="회사 이름">   또는 장식이면  <img src="line.png" alt="">`
4. **link-name** 링크에 이름이 없습니다 — WCAG 2.4.4 (A)
   - 위치: `#top > a` · examples/demo/before.html:10
   - 마크업: `<a href="/">`
   - 내용: 접근성 이름이 없습니다 (아이콘만 있거나 빈 링크).
   - 왜: 링크 목록만 훑는 사용자는 이름 없는 링크를 고를 수 없습니다.
   - 고치기: `<a href="/notice">공지사항</a>   또는  <a href="/notice" aria-label="공지사항">…</a>`

### 심각
5. **aria-hidden-focus** aria-hidden 안에 포커스 가능한 요소가 있습니다 — WCAG 4.1.2 (A)
   - 위치: `#main > div` · examples/demo/before.html:28
   - 마크업: `<div aria-hidden="true">`
   - 내용: aria-hidden 안에 포커스 가능한 요소 1개 (<button type="button">).
   - 왜: Tab 키로는 닿는데 화면 낭독기는 읽지 않는 '보이지 않는 함정'이 됩니다.
   - 고치기: `aria-hidden="true" 를 지우거나, 안쪽 요소에 tabindex="-1" 을 준다`
6. **duplicate-id** id 가 중복됩니다 — WCAG 4.1.1 (A)
   - 위치: `#notice` · examples/demo/before.html:30
   - 마크업: `<div id="notice">`
   - 내용: id="notice" 이 문서에 2번 있습니다.
   - 왜: label for·aria-labelledby·앵커 이동이 첫 번째 요소만 가리켜, 두 번째 요소는 영영 이름을 못 받습니다.
   - 고치기: `<input id="email"> … <input id="email-2">   ← id 는 문서에서 하나`
7. **html-lang** 문서 언어가 없습니다 — WCAG 3.1.1 (A)
   - 위치: `html` · examples/demo/before.html:2
   - 마크업: `<html>`
   - 내용: lang 속성이 비어 있습니다.
   - 왜: 화면 낭독기가 어떤 발음 규칙으로 읽을지 몰라, 한국어 문서를 영어 발음으로 읽는 일이 생깁니다.
   - 고치기: `<html lang="ko">`
8. **iframe-title** iframe 에 title 이 없습니다 — WCAG 4.1.2 (A)
   - 위치: `#main > iframe` · examples/demo/before.html:27
   - 마크업: `<iframe src="https://map.example/embed">`
   - 내용: title 속성이 없습니다.
   - 왜: 화면 낭독기는 '프레임'이라고만 알려 줍니다. 무엇이 들어 있는지 알 수 없습니다.
   - 고치기: `<iframe src="…" title="지도: 서울시청">`
9. **label-orphan** label 의 for 가 가리키는 칸이 없습니다 — WCAG 1.3.1 (A)
   - 위치: `#main > form > label` · examples/demo/before.html:18
   - 마크업: `<label for="pw">`
   - 내용: for="pw" 에 해당하는 id 가 없습니다.
   - 왜: 오타이거나 id 가 지워진 상태입니다. 레이블과 입력칸이 화면 낭독기에서 따로 놉니다.
   - 고치기: `<label for="email">이메일</label><input id="email" type="email">   ← 두 id/for 를 맞춘다`
10. **table-headers** 표에 머리글 칸(th)이 없습니다 — WCAG 1.3.1 (A)
   - 위치: `#main > table` · examples/demo/before.html:23
   - 마크업: `<table>`
   - 내용: td 4개, th 0개.
   - 왜: 화면 낭독기는 셀을 읽을 때 머리글을 함께 읽어 주는데, 머리글이 없으면 '셀, 셀'만 들립니다.
   - 고치기: `<tr><th scope="col">이름</th><th scope="col">금액</th></tr>`
11. **viewport-zoom** 확대를 막고 있습니다 — WCAG 1.4.4 (AA)
   - 위치: `html > head > meta` · examples/demo/before.html:6
   - 마크업: `<meta content="width=device-width, initial-scale=1, user-scalable=no" name="viewport">`
   - 내용: content="width=device-width, initial-scale=1, user-scalable=no"
   - 왜: 저시력 사용자가 손가락으로 확대하지 못합니다. iOS 는 maximum-scale 도 무시하지만 안드로이드는 막힙니다.
   - 고치기: `<meta name="viewport" content="width=device-width, initial-scale=1">`

### 보통
12. **heading-skip** 제목 단계를 건너뛰었습니다 — WCAG 1.3.1 (A)
   - 위치: `#main > h4:nth-of-type(1)` · examples/demo/before.html:15
   - 마크업: `<h4>`
   - 내용: h1 다음에 h4 — h2, h3 이(가) 빠졌습니다.
   - 왜: 제목으로 문서 구조를 훑는 사용자는 h2 다음 h4 를 만나면 단계가 하나 사라진 것으로 읽습니다.
   - 고치기: `<h2>다음은 <h3> — 숫자를 하나씩만 올린다 (모양은 CSS 로)`
13. **link-vague** 링크 이름이 '여기'·'더 보기' 뿐입니다 — WCAG 2.4.4 (A)
   - 위치: `#main > p:nth-of-type(1) > a` · examples/demo/before.html:22
   - 마크업: `<a href="/find">`
   - 내용: 링크 이름이 "여기" 뿐입니다.
   - 왜: 링크만 모아 읽으면 전부 같은 이름이라 목적지를 구분할 수 없습니다. 조항 위반 여부는 문맥에 따라 판단이 필요합니다.
   - 고치기: `<a href="/notice">11월 공지사항 보기</a>`
14. **main-landmark** 본문 영역(main)이 없습니다 — WCAG 1.3.1 (A)
   - 위치: `html > body` · examples/demo/before.html:8
   - 마크업: `<body>`
   - 내용: main 요소도 role="main" 도 없습니다.
   - 왜: 화면 낭독기의 '본문으로 건너뛰기'가 없어, 페이지마다 머리글·메뉴를 다시 지나가야 합니다.
   - 고치기: `<main>본문</main>   또는  <div role="main">`
15. **tabindex-positive** tabindex 가 0 보다 큽니다 — WCAG 2.4.3 (A)
   - 위치: `#main > span` · examples/demo/before.html:31
   - 마크업: `<span tabindex="2">`
   - 내용: tabindex=2
   - 왜: Tab 순서가 DOM 순서와 어긋나, 화면에 보이는 순서와 키보드 이동 순서가 달라집니다.
   - 고치기: `tabindex="0" (또는 속성 제거) — 순서는 DOM 으로 만든다`

> 색 대비·터치 타깃 크기·포커스 순서·키보드 함정은 계산하지 않습니다 (레이아웃과 렌더링이 필요합니다). JS 로 그리는 내용은 정적 HTML 에 없으면 보이지 않습니다.
```

## 3. 고치기 순서 — `a11y-lens plan examples/demo/before.html`

```text
## 고치기 순서 · examples/demo/before.html
- 위반 17건 / 규칙 15종 · 지금 점수 **0/100** (심각)

**1. 입력칸에 연결된 레이블이 없습니다** — `form-label` · WCAG 3.3.2 (A) · 2건
   - 위치: L17, L19
   - 바꿀 모양: `<label for="email">이메일</label><input id="email" type="email" autocomplete="email">`
   - 확인: 같은 규칙의 위반이 0건이 되면 다음 단계로
**2. 링크에 이름이 없습니다** — `link-name` · WCAG 2.4.4 (A) · 2건
   - 위치: L10, L11
   - 바꿀 모양: `<a href="/notice">공지사항</a>   또는  <a href="/notice" aria-label="공지사항">…</a>`
   - 확인: 같은 규칙의 위반이 0건이 되면 다음 단계로
**3. 버튼에 이름이 없습니다** — `button-name` · WCAG 4.1.2 (A) · 1건
   - 위치: L20
   - 바꿀 모양: `<button type="button" aria-label="검색"><svg aria-hidden="true">…</svg></button>`
   - 확인: 같은 규칙의 위반이 0건이 되면 다음 단계로
**4. 이미지에 대체텍스트가 없습니다** — `image-alt` · WCAG 1.1.1 (A) · 1건
   - 위치: L10
   - 바꿀 모양: `<img src="logo.png" alt="회사 이름">   또는 장식이면  <img src="line.png" alt="">`
   - 확인: 같은 규칙의 위반이 0건이 되면 다음 단계로
**5. aria-hidden 안에 포커스 가능한 요소가 있습니다** — `aria-hidden-focus` · WCAG 4.1.2 (A) · 1건
   - 위치: L28
   - 바꿀 모양: `aria-hidden="true" 를 지우거나, 안쪽 요소에 tabindex="-1" 을 준다`
   - 확인: 같은 규칙의 위반이 0건이 되면 다음 단계로
**6. id 가 중복됩니다** — `duplicate-id` · WCAG 4.1.1 (A) · 1건
   - 위치: L30
   - 바꿀 모양: `<input id="email"> … <input id="email-2">   ← id 는 문서에서 하나`
   - 확인: 같은 규칙의 위반이 0건이 되면 다음 단계로
**7. 문서 언어가 없습니다** — `html-lang` · WCAG 3.1.1 (A) · 1건
   - 위치: L2
   - 바꿀 모양: `<html lang="ko">`
   - 확인: 같은 규칙의 위반이 0건이 되면 다음 단계로
**8. iframe 에 title 이 없습니다** — `iframe-title` · WCAG 4.1.2 (A) · 1건
   - 위치: L27
   - 바꿀 모양: `<iframe src="…" title="지도: 서울시청">`
   - 확인: 같은 규칙의 위반이 0건이 되면 다음 단계로

… 규칙 7종 더 (audit_page 로 전체 목록)

고친 뒤에는 `verify_fixes` 로 **없어진 것/남은 것/새로 생긴 것**을 확인하세요.
```

## 4. 고친 뒤 확인 — `verify --save` → `verify`

```text
💾 기준선 저장: /workspace/daily-mcp-skills/day-04-a11y-lens/../../.work/day04src/lenshome/demo.json
   examples/demo/before.html · 위반 17건 · 점수 0/100
## 고친 뒤 확인 · examples/demo/after.html
- 기준선 17건 → 지금 0건 (**−17**)
- 없어짐 **17** · 남음 **0** · 새로 생김 **0**

✅ 기준선의 위반이 모두 사라졌습니다. 이 상태를 새 기준선으로 저장해 두세요.

### 없어짐 (17)
- 치명 · `button-name` · `#main > form > button` · examples/demo/before.html:20
- 치명 · `form-label` · `#email` · examples/demo/before.html:17
- 치명 · `form-label` · `#password` · examples/demo/before.html:19
- 치명 · `image-alt` · `#top > a > img` · examples/demo/before.html:10
- 치명 · `link-name` · `#top > a` · examples/demo/before.html:10
- 치명 · `link-name` · `#top > a` · examples/demo/before.html:11
- 심각 · `aria-hidden-focus` · `#main > div` · examples/demo/before.html:28
- 심각 · `duplicate-id` · `#notice` · examples/demo/before.html:30
- 심각 · `html-lang` · `html` · examples/demo/before.html:2
- 심각 · `iframe-title` · `#main > iframe` · examples/demo/before.html:27
- 심각 · `label-orphan` · `#main > form > label` · examples/demo/before.html:18
- 심각 · `table-headers` · `#main > table` · examples/demo/before.html:23
- … 5건 더

> 기준선 저장 시각: 2026-11-20T00:03:39+00:00
```

## 5. 사이트 전체 — `a11y-lens audit examples/demo`

```text
## a11y-lens · 사이트 검사 — examples/demo
- 페이지 **2쪽** · 위반 **17건** (치명 6 · 심각 7 · 보통 4)
- 점수: 최저 **0** · 평균 **50** · 90점 이상 1쪽

| 위반 패턴 | 건수 | 쪽 수 | 대표 위치 |
|---|---|---|---|
| 치명 · `link-name` 링크에 이름이 없습니다 | 2 | 1 | `#top > a` · before.html:10 |
| 치명 · `button-name` 버튼에 이름이 없습니다 | 1 | 1 | `#main > form > button` · before.html:20 |
| 치명 · `form-label` 입력칸에 연결된 레이블이 없습니다 | 1 | 1 | `#email` · before.html:17 |
| 치명 · `form-label` 입력칸에 연결된 레이블이 없습니다 | 1 | 1 | `#password` · before.html:19 |
| 치명 · `image-alt` 이미지에 대체텍스트가 없습니다 | 1 | 1 | `#top > a > img` · before.html:10 |
| … 패턴 11개 더 | | | |

### 쪽별 점수 (낮은 순)
- **0** 심각 · `before.html` · 위반 17건
- **100** 양호 · `after.html` · 위반 0건

> 색 대비·터치 타깃 크기·포커스 순서·키보드 함정은 계산하지 않습니다 (레이아웃과 렌더링이 필요합니다). JS 로 그리는 내용은 정적 HTML 에 없으면 보이지 않습니다.
```

## 6. 남의 사이트에도 (2026-11-20 실제 확인)

| 페이지 | 점수 | 위반 | 눈에 띈 것 |
|---|---|---|---|
| [W3C WAI "Inaccessible" 데모](https://www.w3.org/WAI/demos/bad/before/home.html) | 0/100 | 51건 | 이미지 alt 없음 · 아이콘 링크 이름 없음 · 표 머리글 없음 · lang 없음 |
| [W3C WAI "Accessible" 데모](https://www.w3.org/WAI/demos/bad/after/home.html) | 96/100 | 1건 | `main` 랜드마크만 없음 (2010년 이전 문서라 HTML5 `main` 이전) |
| https://www.naver.com | 84/100 | 2건 | `<h1>` 이 배경 이미지라 비어 있음 · `aria-controls` 대상이 스크립트로 생김 |
| https://www.gov.kr/portal/main | 84/100 | 2건 | 자동 로그아웃 모달이 `aria-hidden` 인데 안에 포커스 요소 5개 |
| https://github.com/login | 100/100 | 0건 | 거짓 양성 없음 |

> 전부 로컬 파일로 내려받아 검사했습니다(curl). 검사 시간은 페이지당 0.08~0.23초.
