# 예제 — 같은 데이터, 다른 그림

검사기가 무엇을 잡는지 눈으로 비교하려고 만든 스펙 모음입니다. 값은 가상의 예제 데이터이고
(`examples/*.json`), 실제 공개 데이터 실측은 `tools/real_data.py` 가 합니다.

| 파일 | 형식 | 판정 | 걸리는 것 |
|---|---|---|---|
| `before.json` | guard JSON | **65/100 · 보류** | 축 하한 180(잘린 축) · 저대비 `#ff7f0e` · 글자 10px · 정렬 없음 · 출처·alt 없음 |
| `after.json` | guard JSON | **100/100 · 통과** | 없음 — 축 0, 파랑·주황, 14px, 값 순 정렬, 출처·alt |
| `pie-before.json` | guard JSON | **42/100 · 보류** | 조각 합계 93% · 9조각 · 1.1%(3.9°) 조각 · 무지개 · 순색 |
| `dual-axis-before.json` | guard JSON | **85/100 · 보류** | 두 y축(가입자·전환율)이 겹쳐 있음 |
| `vega-lite-before.json` | Vega-Lite v5 | **73/100 · 보류** | `scale.domain [600,1300]` 로 잘린 축 · 단위 없음 · 11px |
| `chartjs-before.json` | Chart.js | **65/100 · 보류** | `beginAtZero:false` 로 잘린 축 · Tableau 적록 두 색 · 제목 없음 |

## before → after 에서 실제로 달라지는 숫자

```
before.json   y축 하한 180 → 세종 210 vs 서울 1,240 이 화면에서 35.33배, 실제 5.90배 (과장 6.0배)
after.json    y축 하한 0   → 같은 두 막대의 길이비 5.90배 (화면 = 사실)
fix_plan      고친 스펙으로 다시 검사하면 100/100 — 잃은 범주 0 · 잃은 값 0
```

## 직접 돌려 보기

```bash
chart-guard check examples/before.json        # 65/100 · 보류 (종료 코드 2)
chart-guard distortion examples/before.json   # 화면 길이비 35.33배 vs 실제 5.90배
chart-guard fix examples/before.json > /tmp/fixed.json
chart-guard check /tmp/fixed.json             # 100/100 · 통과
chart-guard alt examples/after.json           # 125자 alt + 데이터 표
chart-guard compare examples/before.json examples/after.json
```

## 예제를 만들 때 지킨 것

- **값은 그대로** — `before.json` 과 `after.json` 은 같은 매출 값(억원)을 씁니다. 축·색·순서·글만 다릅니다.
- **원 그래프를 고칠 때** 상위 4개 + `기타` 로 묶고, 묶은 값의 합이 원래 합과 같은지 확인합니다(93.0 → 93.0).
- 실제 데이터가 아닌 예제는 `source` 에 `(가상)` 이라고 적었습니다. 출처를 지어내지 않습니다.
