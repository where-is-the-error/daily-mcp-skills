# daily-mcp-skills

**1일 1스킬** — 하루에 공개된 MCP/에이전트 스킬 **2개**를 골라 섞어, **새 MCP 하나**를
만들어 올리는 시리즈입니다. 매일 코드·README·테스트·릴스 영상까지 같이 올라갑니다.

> Two public MCP servers, mashed into one new tool a day.
> Code, README, tests and a 9:16 reel for every entry.

## 시리즈 규칙

1. **원본 2개는 실제 공개 저장소**에서 고르고, 출처·라이선스·URL을 README에 적는다.
2. 원본 코드를 복사하지 않고 **설계만 가져와** 새로 구현한다(라이선스 표기 필수).
3. **테스트가 실제로 통과**해야 올린다 — 문서만 있는 항목은 올리지 않는다.
4. 매일 `day-NN-슬러그/` 폴더 하나 + 릴스 영상 + 인스타 캡션.

## 목록

| Day | 조합 | 결과물 | 툴 | 테스트 | 릴스 |
|---|---|---|---|---|---|
| 01 | [Filesystem MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) + [Git MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/git) | [`repo-context`](day-01-repo-context/) — 읽기 전용, 토큰 예산 저장소 맥락 팩 | 29 → 4 | 40 passed | 21.6s |

*(Day 02부터 이 표에 한 줄씩 추가됩니다.)*

## Day 01 미리보기

```bash
cd day-01-repo-context
pip install -e ".[dev]"
repo-context --root . pack repo_context --max-tokens 900
```

```markdown
# repo-context · `day-01-repo-context` / `repo_context`
> branch `main` · HEAD `...` · 커밋 5개 · 변경 0개

## 최근 커밋 …
## 핫 파일 (최근 20커밋에서 자주 바뀐 순) …
## TODO / FIXME …
```

- 4개 툴: `repo_overview` · `recent_changes` · `file_outline` · `context_pack`
- 안전: 샌드박스 경로 검증, 읽기 전용 git 허용 목록, `.env`/`*.pem` 차단
- 자세한 설명: [day-01-repo-context/README.md](day-01-repo-context/README.md)

## 라이선스

각 Day의 코드는 **MIT**. 참고한 원본 프로젝트의 라이선스는 해당 Day의 README에 표기합니다.
