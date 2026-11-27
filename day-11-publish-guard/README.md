# publish-guard

올리기 전 약 2초, **파일과 글을 같은 자리에서** 검사하는 MCP 서버.

- 파일은 `ffprobe` 로 재고 (`ebur128` 음량·트루피크, `silencedetect` 앞뒤 무음) 플랫폼 규격에 건다.
- 글은 첫 줄·해시태그·AI 글투 21종으로 읽고, 고칠 때 **숫자·링크·해시태그가 사라지면 먼저 알린다**.
- 영상을 고치지 않는다. ffmpeg 명령은 **문자열로만** 만들고 실행하지 않는다.

```
$ publish-guard check reels-day11.mp4 --caption instagram-caption.md --section auto

판정: 통과 (100/100)
  막음 0 · 주의 0 · 참고 1 · 상자 0개
```

---

## 왜 이 둘을 붙였나

편집이 끝난 영상은 **업로드 버튼 앞에서** 두 번 실패한다.

1. **파일** — 길이·해상도·음량·피크가 플랫폼 규격 밖이다. 소리가 크면 플랫폼이 줄이고, 넘은 피크는 이미 찌그러진 채로 올라간다.
2. **글** — 캡션이 상한을 넘어 잘리고, 첫 줄이 1.5초 안에 읽히지 않고, 문장이 모델 냄새를 풍긴다.

도구 하나가 파일을, 다른 하나가 글을 보면 "어느 쪽 때문에 안 올라갔는지"를 사람이 다시 맞춰야 한다. `publish-guard` 는 둘을 한 점수로 묶고, **고치기 순서**를 막는 것부터 준다.

## 무엇을 재는가

| 축 | 재는 것 | 방법 |
|---|---|---|
| 파일 | 길이 · 해상도 · fps · 코덱 · 픽셀 포맷 · 파일 크기 · 회전 | `ffprobe -show_streams -show_format` |
| 소리 | 통합 음량(LUFS) · 트루피크(dBTP) · 앞뒤 무음 | `ffmpeg -af ebur128=peak=true`, `silencedetect` |
| 화면 | 선언된 문구 상자가 상단·하단·우측 버튼 영역과 겹치는지, 몇 px 옮기면 되는지 | 사각형 교차 계산 |
| 훅 | 첫 줄 길이 · 인사/예고 시작 · 숫자·비교 유무 · 캡션과 중복 | 규칙 7종 |
| 캡션 | 길이 상한 · 해시태그 상한/아무 태그 · 링크 · 첫 줄 · 이모지 · 키워드 위치 · AI 글투 | 규칙 31종 (AI 글투 21종) |

**규칙 64종** — 파일 24 · 화면 2 · 훅 7 · 캡션 31.

AI 글투는 **강한 신호와 약한 신호**를 나눈다. `'단순히 X가 아니라 Y'`, `결론적으로`, `도움이 되셨길` 같은 강한 신호는 한 번만 봐도 고친다. `다양한`, `매우`, 대시 반복 같은 약한 신호는 **둘 이상 겹칠 때만** 고친다 — 짧은 캡션에서 하나 걸렸다고 다 뜯으면 사람 말투가 사라진다.

## 설치

```bash
pip install -e .            # mcp>=2.3
publish-guard-mcp           # stdio MCP
```

`ffmpeg`·`ffprobe` 가 PATH 에 있어야 한다. 없으면 `PUBLISH_GUARD_FFMPEG` / `PUBLISH_GUARD_FFPROBE` 로 지정한다.

```json
{"mcpServers": {"publish-guard": {
  "command": "python", "args": ["-m", "publish_guard.server"],
  "env": {"PUBLISH_GUARD_ROOT": "/path/to/videos"}}}}
```

## 툴 10개

| 툴 | 하는 일 |
|---|---|
| `read_media` | 영상을 재서 사실을 돌려준다 (길이·해상도·fps·코덱·크기·음량·트루피크·앞뒤 무음) |
| `read_caption` | 캡션을 읽는다 (첫 줄·훅·해시태그·멘션·링크·길이·언어). `section="auto"` 면 `## 본문`+`## 해시태그` 구역 |
| `delivery_report` | 파일만 플랫폼 규격에 건다 |
| `safe_zone_report` | 문구 상자 JSON 을 안전 영역에 걸고 **최소 이동 px** 을 계산한다 |
| `hook_report` | 첫 1.5초 훅만 판정한다 |
| `copy_report` | 캡션만 판정한다 |
| `publish_check` | 파일·화면·훅·캡션을 한 번에 → 점수·판정·고치기 순서 |
| `compare_reports` | 두 검사의 점수 변화, 고쳐진/남은 규칙, **잃은 숫자·해시태그·링크** |
| `rule_catalog` | 규칙 64종과 각 규칙이 보는 것 |
| `overview` | 이 서버가 무엇을 하고 무엇을 판정하지 않는지 |

툴 이름은 도구가 아니라 **하는 일**이다. 같은 이유로 출력은 항상 "재지 못한 것"과 "판정하지 않는 것"으로 끝난다.

## CLI

```bash
publish-guard media reels.mp4                      # 파일 사실만
publish-guard caption caption.md --section auto    # 캡션만
publish-guard check reels.mp4 --caption caption.md --boxes boxes.json
publish-guard check reels.mp4 --caption caption.md --json --save before.json
publish-guard compare before.json after.json       # 30 → 100, 잃은 사실
publish-guard rules true-peak-over
```

종료 코드: `0` 통과 · `1` 사용 오류 · `2` 보류 · `3` 수정 후 발행.

## 원본 두 개

둘 다 **MIT**, 원본 코드는 한 줄도 복사하지 않았다. 설계와 태도만 가져와 이 문제에 맞게 다시 썼다.

| 원본 | 확인한 값 | 가져온 것 |
|---|---|---|
| [kajisho5/ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) | MIT · ★11,505 · 2026-11-26 · Python · 툴 42개 | `probe → edit → verify` (고친 뒤 다시 잰다) · 플랫폼 export preset 과 **safe area** · machine-readable contract(툴 스키마를 코드에서 파생) · "편집하는 툴이 무엇이 좋은지 정하지 않는다" |
| [blader/humanizer](https://github.com/blader/humanizer) | MIT · ★73,982 · 2026-11-19 · SKILL.md 504줄 | 번호가 붙은 **26가지 AI 글투** · 강한 신호는 한 번에, 약한 신호는 겹칠 때 · **사실(숫자·인용·날짜) 보존 검사** · "고친 글 + 살아남은 신호 + 최종본" 순서 |

`ffmpeg-skill` 은 영상 편집기이고, `humanizer` 는 글 편집 스킬이다. 이 서버는 **어느 쪽도 편집하지 않는다** — 발행 전에 재고, 고칠 명령과 문장만 제안한다.

## 실제로 잰 값 (2026-11-27)

`tools/audit.py` — 이 저장소의 릴스 10편 + 공개 표본 3편.

| 파일 | 길이 | 해상도 | LUFS | 피크 | 점수 | 판정 |
|---|---|---|---|---|---|---|
| reels-day01.mp4 | 21.5s | 1080×1920 | -11.8 | +0.5 | 68 | 보류 |
| reels-day02.mp4 | 21.5s | 1080×1920 | -11.7 | -0.9 | 68 | 보류 |
| reels-day03.mp4 | 21.5s | 1080×1920 | -11.8 | -1.3 | 80 | 수정 |
| reels-day04.mp4 | 21.5s | 1080×1920 | -11.8 | -1.3 | 80 | 수정 |
| reels-day05.mp4 | 21.5s | 1080×1920 | -11.7 | +0.1 | 68 | 보류 |
| reels-day06.mp4 | 21.5s | 1080×1920 | -11.9 | -1.1 | 80 | 수정 |
| reels-day07.mp4 | 21.5s | 1080×1920 | -11.5 | -0.5 | 68 | 보류 |
| reels-day08.mp4 | 21.5s | 1080×1920 | -11.8 | **+2.8** | 68 | 보류 |
| reels-day09.mp4 | 21.5s | 1080×1920 | -11.7 | -0.2 | 68 | 보류 |
| reels-day10.mp4 | 21.5s | 1080×1920 | -11.7 | -0.2 | 68 | 보류 |
| roman.webm (위키미디어) | 18.1s | 1080×1920 | -12.7 | +0.5 | 77 | 보류 |
| flagpole.webm (위키미디어) | 16.1s | 1080×1920 | — | — | 90 | 수정 |
| bbb.mp4 (test-videos) | 10.0s | 1920×1080 | — | — | 41 | 보류 |

- **피크 초과 8/13** · 목표보다 큰 소리 10/13 · 오디오 없음 2 · **가로 영상 1편은 Shorts 로 분류되지 않는다**.
- 우리 릴스 10편 중 **7편**이 `-1.0 dBTP` 를 넘었다. 가장 큰 것은 `+2.8 dBTP` (day-08).
- 캡션 10편: **2,200자 초과 4편** (최대 2,994자) · **첫 줄 18자 초과 10편** · 5개 초과 해시태그 10편.

`tools/demo.py` — 어제 편과 오늘 편.

```
Day 10 (test-radar):    30/100 · 보류   true-peak-over, caption-too-long ×2
Day 11 (publish-guard): 100/100 · 통과  상자 10개 · -15.1 LUFS · -2.0 dBTP
캡션 고치기 예시: 46 → 100 · 숫자 잃음 없음 · AI 신호 5 → 0
```

day-10 파일을 고치는 명령은 도구가 만든 그대로다.

```bash
ffmpeg -i reels-day10.mp4 -af loudnorm=I=-14:TP=-1.5:LRA=11 \
       -c:v copy -c:a aac -b:a 192k reels-day10-fixed.mp4
# 실측: -14.1 LUFS · -1.7 dBTP (측정값은 파일마다 다르다)
```

## 안전

- **읽기 전용** — 영상을 고치지 않고, 업로드하지 않고, 네트워크로 아무것도 보내지 않는다.
- **명령은 문자열** — `ffmpeg` 명령을 만들어 보여줄 뿐 실행하지 않는다. 실행은 사람이 한다.
- **원본 보호** — 출력 경로는 항상 `-fixed` 같은 새 파일 이름이다.
- **사실 보존** — 캡션을 고친 뒤 `compare_reports` 로 잃은 숫자·링크·해시태그를 확인한다.
- **정직한 공백** — 재지 못한 값은 `?`, 판정하지 않는 것은 출력 끝에 적는다.

## 판정하지 않는 것

- 영상 안에 **실제로 그려진 글자·로고의 위치** (편집본이 선언한 상자만 본다)
- 사람이 느끼는 재미·편집 품질, 소리의 내용(음성 인식 없음)
- 플랫폼 심사·저작권·조회수
- 규격의 미래 — `platforms.AS_OF = 2026-11-27` 에 확인한 공개 문서 기준이고 바뀔 수 있다

플랫폼 화면 덮개 비율은 공식 수치가 없는 곳이 많다. YouTube·TikTok 은 **추정값**, Instagram 은 **Reels 광고 가이드 값**이며, 이 시리즈가 쓰는 **내 규칙(상단 20%·하단 35%·우측 버튼)** 은 따로 `house` 프로파일로 둔다. 어느 값인지 출력에 표시된다.

## 테스트

```bash
pytest        # 389 passed, 1 skipped
```

`caption 45 · check 64 · cli 21 · hook 25 · platforms 27 · probe 25 · report 20 · safearea 34 · server 26 · store 8 · tells 64(1 skip) · types 30`

- in-memory MCP 클라이언트와 **stdio 서브프로세스** 양쪽으로 툴 10개를 호출한다.
- `test_cli` 는 실제 `ffmpeg` 로 4초짜리 1080×1920 영상을 만들어 재고, 종료 코드까지 확인한다.
- 실제 영상이 없는 환경에서는 그 테스트만 건너뛴다.

## 구조

```
publish_guard/
  types.py      자료형 (파일 사실·캡션 사실·발견·보고서)
  probe.py      ffprobe/ffmpeg 실행과 파서 (ebur128·silencedetect)
  platforms.py  플랫폼 규격 4종 (출처·기준일 포함)
  safearea.py   사각형 교차·최소 이동·상자 입력 검증
  caption.py    캡션 파싱 (해시태그·멘션·링크·구역)
  tells.py      AI 글투 21종 (강도·겹침 규칙)
  hook.py       첫 줄 규칙 7종
  check.py      규칙 → 발견 → 점수 → 판정 → 고치기 순서, 비교
  report.py     사람이 읽는 줄, JSON
  rules.py      규칙 색인 64종
  store.py      한 프로세스 안의 ref (m-·c-·r-)
  server.py     MCP 10툴
  cli.py        명령줄
tools/          audit.py (실측) · demo.py (어제 편 vs 오늘 편)
examples/       캡션 전/후, 상자 JSON
reels/          build_reels.py · build_audio.py · boxes-day11.json
```

## 라이선스

MIT. 원본 두 저장소의 라이선스도 MIT 이며, 이 저장소에는 원본 코드가 들어 있지 않다.
