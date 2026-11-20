# design-spec 실행 로그 (2026-11-21)

`examples/demo/before.json` 은 일부러 만든 문제 파일, `after.json` 은 고친 파일입니다.

## 1. 트리 읽기

```bash
design-spec read examples/demo/before.json
```

```text
document "예제몰 – 주문/결제 (before)" · 화면 1개 · 노드 34개 · 텍스트 14개 · 모드 all
document "Page 1" · ref=e1
  canvas "Page 1" · ref=e2
    frame "Checkout / Mobile" 390×844 · s3 · ref=e3
      frame "Header" 390×64 · ref=e4
        instance "Icon/Back" 24×24 · stroke #111827 2 · r4 · ref=e5
        text "주문/결제" 20px/700/lh 24 · 120×24 · fill #111827 · “주문/결제” · ref=e6
        instance "Icon/Cart" 24×24 · stroke #111827 2 · ref=e7
      frame "Body" 390×700 · ref=e8
        frame "Card/Order" 342×120 · fill #F9FAFB · stroke #EEF0F3 1 · r12 · ref=e9
          text "총 결제 금액" 15px/600/lh 22 · 120×22 · fill #6B7280 · “총 결제 금액” · ref=e10
          text "39,800원" 20px/700/lh 28 · 140×32 · fill #111827 · “39,800원” · ref=e11
          text "금액 안내" 13px/400/lh 14 · 220×26 · fill #9AA0A6 · “결제 금액은 배송비와 할인을 모두 반영한 금액입니다” · ref=e12
        frame "Card/Coupon" 342×96 · fill #FFFFFF · stroke #EEF0F3 1 · r12 · ref=e13
          text "쿠폰" 15px/600/lh 22 · 40×22 · fill #111827 · “쿠폰” · ref=e14
          text "쿠폰 안내" 13px/400/lh 18 · 160×20 · “적용 가능한 쿠폰 2장” · s2 · ref=e15
          text "쿠폰 설명" 13px/400/lh 18 · 380×18 · “쿠폰을 선택하면 할인이 적용됩니다. 자세한 내용은 쿠폰함에서 확인하세요.” · s2 · ref=e16
        frame "List/Items" 342×180 · ref=e17
          frame "Item/이어폰" 310×40 · ref=e18
            text "무선 이어폰" 15px/400/lh 22 · 140×22 · “무선 이어폰” · s1 · ref=e19
            text "품절 배지" 11px/700/lh 12 · 48×22 · fill #D92D20 · “품절” · ref=e20
          frame "Item/케이스" 310×40 · ref=e21
            text "휴대폰 케이스" 15px/400/lh 22 · 140×22 · “휴대폰 케이스” · s1 · ref=e22
          frame "Item/충전기" 310×40 · ref=e23
            text "충전기" 15px/400/lh 22 · 100×22 · “충전기” · s1 · ref=e24
        frame "Frame 12" 342×60 · fill #FFFFFF · r10 · ref=e25
          rectangle "Rectangle 5" 342×60 · fill #F2F4F7 · r10 · ref=e26
          text "쿠폰 받기" 17px/600/lh 20 · 80×20 · fill #0A5CFF · “쿠폰 받기” · ref=e27
      frame "BottomBar" 390×60 · s3 · ref=e28
        frame "Button/Pay" 250×32 · fill #0057FF · r8 · ref=e29
          text "결제 라벨" 16px/700/lh 20 · 100×20 · fill #FFFFFF · “39,800원 결제” · ref=e30
        frame "Button/Coupon" 96×32 · fill #FFFFFF · stroke #0057FF 1 · r8 · ref=e31
          text "쿠폰 버튼 라벨" 16px/600/lh 20 · 36×20 · fill #0057FF · “쿠폰” · ref=e32
        frame "Frame 7" 358×4 · fill #EEF0F3 · ref=e33
          rectangle "Rectangle 9" 40×4 · fill #6B7280 · r2 · ref=e34

## 반복 스타일 (두 노드 이상에서 쓰임 — 숫자가 쓰인 횟수)
s1 ×3 · fill #111827 · 글자 15px/400/Pretendard/lh 22
s2 ×2 · fill #6B7280 · 글자 13px/400/Pretendard/lh 18
s3 ×2 · fill #FFFFFF
```

## 2. 글자만 보기

```bash
design-spec read examples/demo/before.json --mode text --depth 4
```

```text
document "예제몰 – 주문/결제 (before)" · 화면 1개 · 노드 34개 · 텍스트 14개 · 모드 text
document "Page 1" · ref=e1
  canvas "Page 1" · ref=e2
    frame "Checkout / Mobile" 390×844 · ref=e3
      frame "Header" 390×64 · ref=e4
      frame "Body" 390×700 · ref=e8
      frame "BottomBar" 390×60 · ref=e28
  … 깊이 제한으로 3곳에서 멈췄습니다 (depth=0 이면 무제한)
```

## 3. 색

```bash
design-spec palette examples/demo/before.json
```

```text
# 예제몰 – 주문/결제 (before) · 색 10종
#FFFFFF  ×6   surface   5.52:1     410984px²
#F9FAFB  ×1   surface        -      41040px²
#F2F4F7  ×1   surface        -      20520px²
#111827  ×8   text     16.96:1      16612px²
#6B7280  ×4   text      4.62:1      12840px²
#0057FF  ×3   surface   5.52:1       8751px²
#9AA0A6  ×1   text      2.53:1       5720px²
#EEF0F3  ×3   border         -       2171px²
#0A5CFF  ×1   text      5.26:1       1600px²
#D92D20  ×1   text      4.83:1       1056px²

## 거의 같은 색
```

## 4. 간격

```bash
design-spec scale examples/demo/before.json --kind spacing
```

```text
# 간격 · 기준 4px (75%) · 7종
    16  █████████  ×9
    24  ████  ×4
    10  ██  ×2
    20  ██  ×2
     8  █  ×1
    12  █  ×1
    13  █  ×1
  스케일 밖: 10 (2곳)
  스케일 밖: 13 (1곳)
```

## 5. 글자

```bash
design-spec scale examples/demo/before.json --kind type
```

```text
# 글자 · 6단계 · 글꼴 1종
    20px  ×2
    17px  ×1
    16px  ×2
    15px  ×5
    13px  ×3
    11px  ×1
붙어 있는 단계: 15→16 (×1.07), 16→17 (×1.06)
한 번만 쓰인 크기: 17px, 11px
```

## 6. 검사 (before)

```bash
design-spec audit examples/demo/before.json --max-per-rule 1
```

```text
# design-spec · 예제몰 – 주문/결제 (before)  (examples/demo/before.json)

- 화면 1개 · 노드 34개 · 글자 14개 · 색 10종 · 크기 6단계 · 간격 값 7종 (기준 4px)
- 점수 **0/100** (심각) · 위반 **17건** (치명 6 · 심각 2 · 보통 9) · 규칙 12종

## 위반 (무거운 것부터)

1. **contrast-text** 글자 대비 2.53:1 (필요 4.5:1) — 치명
   - `e12` Body > Card/Order > 금액 안내
     근거: #9AA0A6 on #F9FAFB · 13.0px
     고치기: #6F7378 로 바꾸면 4.56:1

2. **layout-collision** 글자 "무선 이어폰" 와 "품절" 가 91% 겹칩니다 — 치명
   - `e19` List/Items > Item/이어폰 > 무선 이어폰
     근거: e19 140×22 · e20 48×22
     고치기: 한쪽을 옮기거나 폭을 줄이세요. 겹친 글자는 둘 다 읽을 수 없습니다

3. **touch-target** 누를 수 있는 요소가 250×32 — 최소 44×44 — 치명
   - `e29` Checkout / Mobile > BottomBar > Button/Pay
     근거: 이름에 "button" 가 들어가 누를 것으로 봤습니다
     고치기: 상자를 44×44 이상으로 (보이는 크기는 그대로, 누르는 영역만 넓혀도 됨)
   - … 3곳 더 (max_per_rule 로 늘릴 수 있습니다)

4. **layout-overflow** 부모 "Card/Coupon" 밖으로 오른쪽 62px 나갑니다 (부모가 잘라내도록 설정됨) — 심각
   - `e16` Body > Card/Coupon > 쿠폰 설명
     근거: 부모 342×96 · 자식 380×18
     고치기: 부모 크기를 늘리거나 자식의 폭·위치를 부모 안으로

5. **type-line-cramped** 줄 높이 14px / 글자 13px = 1.08 — 심각
   - `e12` Body > Card/Order > 금액 안내
     근거: "결제 금액은 배송비와 할인을 모두 반영한 …" (28자 — 여러 줄로 흐를 수 있음)
     고치기: 줄 높이를 20px 근처로 (비율 1.15 이상)

6. **color-hardcoded** 칠한 노드 10개 중 스타일(토큰)을 쓰는 것 4개 — 40% — 보통
   - `e9` Checkout / Mobile > Body > Card/Order
     근거: 색을 직접 넣으면 나중에 한 곳만 바뀌어 색이 갈라집니다
     고치기: Figma 색 스타일(또는 변수)을 만들고 칠을 그것으로 바꾸세요

7. **layout-misaligned** 같은 크기(310×40) 형제 3개가 가로 위치 1px 어긋남 — 보통
   - `e21` Body > List/Items > Item/케이스
     근거: "List/Items" 안
     고치기: auto-layout 에 맡기세요 — 1px 어긋남은 눌러도 모르고, 나중에 제일 먼저 보입니다

8. **naming-default** 이름이 기본값("Frame 12" 같은)인 노드 4개 — 보통
   - `e25` Checkout / Mobile > Body > Frame 12
     근거: "Frame 12", "Rectangle 5", "Frame 7", "Rectangle 9"
     고치기: 역할로 이름을 붙이세요 (Button/Primary, Card/Product). 이름이 곧 컴포넌트 후보입니다

9. **radius-too-many** 모서리 반경이 5종류 — 3종 이하 권장 — 보통
   - 예제몰 – 주문/결제 (before)
     근거: 2, 4, 8, 10, 12
     고치기: 작은 것(4~8)·중간(12~16)·알약형 셋으로 줄이세요

10. **spacing-off-scale** 10px — 기준 4px 의 배수가 아님 (2곳) — 보통
   - `e28` Checkout / Mobile > BottomBar
     근거: 간격 값 20개 중 75% 가 4의 배수
     고치기: 가까운 8px 로
   - … 1곳 더 (max_per_rule 로 늘릴 수 있습니다)

11. **type-one-off** 11px 는 이 화면에서 한 번만 쓰였습니다 — 보통
   - `e20` List/Items > Item/이어폰 > 품절 배지
     근거: "품절"
     고치기: 가까운 단계 13px 로
   - … 1곳 더 (max_per_rule 로 늘릴 수 있습니다)

12. **type-too-many-sizes** 글자 크기가 6단계 — 5단계 이하 권장 — 보통
   - 예제몰 – 주문/결제 (before)
     근거: 20, 17, 16, 15, 13, 11
     고치기: 본문·보조·제목·큰제목 정도로 줄이고 나머지는 굵기로 구분하세요
```

## 7. 고치기 순서

```bash
design-spec plan examples/demo/before.json --max-steps 4
```

```text
# 고치기 순서 · 예제몰 – 주문/결제 (before)

- 점수 0/100 (심각) · 규칙 12종 · 위반 17건

1. **touch-target** (치명 · 4곳) — 누를 수 있는 요소가 250×32 — 최소 44×44
   - 바꿀 것: 상자를 44×44 이상으로 (보이는 크기는 그대로, 누르는 영역만 넓혀도 됨)
   - 첫 곳: `e29` Checkout / Mobile > BottomBar > Button/Pay
2. **contrast-text** (치명 · 1곳) — 글자 대비 2.53:1 (필요 4.5:1)
   - 바꿀 것: #6F7378 로 바꾸면 4.56:1
   - 첫 곳: `e12` Body > Card/Order > 금액 안내
3. **layout-collision** (치명 · 1곳) — 글자 "무선 이어폰" 와 "품절" 가 91% 겹칩니다
   - 바꿀 것: 한쪽을 옮기거나 폭을 줄이세요. 겹친 글자는 둘 다 읽을 수 없습니다
   - 첫 곳: `e19` List/Items > Item/이어폰 > 무선 이어폰
4. **layout-overflow** (심각 · 1곳) — 부모 "Card/Coupon" 밖으로 오른쪽 62px 나갑니다 (부모가 잘라내도록 설정됨)
   - 바꿀 것: 부모 크기를 늘리거나 자식의 폭·위치를 부모 안으로
   - 첫 곳: `e16` Body > Card/Coupon > 쿠폰 설명
… 8종 더

> 고친 뒤 같은 명령을 다시 돌려 점수가 올랐는지 확인하세요.
```

## 8. 검사 (after)

```bash
design-spec audit examples/demo/after.json
```

```text
# design-spec · 예제몰 – 주문/결제 (after)  (examples/demo/after.json)

- 화면 1개 · 노드 31개 · 글자 14개 · 색 6종 · 크기 4단계 · 간격 값 4종 (기준 4px)
- 점수 **100/100** (양호) · 위반 없음
```

## 9. DESIGN.md

```bash
design-spec design-md examples/demo/after.json
```

```text
# Design System: 예제몰 – 주문/결제 (after)

**Source:** `examples/demo/after.json`  ·  **Screens:** 1  ·  **Nodes:** 31  ·  **Score:** 100/100 (양호)

> 이 문서는 `design-spec` 이 디자인 파일에서 **자동으로 뽑은** 것입니다. 색 이름과 역할은 계산으로 추정했으니, 브랜드 이름과 의도는 사람이 고쳐 주세요.

## 1. Visual Theme & Atmosphere

**여유 있는(Airy) · 각진 편(Sharp) · 그림자 없음(Flat).** 화면 1개에 노드 31개(화면당 약 31개), 글자 14개.

- 밀도: 여유 있는(Airy) — 화면당 노드 31개를 기준으로 판단했습니다.
- 모양: 각진 편(Sharp) — 가장 흔한 반경 8px.
- 깊이: 그림자 없음(Flat) — 경계는 선과 색으로만.
- 색: 포인트 색은 Vivid Blue #0057FF.

## 2. Color Palette & Roles

| 이름 | 값 | 역할 | 쓰인 곳 | 최악 대비 |
|---|---|---|---|---|
| Pure White | `#FFFFFF` | 배경·카드 | 6곳 | 5.52:1 |
| Off-White | `#EFF3FA` | 배경·카드 | 1곳 | — |
| Slate Gray | `#6B7280` | 보조 글자 | 5곳 | 4.83:1 |
| Ink Black | `#111827` | 본문 글자 | 8곳 | 17.74:1 |
| Vivid Blue | `#0057FF` | 주요 동작 | 4곳 | 4.96:1 |
| Light Gray | `#D0D5DD` | 선·구분 | 2곳 | — |

> 이름은 브랜드 이름이 아니라 **색상·채도·밝기**로 지은 것입니다. 역할은 면적·빈도·이름(Button 등)으로 추정했습니다.

## 3. Typography Rules

- 글꼴: Pretendard
- 굵기: 400, 600, 700

| 단계 | 크기 | 쓰인 곳 | 역할(추정) |
|---|---|---|---|
| 1 | 20px | 2곳 | 제목 |
| 2 | 16px | 3곳 | 부제목 |
| 3 | 14px | 5곳 | 본문 |
| 4 | 12px | 4곳 | 보조 |

- 줄 높이: 평균 1.46배 (가장 좁은 1.40배 · 가장 넓은 1.50배)

## 4. Component Stylings

* **Buttons:**
  가장 흔한 높이 48px · 반경 8px · 3개. 대표 버튼 "Button/Pay" 250×48, 칠 #0057FF, 글자 대비 5.52:1.
* **Cards/Containers:**
  반경 12px · 칠 #FFFFFF · 선 3개 · 그림자 0개 (5개 컨테이너 기준).
* **Inputs/Forms:**
  입력 필드로 이름 붙은 노드를 찾지 못했습니다.

## 5. Layout Principles

- 기준 단위 **4px** — 간격 값 20개 중 100%가 이 값의 배수입니다.
- 자주 쓰는 간격: 16×12, 24×4, 12×3, 8×1
- 여백(padding): 16×10, 24×4, 12×2
- auto-layout 사용: 컨테이너 15개 중 4개 (27%)
- 화면 크기: 390×844
```

