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
| 02 | [Fetch MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch) + [Memory MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | [`web-memo`](day-02-web-memo/) — 한 번 읽고 **바뀐 줄만**, 메모는 기억 그래프에 | 10 → 5 | 117 passed | 21.5s |

## 다음 화 만드는 법 (Day 02~)

1. **공개 MCP/스킬 2개 선정** — `gh repo view`로 실제 존재·라이선스·툴 수를 확인한다.
2. **`day-NN-슬러그/` 폴더** — `repo_context` 같은 패키지 + `tests/` + README(출처 링크·라이선스·아키텍처·설치·실행·한계).
3. **테스트 통과** — `python -m pytest`. 통과 못 한 항목은 올리지 않는다.
4. **릴스** — 직전 Day의 `reels/build_reels.py`·`build_audio.py`를 복사해 문구만 교체 → `reels-dayNN.mp4`(1080×1920 · 15~25초 · 30fps · 사운드 포함).
5. **캡션** — `instagram-caption.md`에 본문·해시태그·업로드 체크리스트.
6. **목록 표에 한 줄 추가**하고 커밋. 커밋은 `feat(day-NN)` / `test(day-NN)` / `docs(day-NN)` / `content(day-NN)`으로 나눈다.

> 릴스 제작에는 `ffmpeg`가 필요하다. 없으면 `pip install imageio-ffmpeg`로 받은 바이너리 경로를 `ffmpeg`로 심볼릭 링크해 쓴다.

## Day 02 미리보기

```bash
cd day-02-web-memo
pip install -e ".[dev]"
web-memo remember https://docs.example.com/changelog
web-memo remember https://docs.example.com/changelog   # 같은 내용 → "변경 없음"
web-memo changes  https://docs.example.com/changelog   # 바뀐 줄만
```

```markdown
# web-memo · PayFlow API 변경 이력
- 상태: 변경됨 · +4줄 / -2줄
- 이번 응답은 바뀐 부분만: 약 298 토큰 (전체 1,903 토큰 대신 1,605 토큰 절약)

## 바뀐 부분
@@ -117,7 +119,7 @@
- v2.3.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 403 정비
+ v2.3.1 — 결제 API 응답 필드 정리(핫픽스), 재시도 정책 문서화, 오류 코드 403 정비
```

- 5개 툴: `remember_page` · `page_changes` · `recall` · `annotate` · `overview`
- 안전: robots.txt **longest-match**(직접 구현) · 사설망 차단(SSRF) · MIME/크기 상한 · JS 미실행
- 자세한 설명: [day-02-web-memo/README.md](day-02-web-memo/README.md)

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
