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
| 03 | [Time MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/time) + [SQLite MCP](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite) | [`deadline-clock`](day-03-deadline-clock/) — 마감을 **시각+시간대**로, 남은 시간·D-day·평일 | 9 → 6 | 198 passed | 21.5s |
| 04 | [chrome-devtools-mcp 의 `a11y-debugging` 스킬](https://github.com/ChromeDevTools/chrome-devtools-mcp/tree/main/skills/a11y-debugging) + [Playwright MCP](https://github.com/microsoft/playwright-mcp) | [`a11y-lens`](day-04-a11y-lens/) — 브라우저 없이 **접근성 트리**와 WCAG 위반, 고친 뒤 확인 | 63+72 → 7 | 308 passed | 21.5s |
| 05 | [Figma-Context-MCP](https://github.com/GLips/Figma-Context-MCP) + [Stitch `design-md` 스킬](https://github.com/google-labs-code/stitch-skills/tree/main/plugins/stitch-utilities/skills/design-md) | [`design-spec`](day-05-design-spec/) — 디자인 파일에서 **색·간격·글자**를 세고 DESIGN.md | 2+1 → 8 | 321 passed | 21.5s |
| 06 | [Terraform MCP](https://github.com/hashicorp/terraform-mcp-server) + [AWS IaC MCP](https://github.com/awslabs/mcp/tree/main/src/aws-iac-mcp-server) | [`plan-guard`](day-06-plan-guard/) — apply 전에 plan: **사라지는 것·열린 포트·되돌리기** | 2 → 9 | 242 passed | 21.5s |

## 다음 화 만드는 법 (Day 02~)

1. **공개 MCP/스킬 2개 선정** — `gh repo view`로 실제 존재·라이선스·툴 수를 확인한다.
2. **`day-NN-슬러그/` 폴더** — `repo_context` 같은 패키지 + `tests/` + README(출처 링크·라이선스·아키텍처·설치·실행·한계).
3. **테스트 통과** — `python -m pytest`. 통과 못 한 항목은 올리지 않는다.
4. **릴스** — 직전 Day의 `reels/build_reels.py`·`build_audio.py`를 복사해 문구만 교체 → `reels-dayNN.mp4`(1080×1920 · 15~25초 · 30fps · 사운드 포함).
5. **캡션** — `instagram-caption.md`에 본문·해시태그·업로드 체크리스트.
6. **목록 표에 한 줄 추가**하고 커밋. 커밋은 `feat(day-NN)` / `test(day-NN)` / `docs(day-NN)` / `content(day-NN)`으로 나눈다.

> 릴스 제작에는 `ffmpeg`가 필요하다. 없으면 `pip install imageio-ffmpeg`로 받은 바이너리 경로를 `ffmpeg`로 심볼릭 링크해 쓴다.

## Day 06 미리보기

```bash
cd day-06-plan-guard
pip install -e ".[dev]"
plan-guard risk examples/proposal-plan.json --fail-on 치명   # 판정 보류 · 치명 4 · 심각 2 (exit 2)
plan-guard risk examples/fixed-plan.json                     # 판정 통과 · 0건 (exit 0)
plan-guard compare examples/proposal-plan.json examples/fixed-plan.json
```

```text
판정 **보류** · 치명 4 · 심각 2 · 보통 0 · 참고 0 · 규칙 6종

**치명 · 관리 포트가 인터넷에 열림** — `aws_security_group.api`
- 근거: tcp · 22 · 열린 관리 포트 22(SSH) · 출처 0.0.0.0/0

**치명 · 데이터가 있는 리소스가 재생성됨** — `aws_db_instance.main`
- 근거: aws_db_instance · 재생성 · 바꾼 속성 storage_encrypted (데이터 리소스)

치명 4 → 0 · 사라지는 리소스 2 → 0 · 판정 보류 → 통과
```

- 9개 툴: `read_plan` · `list_changes` · `diff_resource` · `risk_report` · `apply_order` · `rollback_plan` · `compare_plans` · `redact_plan` · `rule_catalog`
- 규칙 15종(데이터 재생성·관리 포트 개방·공개 버킷·IAM `*`·암호화 끔·스냅샷 없이 삭제…) · **바뀐 것만** 잡는다
- 예제 plan 은 **terraform 1.9.8 이 실제로 계산**한 것 (state 는 스키마에 맞춰 만든 예제 — `examples/infra/README.md`)
- 같은 비밀번호가 plan 파일 **5곳**에 평문으로 있다 → `redact` 후 0회
- 판정하지 않음: 비용·apply 결과·drift·처음 보는 리소스 타입
- 자세한 설명: [day-06-plan-guard/README.md](day-06-plan-guard/README.md)

## Day 05 미리보기

```bash
cd day-05-design-spec
pip install -e ".[dev]"
design-spec audit examples/demo/before.json   # 0/100 · 위반 17건 · 규칙 12종
design-spec audit examples/demo/after.json    # 100/100 · 위반 0건
design-spec design-md examples/demo/after.json
```

```text
- 화면 1개 · 노드 34개 · 글자 14개 · 색 10종 · 크기 6단계 · 간격 값 7종 (기준 4px)
- 점수 **0/100** (심각) · 위반 **17건** (치명 6 · 심각 2 · 보통 9) · 규칙 12종

1. **contrast-text** 글자 대비 2.53:1 (필요 4.5:1) — 치명
   - `e12` Body > Card/Order > 금액 안내
     고치기: #6F7378 로 바꾸면 4.56:1
3. **touch-target** 누를 수 있는 요소가 250×32 — 최소 44×44 — 치명
```

- 8개 툴: `read_design` · `find_in_design` · `palette_report` · `scale_report` · `audit_design` · `fix_order` · `write_design_md` · `overview`
- 규칙 17종(글자 대비·터치 44·글자 겹침·넘침·간격 스케일·거의 같은 색·글자 단계·1px 어긋남…) · 점수는 **규칙 종류당 한 번**만 감점
- 색 역할 추정 · WCAG 대비 계산 · 기준 단위 추정 · **DESIGN.md 다섯 칸** 자동 작성
- 실측: 같은 화면을 고치자 0 → 100점, 색 10 → 6종, 크기 6 → 4단계, 반경 5 → 2종, 토큰 커버리지 40% → 100%
- 안전·정직: 그라디언트·이미지 위 대비와 `lineHeight: auto` 는 **판정하지 않는다고 말함**, 색 이름은 기하 규칙으로만
- 자세한 설명: [day-05-design-spec/README.md](day-05-design-spec/README.md)

## Day 04 미리보기

```bash
cd day-04-a11y-lens
pip install -e ".[dev]"
a11y-lens snapshot examples/demo/before.html --depth 3
a11y-lens audit    examples/demo/before.html --max-per-rule 2
a11y-lens verify   examples/demo/before.html --baseline demo --save   # 고치기 전
a11y-lens verify   examples/demo/after.html  --baseline demo          # 고친 뒤
```

```text
document "예제몰 – 로그인"
  heading "로그인" level=1 · ref=e4 · L14
  heading "회원" level=4 · ref=e5 · L15      ← h2 단계가 없다
  textbox type=email · ref=e6 · L17          ← 이름이 없다
```

- 7개 툴: `snapshot_page` · `find_in_snapshot` · `audit_page` · `audit_site` · `fix_plan` · `verify_fixes` · `overview`
- 규칙 20종(WCAG 2.2 A·AA) · 브라우저 없음 → **원본 줄 번호 + CSS 선택자** · CI 종료 코드
- 안전·정직: 색 대비·터치 크기·키보드 순서는 **판정하지 않는다고 말함**, JS 렌더링 없음, 점수는 규칙 종류 기준
- 실측: W3C 접근성 데모 0 → 96점, github.com/login 100점(거짓 양성 0), 정부24 1007요소 0.23초
- 자세한 설명: [day-04-a11y-lens/README.md](day-04-a11y-lens/README.md)

## Day 03 미리보기

```bash
cd day-03-deadline-clock
pip install -e ".[dev]"
deadline-clock add "공모전 제출" "내일 오후 6시"
deadline-clock add "해커톤 마감" "2026-11-21 18:00 UTC"
deadline-clock ls
```

```text
[등록] 해커톤 마감
  dl_357e75 · 2026-11-22(일) 03:00 KST · D-3 · 2일 17시간 남음
                     ↑ UTC 21일 18:00 = 한국 시간 22일 새벽 3시
```

- 6개 툴: `add_deadline` · `list_deadlines` · `deadline_status` · `mark_done` · `preview_when` · `overview`
- 안전: IANA 대소문자 엄격 · 서머타임 **두 번/없음**을 숨기지 않음 · 임의 SQL 없음 · 같은 마감 중복 차단
- 자세한 설명: [day-03-deadline-clock/README.md](day-03-deadline-clock/README.md)

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
