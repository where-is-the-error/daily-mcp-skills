# log-triage — 로그를 넘기기 전에 읽는다

장애가 나면 사람은 로그 파일 네 개를 받는다. 4만 줄. 그 안에서 같은 에러가 ID만 바꿔
800번 반복되고, 첫 발생은 14:10이고, 배포는 14:09에 있었다. 이걸 눈으로 찾는 데 20분이
걸린다. **log-triage**는 파일을 읽고 **무엇이·언제부터·얼마나**를 먼저 말한다 —
같은 메시지를 서명으로 묶고, 분당 비율로 폭주와 끊김을 찾고, before/after를 비교해
새로 생긴 서명만 남기고, 스택에서 터진 위치를 고르고, 넘기기 전에 비밀을 지운다.

- MCP 서버(stdio) + CLI, 툴 11개, 규칙 25종, pytest **304 passed**
- 표기 14종(ISO·syslog·Apache·HDFS·logcat·epoch…), 인코딩(UTF-8·CP949·UTF-16·BOM), JSON 줄, 여러 줄 스택
- **버린 줄 0** — 시각을 못 읽은 줄도 앞 사건에 붙이거나 첫 사건 앞 줄로 남긴다
- 읽기 전용. 원본을 고치지 않고, 마스킹본은 새 파일로만 쓴다

## 조합한 공개 소스 2개

| 원본 | 라이선스 | 규모 | 가져온 것 | 가져오지 않은 것 |
|---|---|---|---|---|
| [grafana/mcp-grafana](https://github.com/grafana/mcp-grafana) (Grafana MCP) | **Apache-2.0** | ★3,699 · 마지막 푸시 2026-11-24 · 소스의 툴 등록 142건 · 이름 134개 | **좁혀서 묻는 순서** — 라벨/시간 범위를 먼저 정하고 그 안에서만 질의하며, 원본 대신 **요약**(dashboard summary·property)을 돌려줘 컨텍스트를 아끼고, 쓰기 툴은 기본으로 꺼 둔다는 태도 | Go 코드, Grafana API 클라이언트, Prometheus·Loki·CloudWatch 질의, 대시보드 편집 |
| [ClickHouse/mcp-clickhouse](https://github.com/ClickHouse/mcp-clickhouse) (ClickHouse MCP) | **Apache-2.0** | ★918 · 마지막 푸시 2026-11-16 · 툴 4개 | **읽기 전용이 기본**(`CLICKHOUSE_ALLOW_WRITE_ACCESS=false`), 스키마를 먼저 확인하고, 결과에 **상한과 페이지**를 두고, 질의를 실행하기 전에 `DESCRIBE`/`EXPLAIN ESTIMATE`로 먼저 본다는 습관 | Rust 코드, ClickHouse 연결·인증(OAuth/OIDC), chDB, SQL 실행 엔진 |

두 원본의 코드를 복사하지 않았다. **설계와 태도만** 가져와 새로 썼다.

* Grafana MCP → 로그를 **한 번에 다 읽지 않는다**. 좁히고(시간·라벨) → 세고 → 필요한 것만
  본다. 여기서는 그것을 순서로 만든다: `read_logs` → `signature_report` → `rate_report` →
  (필요할 때만) `timeline`·`stack_report`. 원본이 큰 대시보드 JSON 대신 요약을 주듯,
  여기서는 원문 대신 **서명과 비율**을 준다.
* ClickHouse MCP → **읽기 전용이 기본값**이고, 쓰기는 명시적으로만. 여기서는 파일을 열어도
  고치지 않고, 마스킹본만 새 경로에 쓰며, 모든 비교는 비율(분당)로 한다 — 절대 개수는
  창 길이에 속아서.

## 무엇을 하는가

**읽기** — 시각을 읽고(표기 14종), 레벨을 맞추고, 여러 줄을 한 사건으로 묶는다.
시각이 없는 줄은 앞 사건에 붙이고, 붙일 곳이 없으면 목록에 남긴다(버리지 않는다).

**묶기** — 같은 메시지를 하나로. 숫자·UUID·IP·경로·요청 ID·상품 코드를 걷어낸 뼈대가
서명이다. `PoolTimeoutError: pool 7 after 5000ms (request=8f3c…)` 와 `pool 12 … (request=aa1e…)`는
같은 서명이 된다.

**세기** — 구간별 개수, **오류만 따로** 센 폭주(전체 줄 수는 트래픽에 따라 평평해서 오류가
묻힌다), 끊긴 구간, 같은 초에 몰린 재시도, 시각이 뒤로 간 줄.

**비교** — before/after를 **분당 비율**로. 새로 생김 / 사라짐 / 늘어남 / 줄어남. 한 번만
본 것은 `새로 생김(드묾)`으로 따로 — 한 번 본 에러로 배포를 되돌리면 그게 더 큰 사고다.

**위치** — 스택에서 가장 안쪽 프레임. Python은 마지막, Java·Node는 첫 번째, Go는 `panic:`
다음 첫 함수. 언어를 모르면 위치를 **비우고 그렇다고 말한다**.

**넘기기 전** — 비밀번호·토큰·JWT·AWS 키·쿠키·카드·전화·이메일·IP를 종류 이름으로 바꾸고,
바꾼 뒤 같은 탐지기를 다시 돌려 **남은 것 0**을 확인한다.

## 툴 11개

| 툴 | 하는 일 |
|---|---|
| `read_logs(path, assume_year)` | 인코딩·시각 표기·레벨·구간·서명 요약 + `ref` |
| `signature_report(ref, limit)` | 서명별 개수·비율·처음/마지막 시각·예시 |
| `rate_report(ref, bucket_seconds)` | 구간 중앙값·최대, 오류 폭주, 끊김, 같은 초 반복, 시각 역행 |
| `compare_logs(ref_before, ref_after)` | 분당 비율 비교 — 새로 생김/사라짐/늘어남/줄어남 |
| `stack_report(ref, limit)` | 예외 종류·가장 안쪽 프레임·인과 깊이·서로 다른 스택 수 |
| `timeline(ref, baseline_ref, gap_minutes)` | 첫 오류·직전 정상 줄·에피소드·처음 등장 순서 |
| `find_text(ref, pattern, context, regex)` | 원본 줄 번호와 앞뒤 줄로 검색 |
| `redact_secrets(ref, out)` | 마스킹본 저장 + 남은 것 0 확인 (원본 불변) |
| `find_problems(ref, now)` | 규칙 25종 위반 + 고치는 순서 |
| `rule_catalog(rule)` | 규칙 목록 / 규칙 하나의 '왜·어떻게' |
| `overview()` | 이 서버가 무엇을 하고 무엇을 판정하지 않는지 |

CLI도 같은 일을 한다.

```bash
log-triage read logs/api-after.log            # 요약 + 상위 서명
log-triage sigs logs/api-after.log --limit 8
log-triage rates logs/api-after.log
log-triage compare logs/api-before.log logs/api-after.log
log-triage stack logs/api-after.log
log-triage timeline logs/api-after.log --baseline logs/api-before.log
log-triage find logs/api-after.log PoolTimeout --context 3
log-triage redact logs/messy.log --out out/masked.log   # 남은 값 있으면 exit 2
log-triage problems logs/messy.log                      # 치명 exit 2, 주의 exit 1
log-triage catalog secret-in-log
```

## 규칙 25종

**읽기·시각** — `no-timestamp`(치명) `partial-timestamp` `orphan-lines` `no-timezone`
`mixed-timezones` `out-of-order` `future-timestamp` `year-assumed` `time-gap` `mixed-formats`
`mojibake`
**레벨** — `unknown-level` `level-case-mixed` `error-without-trace` `trace-without-error`
**모양** — `empty-message` `one-line-storm` `retry-storm` `error-burst` `long-line` `control-chars`
**유출** — `secret-in-log`(치명) `pii-in-log`
**추적** — `no-request-id` `unparsed-stack`

## 실측 (2026-11-25)

### 1. 장애 두 창 — 배포 전/후

`examples/api-before.log` → `examples/api-after.log` (합성. 아래 2번은 실제 공개 로그다.)

```text
↔ before → after
   창 30.0분 → 30.0분 · 레코드 1,429 → 1,448
   ERROR/CRITICAL 3 → 291 (0.1/분 → 9.7/분, 97.0배)
   새로 생김 2 · 사라짐 1 · 사라짐(드묾) 1 · 그대로 2
   + 새로 생김    0 → 291 (9.7/분)  PoolTimeoutError: could not get connection from pool <n> after <n>
   + 새로 생김    0 → 125 (4.2/분)  pool in_use=<n> wait_ms=<n>
   − 사라짐       3 →   0           ConnectionResetError: connection reset by peer
   · 사라짐(드묾)  2 →   0           slow query
```

- 첫 오류 **14:10:05.395**, 직전 정상 줄 14:10:04.853, 오류 구간 **19.9분**, 에피소드 1개
- 오류 폭주는 **14:18 한 구간 27건(평소 12.5건/분의 2.2배)** — 전체 줄 수는 44건/분으로 평평해서,
  전체만 세면 이 폭주가 안 보인다. 그래서 오류를 따로 센다.
- 스택 291건 전부 `acquire (pool.py:64)` — 서명 1개, 서로 다른 스택 1개

### 2. 실제 공개 로그 14종 (Loghub 2,000줄 샘플)

`python3 tools/corpus_probe.py --md` — 파일은 내려받아 분석만 하고 저장소에 넣지 않는다.

| 코퍼스 | 줄 | 레코드 | 시각 읽음 | 버린 줄 없음 | 서명 | 최다 비중 | ERROR | 기간 | 인코딩 | 규칙(치명/주의/참고) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| HDFS | 2,000 | 1,057 | 52.9% | 100.0% | 6 | 29% | 0 | 2264분 | utf-8 | 0/2/3 |
| Apache | 2,000 | 2,000 | 100.0% | 100.0% | 6 | 42% | 595 | 2308분 | utf-8 | 0/5/3 |
| Linux | 2,000 | 2,000 | 100.0% | 100.0% | 162 | 13% | 43 | 61886분 | utf-8 | 0/4/5 |
| Mac | 2,000 | 2,000 | 100.0% | 100.0% | 577 | 4% | 8 | 10030분 | utf-8 | 1/4/5 |
| Zookeeper | 2,000 | 2,000 | 100.0% | 100.0% | 63 | 16% | 13 | 38505분 | utf-8 | 1/3/3 |
| OpenStack | 2,000 | 2,000 | 100.0% | 100.0% | 44 | 40% | 0 | 15분 | utf-8 | 0/2/2 |
| HPC | 2,000 | 1,932 | 96.6% | 100.0% | 63 | 20% | 0 | 1432280분 | utf-8 | 0/4/3 |
| Proxifier | 2,000 | 2,000 | 100.0% | 100.0% | 572 | 20% | 0 | 138711분 | utf-8 | 0/4/3 |
| HealthApp | 2,000 | 1,368 | 68.4% | 100.0% | 55 | 15% | 0 | 102분 | utf-8 | 0/3/4 |
| BGL | 2,000 | 2,000 | 100.0% | 100.0% | 529 | 36% | 1 | 307650분 | utf-8 | 0/3/5 |
| Spark | 2,000 | 2,000 | 100.0% | 100.0% | 388 | 19% | 0 | 1분 | utf-8 | 0/2/1 |
| Android | 2,000 | 2,000 | 100.0% | 100.0% | 207 | 10% | 3 | 3분 | utf-8 | 1/1/4 |
| Thunderbird | 2,000 | 2,000 | 100.0% | 100.0% | 806 | 3% | 0 | 15분 | utf-8 | 0/2/1 |
| Windows | 2,000 | 2,000 | 100.0% | 100.0% | 952 | 14% | 0 | 1294분 | utf-8 | 1/3/1 |

**합계 14개 코퍼스 · 28,000줄 → 레코드 26,357 (94.1%) · 남은 줄 0 · 파싱 717ms**

- `시각 읽음 94.1%` 는 실패가 아니다. HDFS·HealthApp 은 스택·이어짐 줄이 많아 **레코드 수가
  줄 수보다 적은 것**이고, 그 줄들은 전부 앞 사건에 붙었다(버린 줄 100.0%→0).
- `맨 앞이 아닌 시각`도 읽는다: HPC는 노드 이름 뒤 **epoch**, BGL은 `2005-06-03-15.42.50.675872`.
- 기간이 1,432,280분(2.7년)인 HPC·BGL에서 1분 버킷을 다 메우면 130만 개가 되므로, 구간이
  길면 **관측된 버킷만** 쓰고 끊김은 레코드 사이 간격으로 직접 잰다.

### 3. 넘기기 전에 걸리는 것 — `examples/messy-export.log`

```text
🚨 규칙 위반 13종 (치명 1 · 주의 7 · 참고 5)
   1. [치명] 비밀번호·토큰이 찍힘 — 4건   password 1, api_key 1, jwt 1, aws_key 1
   5. [주의] 개인정보로 보이는 값 — 3건   email 1, card 1, phone 1
   … 한 서명 68% · 같은 초 5회 반복 · 제어 문자 · 깨진 글자 · 2,000자 넘는 SQL
```

```text
🕶 지운 값 7개 · 바뀐 줄 4/60 · password 1, api_key 1, email 1, card 1, phone 1, jwt 1, aws_key 1
   남은 것: 0개 (0 확인)
```

- 카드번호는 **Luhn 검사**를 통과할 때만 지운다 — 그래서 `2026-11-25T10:40:47` 같은 시각은
  건드리지 않는다(거짓 양성 0).
- 값은 돌려주지 않는다. 종류와 개수만 남긴다.

### 4. 한 파일에 섞인 표기 — `examples/formats.log`

19줄 → 레코드 13개, 시각 표기 **8가지**(iso 4 · json 2 · apache 2 · syslog 1 · hdfs 1 · spark 1 ·
android 1 · time-only 1), 오프셋 3종(없음 8 · +09:00 3 · UTC 2). `mixed-timezones`·
`mixed-formats`·`no-timezone` 이 그대로 잡힌다.

`examples/korean-cp949.log` — CP949(확신 **1.00**)로 읽고 `[결제] 결제 승인 실패` 를 그대로 보존.

### 5. 속도 (100,000줄, 이 환경)

| 단계 | 시간 |
|---|---|
| 파싱(디코딩·시각·레벨·묶음) | **1.6초** |
| 서명 묶기 | **1.4초** |
| 규칙 25종 + 마스킹 검사 | **2.7초** |

서명은 레코드에 한 번 계산해 남긴다(집계·규칙·타임라인이 같이 쓴다). 마스킹은 13개 정규식을
모든 줄에 돌리지 않고, 값의 모양(`@`, `=`, 13자리 숫자…)으로 먼저 거른다.

## 설치·실행

```bash
pip install -e ".[dev]"
python -m log_triage.cli overview
python -m pytest                     # 304 passed
python examples/build_examples.py    # 예제 로그 재생성
```

MCP 클라이언트:

```json
{"mcpServers": {"log-triage": {
  "command": "python", "args": ["-m", "log_triage.server"],
  "env": {"LOG_TRIAGE_ROOT": "/Users/me/logs"}}}}
```

## 판정하지 않는 것 (도구가 아는 척하지 않는 경계)

- **로그 내용이 사실인지** — 로그는 거짓말도 한다. 이 도구는 모양만 본다.
- **지표가 정상 범위인지** — 폭주는 '평소의 몇 배'로만 말한다(중앙값). 계절성·트래픽 증가는 모른다.
- **장애의 원인** — 첫 오류 시각과 서명을 줄 뿐, 원인은 사람이 정한다.
- **배포·설정 이력** — 배포가 14:09에 있었는지는 다른 곳에서 확인해야 한다.
- **시각의 정확성** — 오프셋 없는 시각은 UTC로 가정한다(그 사실을 `no-timezone` 이 알린다).
  벽시계가 틀린 서버는 `future-timestamp`·`out-of-order` 로만 흔적이 남는다.
- **색 대비·렌더링 같은 시각 품질** — 로그 뷰어의 일이다.
- **프레임 순서를 모르는 언어** — 스택 위치를 비우고 `unparsed-stack` 으로 남긴다.
- **압축·회전된 로그(`.gz`, `logrotate` 결과)** — 지금은 평문 파일만 읽는다.

## 예제 파일

| 파일 | 무엇 | 성격 |
|---|---|---|
| `examples/api-before.log` | 배포 전 30분, 정상 트래픽 + 드문 클라이언트 오류 3건 | 합성 |
| `examples/api-after.log` | 배포 후 30분, 새 `PoolTimeoutError` 291건 | 합성 |
| `examples/formats.log` | 한 파일에 섞인 8가지 시각 표기 + JSON 줄 + 스택 | 합성 |
| `examples/korean-cp949.log` | CP949 로 저장한 한국어 로그 | 합성 |
| `examples/messy-export.log` | 비밀·개인정보·긴 줄·제어 문자·깨진 글자 | 합성 |
| `examples/messy-export.masked.log` | 위 파일의 마스킹본(남은 것 0) | 생성물 |

실제 공개 로그 측정은 `tools/corpus_probe.py` 로만 한다(파일 저장소 미포함).

## 라이선스

이 저장소의 코드는 MIT. 원본 두 프로젝트는 **Apache-2.0** 이며, 코드를 복사하지 않고
설계만 참고했다(위 표의 '가져온 것').
