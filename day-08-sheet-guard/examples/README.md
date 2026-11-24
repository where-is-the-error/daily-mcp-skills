# 예제 파일 — 일부러 넣은 오염 목록

`build_examples.py`가 같은 내용을 다시 만든다.

```bash
python3 examples/build_examples.py
```

## `raw_population.csv`

공공데이터포털에서 받은 주민등록 인구 CSV를 흉내 낸 파일. **CP949**(엑셀 기본 저장)로 저장했고,
아래를 일부러 넣었다. 각 항목은 `sheet-guard problems`에서 규칙 하나로 잡힌다.

| # | 넣은 것 | 어디 | 잡는 규칙 |
|---|---|---|---|
| 1 | CP949 인코딩 | 파일 전체 | `cp949-encoding` |
| 2 | 제목 줄 + `(단위: 명, 세대, ㎡)` | 1~2행 | `preamble-rows` |
| 3 | `소계` 행 3개(서울·경기·부산 끝) | r30·r45·r55 | `subtotal-row` |
| 4 | `※`, `출처:` 각주 2줄 | r56·r57 | `footnote-row` |
| 5 | 중간 빈 줄 | r52 | `blank-row` |
| 6 | 완전히 같은 행 1개(성동구) | r8 | `duplicate-rows` |
| 7 | 따옴표 없는 쉼표 `안양시, 동안구` | r38 | `ragged-row` |
| 8 | 천 단위 쉼표 `"132,456"` | 인구수·세대수 47칸 | `thousands-separator` |
| 9 | 날짜 표기 3종 `2024-09-30`·`2024.9.30`·`24.09.30` | 기준일 14칸 | `date-format-mixed` |
| 10 | 값 안의 단위 `23.91㎡` | 면적 47칸 | `unit-in-cell` |
| 11 | 앞자리 0 코드 `04389` | 우편번호 24칸 | `leading-zero-kept` |
| 12 | 전화번호에 `+82`·하이픈 없음 | 대표전화 일부 | `phone-inconsistent` |
| 13 | 전각 숫자 `１２０,334`, `＋　301` | r41 | `fullwidth-digit` |
| 14 | 앞뒤 공백 `" 화성시 "` | r41 | `whitespace-padding` |
| 15 | 숫자 열 안의 글자 `＋　301` | 증감 | `text-in-numeric-column` |

기대 결과(2026-11-24 기준):

```
치명 2 · 주의 9 · 참고 5
계획 10단계 → 값 157칸 · 뺀 행 8개(소계3·각주2·빈줄1·중복1·격리1) · 새 열 면적_단위
정리 후 46행 · 값 손실 0
```

`clean.ragged.csv`에는 칸이 밀린 r38이 **잘리지 않고** 그대로 남는다(10칸 + `초과1` 머리글).

## `merged_population.xlsx`

병합 칸이 있는 엑셀. 3행이 머리글, `C3:D3`을 `규모`로 병합, `A4:A6`·`A7:A9`를 시도로 병합,
11행이 `합계`.

| 잡히는 것 | 규칙 |
|---|---|
| 병합 칸의 빈 자리 3곳 | `merged-cell-gap` |
| 머리글 `규모`가 두 번 | `duplicate-header` |
| 맨 끝 `합계` 행 | `trailing-total` |
| `04530` 같은 앞자리 0 코드 | `leading-zero-kept` |

`clean_plan`의 `fill_down`은 병합 범위(`A4:A6` 등)를 펼쳐 `서울/서울/서울, 경기/경기/경기`로
채운다. 채운 칸은 모두 `changes`에 남는다.
