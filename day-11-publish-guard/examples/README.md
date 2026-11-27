# examples

| 파일 | 쓰는 곳 |
|---|---|
| `caption-before.txt` | AI 글투가 섞인 캡션 — 46/100, 보류 (`hook-vague-opener`, `hook-passive-promise`, 대구·나열·강조 조각) |
| `caption-after.txt` | 같은 숫자(1080·1920·-14·-1.0)를 남기고 문장만 고친 캡션 — 100/100 |
| `boxes.json` | 문구 상자 예시 — 하나는 일부러 상단 덮개(y=300)에 걸치게 두었다 |

```bash
publish-guard check --caption examples/caption-before.txt
publish-guard check --caption examples/caption-after.txt
publish-guard check reels-day11.mp4 --caption examples/caption-after.txt --boxes examples/boxes.json
```

`caption-before` → `caption-after` 는 `compare` 로 숫자·해시태그가 사라졌는지 확인하는 예시다.
`boxes.json` 은 `safe_zone_report` 가 "몇 px 옮기면 되는지"를 계산하는 모습을 보여준다.
