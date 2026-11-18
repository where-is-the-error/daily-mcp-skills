# Day 02 · web-memo — Fetch MCP × Memory MCP

> **1일 1스킬**: 공개된 MCP/스킬 두 개를 골라, 버릴 건 버리고 붙일 곳만 붙여
> **새 MCP 하나**로 다시 만드는 시리즈. Day 02는 웹 읽기와 기억을 섞었습니다.
>
> Fetch MCP(1 tool) + Memory MCP(9 tools) → **web-memo(5 tools)**
> — 한 번 읽은 페이지는 기억해 두고, 다음엔 **바뀐 줄만** 받습니다.

---

## 1. 섞은 두 스킬

| | 원본 | 라이선스 | 툴 수 | 여기서 가져온 것 | 가져오지 않은 것 |
|---|---|---|---|---|---|
| ① | [`mcp-server-fetch`](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch) (`mcp-server-fetch` 2026.11.11) | **MIT** (`src/fetch/LICENSE`) | 1 (`fetch`) | **URL → 본문 텍스트**, robots.txt 존중, `max_length` 잘라내기, 문서 MIME 확인 | 무제한 길이, `start_index` 페이지네이션, raw HTML 반환 |
| ② | [`@modelcontextprotocol/server-memory`](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) (2.1.1) | **MIT** (README `## License`) | 9 (`create_entities`, `create_relations`, `add_observations`, `delete_*` 3종, `read_graph`, `search_nodes`, `open_nodes`) | **엔티티·관계·관찰 3원자**, JSONL 영속화 사상 | 그래프 전체 덤프, `delete_*` 3종, `open_nodes` |

두 원본 모두 [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) 안의 **서로 다른 서버**입니다
(GitHub ★ 92,000+ · 2026-11-18 기준). 코드를 복사하지 않고 **설계만 참고해 파이썬으로 새로 작성**했습니다.

> 라이선스 표기 그대로: fetch 서버는 디렉터리에 `LICENSE`(MIT, Anthropic PBC)가 있고,
> memory 서버는 디렉터리에 별도 `LICENSE` 파일이 없어 저장소 루트 `LICENSE`(MIT → Apache-2.0 전환 중)와
> `src/memory/README.md`의 `## License`(MIT)를 함께 확인했습니다.

Day 01(`filesystem` × `git`)과 겹치지 않게, 파일 접근·git 이력은 건드리지 않았습니다.

## 2. 왜 섞었나

에이전트가 문서를 읽는 방식은 대개 이렇습니다.

1. 페이지를 통째로 받아 온다 → **8,000자 ≈ 2,000 토큰**이 컨텍스트에 들어간다.
2. 다음 날 같은 페이지를 **또 통째로** 받아 온다.
3. 실제로 바뀐 건 요금제 한 줄인데, 토큰은 다시 다 쓴다.

Fetch MCP는 매번 새로 읽고, Memory MCP는 무엇을 **언제** 읽었는지 모릅니다.
그래서 두 서버를 **"URL 한 개"라는 접점**에서 붙였습니다.

> Fetch가 **지금 본문**을 가져오고,
> 스냅샷 저장소가 **지난 본문**과 비교해 바뀐 줄만 남기고,
> 기억 그래프가 **그 페이지에 대해 내가 한 말**을 붙든다.

## 3. 아키텍처

```
        ┌──────────────────────────────────────────────────────────┐
        │ MCP client (Claude Desktop · Cursor · Claude Code …)      │
        └───────────────┬──────────────────────────────────────────┘
                        │ stdio (JSON-RPC)
        ┌───────────────▼──────────────────────────────────────────┐
        │ server.py — 5 tools                                      │
        │  remember_page · page_changes · recall ·                 │
        │  annotate · overview                                     │
        └───────┬───────────────────────────────┬──────────────────┘
                │                               │
   ┌────────────▼─────────────┐   ┌─────────────▼──────────────────┐
   │ fetch.py (① 에서)        │   │ graph.py (② 에서)              │
   │ robots.txt 판정(RFC 9309) │   │ 엔티티 · 관찰 · 관계            │
   │ 사설망·스킴 차단          │   │ 태그 → `tagged` 관계            │
   │ 5MB/20s 상한, MIME 확인   │   │ 같은 문장은 한 번만             │
   └────────────┬─────────────┘   └─────────────┬──────────────────┘
                │                               │
        ┌───────▼────────┐              ┌───────▼──────────┐
        │ extract.py     │              │ search.py        │
        │ HTML → 본문     │              │ 본문+메모 검색     │
        └───────┬────────┘              └───────┬──────────┘
                │                               │
        ┌───────▼───────────────────────────────▼──────────┐
        │ pages.py · diff.py · db.py (SQLite 한 파일)        │
        │ 스냅샷 + 그래프, content hash로 중복 저장 차단      │
        └───────────────────────────────────────────────────┘
```

**한 파일에 다 들어가는 이유**: "페이지를 읽고 → 스냅샷을 남기고 → 그 사실을 기억에 붙이는" 일이
한 트랜잭션으로 끝납니다. Memory MCP의 JSONL 전체 다시 쓰기보다 안전하고, 스냅샷 본문을 SQL로 바로 훑습니다.

## 4. 툴 5개

| 툴 | 하는 일 | 언제 |
|---|---|---|
| `remember_page` | URL을 읽어 스냅샷 저장. 이미 아는 페이지면 **diff만** 반환 | 문서·릴리스 노트·요금표를 다시 볼 때 |
| `page_changes` | 저장된 두 스냅샷의 차이 (네트워크 0회) | "지난주 이후 뭐 바뀌었지" |
| `recall` | 페이지 본문·메모·태그를 한 번에 검색, 걸린 줄만 발췌 | "타임아웃 어디에 적혀 있더라" |
| `annotate` | 대상에 메모·태그 (엔티티·관찰·관계) | 읽으면서 남긴 판단을 붙여 둘 때 |
| `overview` | 기억 현황·최근 확인·오래 안 본 페이지 | 새 세션에서 "내가 아는 것" 먼저 볼 때 |

## 5. 설치

```bash
git clone https://github.com/where-is-the-error/daily-mcp-skills.git
cd daily-mcp-skills/day-02-web-memo

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # mcp>=2.3, pytest
```

설치 없이 바로 돌려 보려면 이 디렉터리에서:

```bash
PYTHONPATH=. python -m web_memo.cli remember https://example.com/
PYTHONPATH=. python -m web_memo.server       # stdio MCP 서버
```

> 이 저장소를 만든 샌드박스에는 `setuptools`가 없어 `pip install -e .` 경로 자체는 실행 검증하지 못했습니다.
> 테스트 117개, CLI, stdio 서버는 `PYTHONPATH=.`로 실제 실행해 확인했습니다.

## 6. MCP 클라이언트에 연결

```json
{
  "mcpServers": {
    "web-memo": {
      "command": "python",
      "args": ["-m", "web_memo.server"],
      "env": { "WEB_MEMO_DB": "/absolute/path/to/web-memo/memo.db" }
    }
  }
}
```

`WEB_MEMO_DB`를 생략하면 `~/.local/share/web-memo/memo.db`를 씁니다.
기억은 이 파일 하나에만 남고, 삭제는 `web-memo forget <url>` 또는 파일 삭제로 끝납니다.

## 7. CLI로 바로 써 보기

```bash
web-memo remember https://docs.example.com/pricing
web-memo changes  https://docs.example.com/pricing
web-memo recall 타임아웃
web-memo note https://docs.example.com/pricing "연간 결제 조항 신설" --tags pricing,docs
web-memo overview
web-memo forget https://docs.example.com/pricing
```

실제 실행 결과 전체는 [`examples/sample_output.md`](examples/sample_output.md)에 있습니다.
1,867 토큰짜리 변경 이력 페이지에서 요금 한 줄이 바뀌었을 때 실제 응답:

```diff
# web-memo · PayFlow API 변경 이력
- 상태: 변경됨 · +4줄 / -2줄
- 이번 응답은 바뀐 부분만: 약 298 토큰 (전체 1,903 토큰 대신 1,605 토큰 절약)

## 바뀐 부분
@@ -117,7 +119,7 @@
  v2.4.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 404 정비
- v2.3.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 403 정비
+ v2.3.1 — 결제 API 응답 필드 정리(핫픽스), 재시도 정책 문서화, 오류 코드 403 정비
```

같은 페이지를 그대로 다시 부르면 저장도, 긴 응답도 없습니다.

```markdown
- 상태: 변경 없음 · 스냅샷을 늘리지 않았습니다
- 같은 내용이라 이번엔 아무것도 저장하지 않았습니다 (이 페이지 본문 1,903 토큰을 다시 넘기지 않아도 됩니다)
```

## 8. 무엇이 "바뀜"인가

| 경우 | 판정 | 저장 |
|---|---|---|
| 처음 보는 URL | `new` | 스냅샷 1개 |
| 본문 정규화 후 해시 동일 | `unchanged` | **저장 안 함** (확인 횟수만 +1) |
| 해시 다름 | `changed` | 스냅샷 추가 + 이전과의 diff |

- **정규화 먼저**: `script`·`style`·`nav`·`footer`·`aside`·`form`·`hidden` 제거, 공백·빈 줄 정리,
  줄 끝 공백 제거 후 비교합니다. 조회수 카운터나 광고만 바뀐 페이지는 "변경 없음"이 됩니다.
- **diff는 hunk 단위**: 바뀐 줄 앞뒤 `context`줄만 남기고, 가까운 변경(간격 ≤ context×2)은 한 hunk로 묶습니다.
- **diff가 전문보다 길면 그렇다고 말합니다** — 짧은 페이지에서는 솔직하게 "전문이 더 짧다"고 알려 줍니다.
- 스냅샷은 페이지당 최근 30개까지 남습니다(`keep`).

## 9. 안전장치

- **robots.txt 준수** — 호스트별로 한 번 읽고 캐시. 표준 라이브러리 `urllib.robotparser`는
  규칙을 **적힌 순서대로** 처음 맞는 것만 적용해서 `Allow: /` + `Disallow: /admin` 조합을 뚫습니다.
  그래서 **RFC 9309 longest-match**(긴 패턴 우선, 동률이면 Allow)를 직접 구현했습니다.
- **사설망 차단(SSRF)** — `127.0.0.1`, `10.x`, `192.168.x`, `169.254.169.254`, `::1` 등은
  DNS 해석 결과까지 확인해 열지 않습니다. 스킴은 `http`/`https`만(`file:`·`data:` 거부).
- **MIME 화이트리스트** — `text/html`, `text/plain`, `text/markdown` 등 문서만. PDF·이미지는 거부.
- **상한** — 응답 5 MB, 타임아웃 20초, 저장 본문 `max_chars`(기본 12,000자), 툴 응답 토큰 예산(기본 900).
- **JS 미실행** — 마크업만 읽습니다. 스크립트·쿠키·로그인 상태를 쓰지 않으므로,
  로그인 뒤에만 보이는 페이지는 읽지 못합니다(의도된 한계).
- **로컬 테스트용 예외** — CLI의 `--allow-private`(또는 `WEB_MEMO_ALLOW_PRIVATE=1`)로만 사설망이 열립니다.
  MCP 서버 기본값은 항상 차단입니다.

## 10. 테스트

```bash
python -m pytest        # 117 passed
```

| 파일 | 검증 |
|---|---|
| `tests/test_extract.py` | title/폴백, script·nav·footer·hidden 제거, `role="main"`, 사이드바 클래스, 엔티티 디코딩, 잘라내기 |
| `tests/test_fetch.py` | URL 정규화 5종, 사설망 8종, robots 12종(**longest-match·와일드카드·UA별 그룹·캐시**), MIME·크기 거부, charset |
| `tests/test_pages.py` | new/unchanged/changed 판정, 해시 중복, 확인 횟수, 스냅샷 상한, stale 목록, 삭제 |
| `tests/test_diff.py` | +/- 개수, context 제한, hunk 병합/분리, 헤더 번호, 상한·잘림, 한글 |
| `tests/test_search.py` | 제목/본문/메모/태그 가중치, 발췌, 본문 히트 상한, 빈 결과 |
| `tests/test_graph.py` | 엔티티 타입 추론, 관찰 중복 차단, 태그 관계 멱등성, `about` 관계 |
| `tests/test_views.py` | 상태별 문구, 토큰 예산 절단, 빈 상태 |
| `tests/test_server.py` | **실제 MCP 클라이언트**로 툴 5개 목록·호출, 변경/동일/거부 흐름, **stdio 프로세스 실행** |

stdio 실행 확인:

```bash
$ python -m web_memo.server
{"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{"listChanged":false},...},
 "serverInfo":{"name":"web-memo","title":"web-memo","version":"0.1.0"}}}
```

## 11. 한계

- **JS로 그리는 페이지는 본문이 비어 나옵니다** (SPA·무한 스크롤). 헤드리스 브라우저를 쓰지 않는 설계입니다.
- 추출은 휴리스틱입니다. `<main>`이 없는 사이트는 본문 판정이 거칠 수 있습니다.
- 토큰 수는 **추정치**입니다(ASCII 4자 ≈ 1, 긴 글자 1자 ≈ 1).
- diff는 줄 단위입니다. 한 줄 안에서 단어만 바뀌면 그 줄 전체가 -/+로 나옵니다.
- robots.txt 판정은 사이트가 규칙을 자주 바꾸면 최대 1시간(캐시 TTL) 늦을 수 있습니다.
- 리다이렉트는 `urllib` 기본 정책을 따르고, 최종 URL이 아닌 요청 URL을 키로 저장합니다.

## 12. 릴스

| 파일 | 내용 |
|---|---|
| [`reels-day02.mp4`](reels-day02.mp4) | 1080×1920 · **21.5초** · 30fps · H.264 + AAC 256k 스테레오 — 자체 제작 사운드트랙 포함 |
| [`reels-day02-poster.png`](reels-day02-poster.png) | 커버 이미지 (훅 + 삐에로 반전 문구) |
| [`reels-day02-audio.wav`](reels-day02-audio.wav) | 사운드트랙 48kHz 스테레오 24bit |
| [`instagram-caption.md`](instagram-caption.md) | 본문 + 해시태그 |
| [`reels/build_reels.py`](reels/build_reels.py) | 영상 생성(Pillow + ffmpeg) |
| [`reels/build_audio.py`](reels/build_audio.py) | 사운드트랙 합성(numpy) |

컷 구성 — 120 BPM(1마디 2.0초) 마디 경계에 씬 경계를 맞춤:

| 시간 | 씬 | 내용 |
|---|---|---|
| 0.0~1.5 | 훅 | 붉은 경고·글리치 + "또 그 문서 처음부터 읽어요?" |
| 1.5~3.5 | 드롭 | "삐에로가 웹페이지에 기억을 심었습니다" (Fetch + Memory → web-memo) |
| 3.5~7.5 | 10 → 5 | 원본 두 서버 카드, 툴 10개에 취소선 → 5 |
| 7.5~13.5 | 툴 + 터미널 | 5개 툴, `remember_page` 실행과 `+4/-2줄 · 298 토큰` |
| 13.5~17.5 | 안전장치 | robots longest-match · 사설망 차단 · JS 미실행 |
| 17.5~21.5 | CTA | GitHub 저장소 · @pierrot.dev.kr |

이모지는 폰트에서 네모로 깨지므로 쓰지 않습니다. 아이콘(경고·자물쇠·방패)은 전부 도형으로 그립니다.
글꼴은 `reels/fonts/Pretendard-*.otf`(OFL)입니다.

## 라이선스

이 저장소의 코드는 **MIT**(루트 `LICENSE`). 참고한 두 원본 서버도 **MIT**이며,
이 프로젝트는 원본 코드를 포함하지 않습니다. 원본 프로젝트와 제휴·보증 관계가 없습니다.
