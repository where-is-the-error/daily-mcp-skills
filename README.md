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
| 07 | [DBHub](https://github.com/bytebase/dbhub) + [Postgres MCP Pro](https://github.com/crystaldba/postgres-mcp) | [`migrate-guard`](day-07-migrate-guard/) — 마이그레이션 실행 전: **락·재작성·되돌리기** | 5+9 → 9 | 322 passed | 21.5s |
| 08 | [Excel MCP Server](https://github.com/haris-musa/excel-mcp-server) + [MarkItDown](https://github.com/microsoft/markitdown) | [`sheet-guard`](day-08-sheet-guard/) — 표를 쓰기 전에: **인코딩·소계 행·앞자리 0·칸 밀림** | 9 | 324 passed | 21.5s |
| 09 | [Grafana MCP](https://github.com/grafana/mcp-grafana) + [ClickHouse MCP](https://github.com/ClickHouse/mcp-clickhouse) | [`log-triage`](day-09-log-triage/) — 로그를 넘기기 전에: **서명·폭주·첫 오류·스택·마스킹** | 134+4 → 11 | 304 passed | 21.5s |
| 10 | [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) + [GitHub MCP Server](https://github.com/github/github-mcp-server) | [`test-radar`](day-10-test-radar/) — 바뀐 코드에 **닿는 테스트만**, 확신 없으면 전체 실행 | 17+96 → 10 | 308 passed | 21.5s |
| 11 | [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) + [humanizer](https://github.com/blader/humanizer) | [`publish-guard`](day-11-publish-guard/) — 올리기 전 **파일 규격·음량·safe zone·AI 글투**, 고쳐도 사실은 안 지움 | 42+26 → 10 | 389 passed | 21.5s |

## 다음 화 만드는 법 (Day 02~)

1. **공개 MCP/스킬 2개 선정** — `gh repo view`로 실제 존재·라이선스·툴 수를 확인한다.
2. **`day-NN-슬러그/` 폴더** — `repo_context` 같은 패키지 + `tests/` + README(출처 링크·라이선스·아키텍처·설치·실행·한계).
3. **테스트 통과** — `python -m pytest`. 통과 못 한 항목은 올리지 않는다.
4. **릴스** — 직전 Day의 `reels/build_reels.py`·`build_audio.py`를 복사해 문구만 교체 → `reels-dayNN.mp4`(1080×1920 · 15~25초 · 30fps · 사운드 포함).
5. **캡션** — `instagram-caption.md`에 본문·해시태그·업로드 체크리스트.
6. **목록 표에 한 줄 추가**하고 커밋. 커밋은 `feat(day-NN)` / `test(day-NN)` / `docs(day-NN)` / `content(day-NN)`으로 나눈다.

> 릴스 제작에는 `ffmpeg`가 필요하다. 없으면 `pip install imageio-ffmpeg`로 받은 바이너리 경로를 `ffmpeg`로 심볼릭 링크해 쓴다.

## Day 11 미리보기

```bash
cd day-11-publish-guard
pip install -e ".[dev]"
publish-guard check reels-day11.mp4 --caption instagram-caption.md --section auto
publish-guard rules            # 규칙 64종 (AI 글투 21종 포함)
python tools/audit.py --public samples/*.webm   # 릴스 10편 + 공개 표본 실측
```

```text
발행 전 검사 — reels-day11.mp4
  21.50초 · 1080×1920 (세로) · 30.00fps · h264 High · yuv420p
  소리: -15.1 LUFS (목표 -14.0 ±1.5) · 트루피크 -2.0 dBTP (한계 -1.0)
캡션: 11자 훅 · 1323자 전체 · 해시태그 5개

판정: 통과 (100/100)
  막음 0 · 주의 0 · 참고 1 · 상자 0개

플랫폼별
  YouTube Shorts: 통과 (100/100)
  Instagram Reels: 통과 (100/100)
  TikTok: 통과 (100/100)
```

```
Day 10 (test-radar):    30/100 · 보류   true-peak-over, caption-too-long ×2
Day 11 (publish-guard): 100/100 · 통과  상자 10개 · -15.1 LUFS · -2.0 dBTP
```

## Day 09 미리보기

```bash
cd day-09-log-triage
pip install -e ".[dev]"
log-triage read examples/api-after.log                    # 요약 + 상위 서명
log-triage compare examples/api-before.log examples/api-after.log
log-triage problems examples/messy-export.log             # 치명 있으면 exit 2
```

```text
↔ examples/api-before.log → examples/api-after.log
   창 30.0분 → 30.0분 · 레코드 1,429 → 1,448
   ERROR/CRITICAL 3 → 291 (0.1/분 → 9.7/분, 97.0배)
   새로 생김 2 · 사라짐 1 · 사라짐(드묾) 1 · 그대로 2
   + 새로 생김     0 → 291 (9.7/분)  PoolTimeoutError: could not get connection from pool <n> after <n>
   + 새로 생김     0 → 125 (4.2/분)  pool in_use=<n> wait_ms=<n>
   − 사라짐        3 →   0           ConnectionResetError: connection reset by peer
```

- 11개 툴: `read_logs` · `signature_report` · `rate_report` · `compare_logs` · `stack_report` · `timeline` · `find_text` · `redact_secrets` · `find_problems` · `rule_catalog` · `overview`
- 규칙 25종(시각·오프셋·레벨 표기·폭주·끊김·재시도·긴 줄·제어 문자·깨진 글자·비밀·개인정보…)
- 실측: 실제 공개 로그 **14종 28,000줄 → 26,357 레코드 · 버린 줄 0 · 파싱 717ms** (`tools/corpus_probe.py`)
- 읽기 전용 · 원본 불변 · 마스킹본은 새 파일 · **남은 비밀 0** 확인 · 판정 못 한 것은 결과에 표기

## Day 08 미리보기

```bash
cd day-08-sheet-guard
pip install -e ".[xlsx,dev]"
sheet-guard read examples/raw_population.csv        # 인코딩·머리글·열 요약
sheet-guard problems examples/raw_population.csv    # 규칙 위반 (치명 있으면 exit 2)
sheet-guard clean examples/raw_population.csv --out out/clean.csv
```

```text
📄 examples/raw_population.csv
   인코딩 CP949(확신 0.81) · 구분자 , · 48행 × 9열
   머리글 1줄, 앞머리 2줄 뺌
   판정: 치명 2 · 주의 9 · 참고 5

✅ 적용 완료 — 값 157칸 · 뺀 행 8개 · 격리 1행 · 새 열 면적_단위
🔍 정리 전 48행 → 정리 후 46행 · 짝지은 행 46 (95.8% 유지) · 값 손실 0
```

- 9개 툴: `read_table` · `profile_columns` · `find_problems` · `clean_plan` · `apply_plan` · `to_markdown` · `compare_tables` · `rule_catalog` · `overview`
- 규칙 35종(CP949·BOM·제목 줄·2줄 머리글·소계 행·앞자리 0·날짜 3종·천 단위 쉼표·값 안의 단위·전각 숫자·병합 칸·칸 밀림…)
- 실측: 행정안전부 주민등록 연령별 인구 **298행 × 79열** → 19,760칸 정리 · **값 손실 0** · 읽기 144ms
- 원본 불변 · `changes.csv` · 단위 열 보존 · 칸 밀린 행 격리 · 적용 뒤 `compare_tables` 로 대조

## Day 07 미리보기

```bash
cd day-07-migrate-guard
pip install -e ".[dev]"
migrate-guard summary examples/0012_add_email_verified.up.sql --baseline examples/schema.sql --rows examples/stats.json
migrate-guard rollout examples/0012_add_email_verified.up.sql --baseline examples/schema.sql --rows examples/stats.json
migrate-guard compare examples/0012_add_email_verified.up.sql examples/0012_add_email_verified.fixed.up.sql \
  --baseline examples/schema.sql --rows examples/stats.json
```

```text
# 0012_add_email_verified.up.sql
문장 8개 · 표 4개 · 판정 **보류** · 최대 잠금 12분 (events · ACCESS EXCLUSIVE)
- BEGIN…COMMIT 하나로 묶여 있음 → 락이 커밋까지 유지 (합계 13분)

치명: 3 → 0 · 심각: 8 → 0 · 락 유지 13분 → 0.02초 · 판정 보류 → 통과
```

- 9개 툴: `read_migration` · `list_statements` · `lock_report` · `risk_report` · `rollout_plan` · `rollback_plan` · `schema_change` · `compare_migrations` · `rule_catalog`
- 규칙 24종(조건 없는 UPDATE·휘발성 기본값 재작성·`SET NOT NULL` 스캔·트랜잭션 안 CONCURRENTLY·외래키 전체 검증…)
- 하는 일: 문장을 나누고(주석·문자열·`$$` 안의 `;` 무시) → PostgreSQL 락 모드와 비용을 붙이고 → 확장·백필·전환으로 다시 씀
- 실측: **실제 마이그레이션 241개 612문장**(mattermost) 예외 0 · 분류 밖 0 · SQLite 카탈로그 20컬럼 **불일치 0**
- 판정하지 않음: 실행 시간의 실측·지금 잡힌 락·복제 지연·데이터 분포(모델 가정을 결과에 명시)
- 자세한 설명: [day-07-migrate-guard/README.md](day-07-migrate-guard/README.md)

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
