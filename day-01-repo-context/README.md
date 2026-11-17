# Day 01 · repo-context — Filesystem MCP × Git MCP

> **1일 1스킬**: 공개된 MCP/스킬 두 개를 골라, 버릴 건 버리고 붙일 곳만 붙여
> **새 MCP 하나**로 다시 만드는 시리즈. Day 01은 파일 접근과 git 이력을 섞었습니다.
>
> filesystem MCP(15 tools) + git MCP(14 tools) → **repo-context(4 tools)**
> — 읽기 전용, 토큰 예산 안에서 저장소 맥락을 한 장으로.

---

## 1. 섞은 두 스킬

| | 원본 | 라이선스 | 툴 수 | 여기서 가져온 것 | 가져오지 않은 것 |
|---|---|---|---|---|---|
| ① | [`@modelcontextprotocol/server-filesystem`](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) | Apache-2.0 | 15 | **경로 샌드박스**·읽기 전용 모드·바이너리/대용량 거부 | write/edit/move/copy, 미디어 읽기 |
| ② | [`mcp-server-git`](https://github.com/modelcontextprotocol/servers/tree/main/src/git) (PyPI) | Apache-2.0 | 14 | **저장소 이력 읽기**(status·log·diff·ls-files) | commit/add/reset/merge/checkout 같은 쓰기 툴 |

두 원본은 모두 [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
(GitHub ★ 92,058 · 2026-11-17 기준) 안의 서로 다른 서버입니다.
라이선스는 저장소 `LICENSE` 기준 **Apache-2.0**(과거 MIT 기여분 병존)이며, 이 프로젝트는
코드를 복사하지 않고 **설계만 참고해 파이썬으로 새로 작성**했습니다. 원본과 제휴 관계는 없습니다.

## 2. 왜 섞었나

두 서버를 에이전트에 그대로 붙이면 이런 일이 생깁니다.

1. **툴 정의만 29개** — 모델의 컨텍스트와 툴 선택 정확도를 갉아먹습니다.
2. **filesystem은 "무엇이 최근에 바뀌었는지" 모릅니다.** 파일 400개 중 어디를 먼저 읽어야 하는지는
   파일 내용만 봐서는 알 수 없습니다.
3. **git은 "그 파일 안에 무엇이 있는지" 모릅니다.** `git diff`는 줄을 보여 주지만
   "이 저장소 지금 어디부터 봐야 하나"에는 답하지 않습니다.

그래서 두 서버를 **파일 경로라는 하나의 접점**에서 붙였습니다.

> git 이력이 **어떤 파일이 지금 중요한지** 정하고,
> 샌드박스가 **그 파일 안을 읽어** 심볼·TODO로 요약하고,
> 토큰 예산이 **얼마나 넘길지** 정한다.

## 3. 아키텍처

```
        ┌──────────────────────────────────────────────────────────┐
        │ MCP client (Claude Desktop · Cursor · Claude Code …)     │
        └───────────────┬──────────────────────────────────────────┘
                        │ stdio (JSON-RPC)
        ┌───────────────▼──────────────────────────────────────────┐
        │ server.py — 4 tools                                      │
        │  repo_overview · recent_changes · file_outline ·          │
        │  context_pack                                             │
        └───────┬───────────────────────────────┬──────────────────┘
                │                               │
   ┌────────────▼─────────────┐   ┌─────────────▼──────────────────┐
   │ sandbox.py (① 에서)      │   │ gitio.py (② 에서)              │
   │ 루트 밖 경로 거부         │   │ 읽기 전용 서브커맨드만 허용      │
   │ 심링크 탈출 거부          │   │ status/log/ls-files/diff        │
   │ 비밀·바이너리·대용량 거부  │   │ 저장소 루트 기준 → 샌드박스 기준 │
   └────────────┬─────────────┘   └─────────────┬──────────────────┘
                │                               │
                └───────────┬───────────────────┘
                ┌───────────▼────────────┐   ┌──────────────────────┐
                │ outline.py              │   │ pack.py              │
                │ AST(파이썬)·정규식 심볼  │──▶│ 우선순위 + 토큰 예산   │
                └────────────────────────┘   └──────────────────────┘
```

## 4. 툴 4개

| 툴 | 하는 일 | 언제 |
|---|---|---|
| `repo_overview` | 브랜치·HEAD·커밋 수·커밋 안 된 변경·상위 구조·언어 비중 | 처음 보는 저장소 |
| `recent_changes` | 최근 커밋과 각 커밋이 건드린 파일 + 작업 트리 상태 | 회귀 추적, PR 설명 |
| `file_outline` | 파일의 클래스·함수·메서드 + 줄 번호 (Python은 AST) | 파일을 통째로 읽기 전에 |
| `context_pack` | 위 셋을 하나로 합친 **토큰 예산 맥락 팩** | 작업 시작할 때 한 번 |

## 5. 설치

```bash
git clone https://github.com/where-is-the-error/daily-mcp-skills.git
cd daily-mcp-skills/day-01-repo-context

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # mcp>=2.3, pytest
```

## 6. MCP 클라이언트에 연결

```json
{
  "mcpServers": {
    "repo-context": {
      "command": "python",
      "args": ["-m", "repo_context.server", "--root", "/absolute/path/to/your/repo"],
      "env": { "PYTHONPATH": "/absolute/path/to/daily-mcp-skills/day-01-repo-context" }
    }
  }
}
```

`--root`가 **샌드박스 경계**입니다. 이 디렉터리 밖은 어떤 툴로도 읽히지 않습니다.
환경변수 `REPO_CONTEXT_ROOT`로도 지정할 수 있습니다.

## 7. CLI로 바로 써 보기

```bash
repo-context --root . overview
repo-context --root . recent --limit 5
repo-context --root . outline repo_context/pack.py
repo-context --root . pack repo_context --max-tokens 900
```

실제 실행 결과 전체는 [`examples/sample_output.md`](examples/sample_output.md)에 있습니다.
`pack` 출력의 한 조각:

```markdown
# repo-context · `day-01-repo-context` / `repo_context`
> branch `main` · HEAD `fc6b8b6` (2026-11-17) · 커밋 2개 · 변경 0개

## 최근 커밋 (최근 2개)
- `fc6b8b6` 2026-11-17 feat(day-01): …
  ↳ .gitignore, pyproject.toml, repo_context/__init__.py 외 12개

## 핫 파일 (최근 20커밋에서 자주 바뀐 순)
### 1. `repo_context/pack.py` — 3회
- def `context_pack` (L122) — A repository digest that fits a token budget

## TODO / FIXME (소스 12개 스캔)
- `repo_context/sandbox.py:41` TODO — 심링크 탈출 테스트
```

## 8. 토큰 예산은 이렇게 동작합니다

`context_pack(max_tokens=N)`은 넘치면 **아래쪽 섹션부터 스스로 줄입니다**(단계적 축소).

| 단계 | 최근 커밋 | 바뀐 파일 | 핫 파일 | TODO |
|---|---|---|---|---|
| 0 | 8개 | 8개 | 5개 + 심볼 | 12개 |
| 1 | 5개 | 5개 | 3개 + 심볼 | 6개 |
| 2 | 3개 | 3개 | 2개 (심볼 없이) | 3개 |
| 3 | 2개 | – | – | – |
| 4 | 1개 | – | – | – |

그래도 넘치면 문자 단위로 잘라 `… (토큰 예산에 맞춰 잘림)`을 붙입니다.
**어떤 경우에도 추정 토큰 수가 예산을 넘지 않는다**는 것을 테스트로 고정했습니다
(200·400·800·1,200·2,000 토큰).

> 추정치는 의존성 없는 근사입니다: ASCII 4글자 ≈ 1토큰, 한글 1글자 ≈ 1토큰.

## 9. 안전장치

- **샌드박스**: `..`, 절대경로, 루트 밖을 가리키는 심링크 모두 거부 (`sandbox.py`)
- **읽기 전용 git**: 허용 목록에 없는 서브커맨드는 실행 전에 거부 —
  `commit`/`add`/`reset`은 코드 상 불가능 (`gitio.READ_ONLY_SUBCOMMANDS`)
- **비밀 파일 차단**: `.env`, `*.pem`, `*.key`, `id_rsa*`, `.npmrc`, `credentials*` 등은
  읽지도, 팩에 넣지도 않고 개수만 알려 줍니다
- **바이너리·대용량 거부**: NUL 바이트가 있거나 400KB를 넘는 파일은 컨텍스트에 넣지 않습니다
- **타임아웃**: git 호출은 10초에서 끊습니다

## 10. 테스트

```bash
python -m pytest        # 40 passed
```

| 파일 | 검증 |
|---|---|
| `tests/test_sandbox.py` | 경로 탈출 5종, 심링크·비밀·바이너리·대용량 거부, git 쓰기 차단, 이력 파싱 |
| `tests/test_outline.py` | Python AST 정확도, TS/Go/Rust 패턴, 미지원 확장자 |
| `tests/test_pack.py` | 섹션 구성, 비밀 노출 0건, 예산 5종 준수, 비-git 디렉터리 |
| `tests/test_paths.py` | 모노레포 하위 디렉터리를 루트로 잡았을 때 경로 재기준화 |
| `tests/test_server.py` | **실제 MCP 서버에 클라이언트로 붙어** 툴 4개 목록·호출·경로 탈출 거부 |

마지막 테스트는 in-memory MCP 클라이언트로 서버를 띄워 `list_tools`/`call_tool`을
그대로 호출합니다. stdio 실행도 확인했습니다:

```bash
python -m repo_context.server --root .
# server: repo-context 0.1.0
# tools: ['repo_overview', 'recent_changes', 'file_outline', 'context_pack']
```

## 11. 한계

- 심볼 추출은 Python 외 언어에서 **정규식 근사**입니다(중첩·동적 선언은 놓칩니다).
- `context_pack`의 토큰 수는 정확한 토크나이저가 아닌 **추정치**입니다.
- git 저장소가 아니면 파일 목록만 돌려줍니다.
- 서브모듈·LFS 파일 내용은 읽지 않습니다.

## 12. 릴스

| 파일 | 내용 |
|---|---|
| [`reels-day01.mp4`](reels-day01.mp4) | 1080×1920 · 21.6초 · 30fps · 무음(인스타에서 음원 추가) |
| [`reels-day01-poster.png`](reels-day01-poster.png) | 커버 이미지 |
| [`instagram-caption.md`](instagram-caption.md) | 본문 + 해시태그 초안 |
| [`reels/build_reels.py`](reels/build_reels.py) | 영상 생성 스크립트(Pillow + ffmpeg) — `python3 reels/build_reels.py` |

## 라이선스

이 저장소의 코드는 **MIT**(루트 `LICENSE`). 참고한 원본 두 서버의 라이선스는 **Apache-2.0**이며,
이 프로젝트는 원본 코드를 포함하지 않습니다. 원본 프로젝트와 제휴·보증 관계가 없습니다.
