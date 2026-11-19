# Day 03 · deadline-clock — Time MCP × SQLite MCP

> **1일 1스킬**: 공개된 MCP/스킬 두 개를 골라, 버릴 건 버리고 붙일 곳만 붙여
> **새 MCP 하나**로 다시 만드는 시리즈. Day 03은 시간과 저장을 섞었습니다.
>
> Time MCP(3 tools) + SQLite MCP(6 tools) → **deadline-clock(6 tools)**
> — 마감을 **날짜가 아니라 시각+시간대**로 저장하고, 남은 시간·D-day·남은 평일을 다시 셉니다.

---

## 1. 섞은 두 스킬

| | 원본 | 라이선스 | 툴 수 | 여기서 가져온 것 | 가져오지 않은 것 |
|---|---|---|---|---|---|
| ① | [`mcp-server-time`](https://github.com/modelcontextprotocol/servers/tree/main/src/time) (`src/time`) | **MIT** (디렉터리 README `## License`) | 3 (`get_current_time`, `convert_time`, `get_time_ago`) | **IANA 키 엄격 판정**(대소문자 구분), **서머타임의 두 구멍**(두 번 있는 시각·없는 시각) 처리, "모르면 지어내지 않고 알려 준다" | `get_time_ago`(경과 조회), `--local-timezone` 자동 감지, 오프셋 문자열 출력 |
| ② | [`mcp-server-sqlite`](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite) (`src/sqlite`, 보관됨) | **MIT** (저장소 루트 `LICENSE`) | 6 (`read_query`, `write_query`, `create_table`, `list_tables`, `describe_table`, `append_insight`) + 리소스 `memo://insights` | **한 파일 SQLite + 스키마 + 읽기/쓰기 분리**, "인사이트를 계속 쌓는" 기록 사상 | **임의 SQL 실행**, `create_table`, 프롬프트 `mcp-demo`, 리소스 노출 |

- ①은 [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)(★ 92,000+, 2026-11-19 기준) 안의 서버입니다. 2026-11-18 에 열어 보니 `src/` 에는 `everything`·`fetch`·`filesystem`·`git`·`memory`·`sequentialthinking`·`time` 일곱 개가 남아 있었습니다.
- ②는 같은 팀이 **보관 처리한** 저장소([servers-archived](https://github.com/modelcontextprotocol/servers-archived), 마지막 푸시 2025-05-28)의 SQLite 서버입니다. 지금 `servers` 저장소에는 없습니다. 그래서 **설계만** 가져오고 코드는 파이썬 표준 `sqlite3` 로 새로 썼습니다.
- Day 01(`filesystem` × `git`)·Day 02(`fetch` × `memory`)와 겹치지 않게, 파일 접근·git·웹 읽기·기억 그래프는 건드리지 않았습니다.

> ②의 라이선스 표기: 저장소 루트 `LICENSE` 가 MIT 이고, `src/sqlite` 디렉터리에는 별도 `LICENSE` 파일이 없습니다.
> ①의 `servers` 저장소 루트 `LICENSE` 는 지금 MIT → Apache-2.0 전환 문구가 섞여 있지만,
> `src/time/README.md` 의 `## License` 는 **mcp-server-time is licensed under the MIT License** 라고 명시합니다.

## 2. 왜 섞었나

마감은 대개 이렇게 저장됩니다.

```
due: 2026-11-21        ← 날짜. 시각도, 시간대도 없다.
```

그래서 생기는 일들:

1. **D-day 는 맞는데 남은 시간이 틀린다.** 공지가 `2026-11-21 18:00 UTC` 면 한국 시각으로는 **11월 22일 03:00** 입니다. 21일에 마감이라고 달력에 적어 두면 하루를 잃습니다.
2. **날짜만 넣으면 그날 00:00 이 된다.** 마감은 그날 **끝**인데, 도구는 이미 하루 지난 것으로 계산합니다.
3. **서머타임이 끼면 계산이 어긋난다.** 시계가 되돌아가는 날의 `01:30` 은 **두 번** 있고, 앞으로 뛰는 날의 `02:30` 은 **없습니다**.

Time MCP 는 "지금이 몇 시인가"를 정확히 알지만 마감을 어디에도 남기지 않고,
SQLite MCP 는 마감을 남길 수 있지만 시간대를 모릅니다. 그래서 **"한 순간 + 한 시간대"** 라는 접점에서 붙였습니다.

> Time 이 **표현을 순간으로** 바꾸고,
> SQLite 가 **그 순간을 한 파일에** 남기고,
> 계산기는 **볼 때마다 그 시간대에서 다시** 센다.

## 3. 아키텍처

```
        ┌──────────────────────────────────────────────────────────┐
        │ MCP client (Claude Desktop · Cursor · Claude Code …)      │
        └───────────────┬──────────────────────────────────────────┘
                        │ stdio (JSON-RPC)
        ┌───────────────▼──────────────────────────────────────────┐
        │ server.py — 6 tools                                      │
        │  add_deadline · list_deadlines · deadline_status ·        │
        │  mark_done · preview_when · overview                     │
        └───────┬────────────────────────────────┬─────────────────┘
                │                                │
   ┌────────────▼─────────────┐     ┌────────────▼───────────────────┐
   │ timeparse.py (① 에서)    │     │ store.py (② 에서)              │
   │ 한국어·영어 표현 → 순간   │     │ SQLite 한 파일                  │
   │ 날짜만/시각만 기본값      │     │ deadlines · events             │
   │ 월 더하기(말일 보정)      │     │ 중복 등록 차단 · 완료/되돌리기   │
   └────────────┬─────────────┘     └────────────┬───────────────────┘
                │                                │
   ┌────────────▼─────────────┐     ┌────────────▼───────────────────┐
   │ zones.py (① 에서)        │     │ clock.py                       │
   │ IANA 대소문자 엄격        │     │ 남은 초 · D-day · 평일 수       │
   │ DST 두 번/없음 판정       │     │ 긴급도 6단계 · 표시 문구        │
   └────────────┬─────────────┘     └────────────┬───────────────────┘
                │                                │
        ┌───────▼────────────────────────────────▼──────────┐
        │ views.py — 폰 알림 한 화면 크기의 마크다운 + 토큰 예산 │
        └───────────────────────────────────────────────────┘
```

## 4. 툴 6개

| 툴 | 하는 일 | 언제 |
|---|---|---|
| `add_deadline` | 표현을 해석해 저장. 같은 제목·같은 시각이면 중복을 만들지 않음 | 공모전·과제·면접·구독 갱신을 넣을 때 |
| `list_deadlines` | 마감 순서, 지난 것 포함, 태그 필터 | "이번 주 뭐 있지" |
| `deadline_status` | 하나의 남은 시간·D-day·평일·기록 | "그거 얼마나 남았지" |
| `mark_done` | 완료 / 되돌리기(오탭 복구) | 제출하고 나서 |
| `preview_when` | **저장하지 않고** 해석만 | "이 표현이 몇 시로 읽히지" |
| `overview` | 긴급도 분포 + 앞으로의 마감 한 장 | 새 세션 첫 질문 |

## 5. 설치

```bash
git clone https://github.com/where-is-the-error/daily-mcp-skills.git
cd daily-mcp-skills/day-03-deadline-clock

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # mcp>=2.3, pytest
```

설치 없이 바로:

```bash
PYTHONPATH=. python -m deadline_clock.cli add "공모전 제출" "내일 오후 6시"
PYTHONPATH=. python -m deadline_clock.server      # stdio MCP 서버
```

> 이 저장소를 만든 샌드박스에는 `setuptools` 가 없어 `pip install -e .` 경로 자체는 실행 검증하지 못했습니다.
> 테스트 198개, CLI, in-memory·stdio MCP 서버는 `PYTHONPATH=.` 로 실제 실행해 확인했습니다.

## 6. MCP 클라이언트에 연결

```json
{
  "mcpServers": {
    "deadline-clock": {
      "command": "python",
      "args": ["-m", "deadline_clock.server"],
      "env": { "DEADLINE_CLOCK_DB": "/absolute/path/to/deadline-clock/deadlines.db" }
    }
  }
}
```

`DEADLINE_CLOCK_DB` 를 생략하면 `~/.local/share/deadline-clock/deadlines.db` 하나만 씁니다.

## 7. CLI로 바로 써 보기

```bash
deadline-clock add "공모전 제출" "내일 오후 6시" --tags contest
deadline-clock add "해커톤 마감" "2026-11-21 18:00 UTC" --tags hackathon
deadline-clock add "구독 갱신" "11/25" --tags money
deadline-clock ls
deadline-clock show 공모전
deadline-clock preview "3일 뒤 18시"
deadline-clock done 공모전
deadline-clock overview
```

실제 실행 결과 전체는 [`examples/sample_output.md`](examples/sample_output.md). 그중 두 줄:

```text
[등록] 해커톤 마감
  dl_357e75 · 2026-11-22(일) 03:00 KST · D-3 · 2일 17시간 남음
                                              ↑ UTC 21일 18:00 = KST 22일 03:00
```

```text
$ deadline-clock preview "2026-03-08 02:30 America/New_York"
⚠️ 2026-03-08 02:30 은(는) 서머타임이 시작되는 날에 없습니다. 가장 가까운 시각은 03:30 입니다.
```

## 8. 무엇을 '마감'으로 저장하나

| 입력 | 해석 | 함께 남기는 가정 |
|---|---|---|
| `2026-11-21 18:00` | 그 시각 | 시간대(기본 `Asia/Seoul`) |
| `11/25` | **23:59:59** | `시각을 안 줘서 23:59:59(그날 끝)로 가정` |
| `1/5` (오늘 11/19) | 내년 1/5 23:59 | `연도를 2027년으로 가정` |
| `내일 오후 6시` | 다음 날 18:00 | 시간대 |
| `3일 뒤 18시` | **달력** 3일 뒤 18:00 | 시간대 |
| `2시간 후`, `+90m` | **경과** 90분 뒤 | 시간대 (DST 가 끼면 벽시계와 1시간 달라짐) |
| `2개월 뒤` | 달력 2개월 (말일이면 당김: 1/31 → 2/28) | `말일 보정` |
| `다음 주 금요일` | 다음 주(월요일 시작) 금요일 | 시각 미지정 시 23:59:59 |
| `이번 주 수요일` (오늘 목) | **지난 수요일** 그대로 | 지난 마감으로 보임 |
| `목요일 09:00` (오늘 목 10:00) | 다음 주 목요일 | |
| `09:00` (시각만, 이미 지남) | 내일 09:00 | `시각만 줘서 내일로 가정` |
| `2026-11-21 18:00 UTC` | UTC 순간, 한국에선 22일 03:00 | — |
| `2026-11-21T09:00:00Z` | 오프셋 그대로 | 시간대 변환 없음 |

해석하지 못한 글자가 남으면 **조용히 버리지 않고** 그 글자를 지목합니다.
(`아무말 2026-11-21 18:00` → `이해하지 못한 부분이 있습니다: '아무말'`)

## 9. 안전장치 — 원본보다 엄하게 간 곳

- **임의 SQL 없음.** SQLite MCP 의 `read_query`/`write_query` 는 에이전트가 `DELETE FROM deadlines` 도 칠 수 있다는 뜻입니다. 마감 도구에서는 쓰기를 `add`·`set_done`·`delete` 함수로 좁히고, 테이블은 `deadlines`·`events` 둘만 뒀습니다.
- **IANA 키 대소문자 구분.** `Europe/Warsaw` 는 되고 `europe/warsaw` 는 거부하며, 올바른 철자를 함께 알려 줍니다(macOS 의 대소문자 무시 파일시스템에서도 같은 판정).
- **서머타임 두 경우를 숨기지 않음.** 두 번 있는 시각은 첫 번째를 저장하고 **두 번째도 응답에 적습니다**. 없는 시각은 저장하지 않고 가장 가까운 시각(03:30)을 제안합니다.
- **모르는 것을 만들지 않음.** 시각·날짜를 못 읽으면 저장하지 않고 예시를 붙여 되돌려 줍니다. 기본값을 쓸 때는 **쓴 사실을 응답에 남깁니다**.
- **중복 등록 차단.** 같은 제목(공백·대소문자 무시) + 같은 시각이면 새 행을 만들지 않고 `이미 등록된 마감` 이라고 답합니다.
- **완료는 되돌릴 수 있음.** `mark_done(done=False)` 로 되돌리고, 바뀐 일은 `events` 에 남습니다.

## 10. 테스트

```bash
python -m pytest        # 198 passed
```

| 파일 | 검증 |
|---|---|
| `tests/test_zones.py` | IANA 정확·대소문자 거부·별칭 8종, 오프셋 표기, DST 두 번(05:30Z·06:30Z)·없음(03:30 제안), 서울은 12개월 모두 unique |
| `tests/test_timeparse.py` | 절대 6형식, 날짜만/연도 추론/윤년 없는 날, 오늘·내일·모레·글피, 요일 7종 + 이번 주/다음 주/이미 지난 요일, 상대 9종, 개월·말일 보정, 시각만의 내일 이동, 오전/오후 12시, KST·UTC·뉴욕, ISO 오프셋, DST 두 경우, 잔여 글자 지목, 빈 입력·긴 입력·naive now |
| `tests/test_clock.py` | 남은 초(부호), humanize 13구간, 긴급도 경계 10구간, D-day의 시간대 이월(11/20 15:30Z → D-2), 평일 7구간, describe 6종, `DEADLINE_CLOCK_NOW` 5종 |
| `tests/test_store.py` | 생성·중복·부활, 제목 정규화, 태그 갱신, find 6종, 정렬·창·태그·완료 제외·limit, 완료/되돌리기/이미 그 상태, 이벤트 순서, 삭제 캐스케이드, stats, id 생성 |
| `tests/test_views.py` | 응답 문구 20종(등록·중복·부활·모호·목록·상태·완료·개요·미리보기·토큰 절단) |
| `tests/test_server.py` | **실제 MCP 클라이언트**로 툴 6개 목록·호출, 등록→중복→완료→되돌리기, 미리보기 미저장, 태그·창 필터, DST 거부, 모호 참조, **stdio 프로세스 실행** |

stdio 실행 확인:

```bash
$ python -m deadline_clock.server
{"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{"listChanged":false},...},
 "serverInfo":{"name":"deadline-clock","title":"deadline-clock","version":"0.1.0"}}}
```

## 11. 한계

- **공휴일은 모릅니다.** 남은 평일 수는 월~금만 셉니다. 공휴일·임시공휴일은 넣지 않았고, 응답에도 "공휴일 미포함"이라고 적습니다.
- **반복 마감이 없습니다.** 매달 구독 갱신은 매번 넣거나, `2개월 뒤` 식으로 미리 깔아 둬야 합니다.
- 자연어 범위는 한국어·영어의 위 표 수준입니다. 자유 문장("다음 주 쯤 아무때나")은 거부합니다.
- D-day 는 **날짜** 기준, 남은 시간은 **초** 기준입니다. 그래서 `D-3 · 2일 17시간` 처럼 둘이 3일 어긋나 보일 수 있습니다(날짜 경계 때문).
- 남은 시간은 1초 단위로 반올림하고, 화면에는 분까지만 씁니다.
- `deadlines` 는 로컬 SQLite 파일 하나입니다. 기기 간 동기화는 없습니다.
- ② 원본은 보관된 서버라, 그쪽 코드의 보안 수정이 앞으로 들어오지 않습니다. 그래서 코드를 가져오지 않고 설계만 썼습니다.

## 12. 릴스

| 파일 | 내용 |
|---|---|
| [`reels-day03.mp4`](reels-day03.mp4) | 1080×1920 · **21.5초** · 30fps · H.264 + AAC — 자체 제작 사운드트랙 포함 |
| [`reels-day03-poster.png`](reels-day03-poster.png) | 커버 이미지 |
| [`reels-day03-audio.wav`](reels-day03-audio.wav) | 사운드트랙 48kHz 스테레오 |
| [`instagram-caption.md`](instagram-caption.md) | 본문 + 해시태그 + 업로드 체크리스트 |
| [`reels/build_reels.py`](reels/build_reels.py) | 영상 생성(Pillow + ffmpeg) |
| [`reels/build_audio.py`](reels/build_audio.py) | 사운드트랙 합성(numpy) |

**Safe Zone** — 1080×1920 에서 상단 20%(y 0~384), 하단 35%(y 1250~1920), 우측 버튼 영역(x 860~1080, y 900~1920)에는
핵심 텍스트·로고를 두지 않습니다. 모든 문구는 **y 390~1220**, 필요하면 **x ≤ 860** 안에만 배치합니다.

| 시간 | 씬 | 내용 |
|---|---|---|
| 0.0~3.0 | 훅 | "D-3인 줄 알았는데" → "실제로는 6시간" |
| 3.0~5.0 | 드롭 | Time MCP + SQLite MCP → deadline-clock, 9 → 6 tools |
| 5.0~9.0 | 두 스킬 | 시간(순간) × 저장(한 파일) 카드 |
| 9.0~14.5 | 데모 | `add` → `D-1 · 1일 8시간 · 평일 1일`, UTC 마감이 KST 다음 날로 |
| 14.5~18.0 | 함정 | 대소문자 · 서머타임 01:30 두 번 · 02:30 없음 |
| 18.0~21.5 | CTA | GitHub 저장소 · @pierrot.dev.kr |

이모지는 폰트에서 네모로 깨지므로 영상에는 쓰지 않습니다. 아이콘은 전부 도형으로 그립니다.
글꼴은 `reels/fonts/Pretendard-*.otf` (SIL Open Font License 1.1).

## 라이선스

이 저장소의 코드는 **MIT**(루트 `LICENSE`). 참고한 두 원본 서버도 **MIT** 이며,
이 프로젝트는 원본 코드를 포함하지 않습니다. 원본 프로젝트와 제휴·보증 관계가 없습니다.
