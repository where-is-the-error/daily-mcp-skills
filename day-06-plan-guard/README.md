# plan-guard — terraform plan 을 apply 전에 읽는다

**1일 1스킬 Day 06.** 공개된 MCP·에이전트 스킬 두 개를 골라 하나로 섞는 시리즈의 여섯 번째입니다.

> `terraform plan` 이 `2 to add, 3 to change, 2 to destroy` 라고 말합니다.
> 그 두 개의 destroy 가 무엇인지는 말하지 않습니다.
> 이 서버는 plan JSON 하나로 **무엇이 사라지고, 어디가 열리고, 되돌릴 수 있는지**를 값과 함께 뽑습니다.

```bash
plan-guard risk examples/proposal-plan.json --fail-on 치명
```

```text
# apply 전 확인
판정 **보류** · 치명 4 · 심각 2 · 보통 0 · 참고 0 · 규칙 6종

**치명 · IAM 정책에 * 가 들어감** — `aws_iam_policy.app`
- 근거: 새로 생긴 와일드카드: Statement.Action=*
- 고치기: Action 은 필요한 API 목록으로, Resource 는 arn:aws:s3:::acme-prod-assets/* 처럼 대상으로 좁히세요.

**치명 · 관리 포트가 인터넷에 열림** — `aws_security_group.api`
- 근거: tcp · 22 · 열린 관리 포트 22(SSH) · 출처 0.0.0.0/0
- 고치기: VPN·배스천 대역이나 보안 그룹 참조로 출처를 좁히세요. 정말 필요하면 앱 포트(80/443)만 공개하세요.

**치명 · 버킷이 공개로 바뀜** — `aws_s3_bucket.assets`
- 근거: acl: private → public-read

**치명 · 데이터가 있는 리소스가 재생성됨** — `aws_db_instance.main`
- 근거: aws_db_instance · 재생성 · 바꾼 속성 storage_encrypted (데이터 리소스)

**심각 · 리소스가 삭제됨** — `aws_instance.worker`
**심각 · 스냅샷 없이 DB 를 지움** — `aws_db_instance.main`
- 근거: skip_final_snapshot = true
```

그리고 같은 state 로 다시 만든 "고친 plan" 과 비교하면:

```bash
plan-guard compare examples/proposal-plan.json examples/fixed-plan.json
```

```text
- 판정: **보류** → **통과**
- 치명 4 → 0 · 심각 2 → 0 · 보통 0 → 0
- 리소스 변경: 6 → 2
- 사라지는 리소스: 2 → 0

## 약해진 것 (좋아짐)
- aws_db_instance.main: 재생성 → 수정
- aws_iam_policy.app: 수정 → 변화 없음
- aws_instance.worker: 삭제 → 변화 없음
```

---

## 오늘 섞은 두 가지

| 원본 | 라이선스 | 무엇을 가져왔나 |
|---|---|---|
| [hashicorp/terraform-mcp-server](https://github.com/hashicorp/terraform-mcp-server) (공식 Terraform MCP) | **MPL-2.0** | **좁혀 보여 주는 방식** — 레지스트리·provider 문서를 통째로 주지 않고 *검색 → 정확한 문서 하나*로 좁히듯, plan 전체가 아니라 **주소 하나(`diff_resource`)** 로 좁혀 속성만 보여 주기. 도구를 작게 나누고 각 도구가 한 질문에만 답하는 구성 |
| [awslabs/mcp](https://github.com/awslabs/mcp) 의 [`aws-iac-mcp-server`](https://github.com/awslabs/mcp/tree/main/src/aws-iac-mcp-server) | **Apache-2.0** | **배포 전에 막는 태도** — ① 배포 실패를 **30여 가지 패턴으로 분류**하듯 삭제·재생성 사유를 라벨로 나누기, ② cfn-lint/cfn-guard 를 **차단 게이트**로 쓰듯 `--fail-on` 종료 코드, ③ best practice 를 링크가 아니라 **"고치기" 문장**으로 주기 |

- 두 저장소의 라이선스·규모는 `gh repo view` 로 확인했습니다 — terraform-mcp-server **MPL-2.0**, stars **1,561**, 마지막 푸시 2026-11-20 / awslabs/mcp **Apache-2.0**, stars **9,939**, 마지막 푸시 2026-11-21.
- **원본 코드는 한 줄도 복사하지 않았습니다.** 위에 적은 설계와 태도만 가져와 Python 표준 라이브러리로 새로 썼습니다.
- 툴 수: terraform-mcp-server 는 registry·module·policy·HCP Terraform 워크스페이스까지 여러 툴셋, aws-iac-mcp-server 는 **9개**(README 의 툴 목록) → 이 서버 **9개**.

### 원본과 이 서버는 무엇이 다른가

| | Terraform MCP | AWS IaC MCP | **plan-guard** |
|---|---|---|---|
| 입력 | 레지스트리·provider 문서·TFE | CloudFormation/CDK 템플릿 | **이미 계산된 plan JSON** |
| 클라우드 자격 증명 | provider 문서는 불필요, TFE 는 필요 | AWS 계정 필요 | **불필요** |
| 하는 일 | 문서·모듈 찾기 | 템플릿 검증·배포 실패 분석 | **apply 전 영향·위험·롤백** |
| "무엇이 사라지는가" | ✗ | ✗ | **✓ plan 의 before/after 로** |
| 되돌리기 계획 | ✗ | ✗ | **✓ 백업 명령·되돌릴 값** |
| plan 두 개 비교 | ✗ | ✗ | **✓ 치명 4 → 0** |
| CI 종료 코드 | ✗ | cfn-guard 계열 | **✓ `--fail-on 치명` → exit 2** |

Terraform 이 plan 을 만드는 일은 원본의 몫으로 두고, **만들어진 plan 을 사람이 apply 전에 읽는 자리**를 맡습니다.
브라우저도 클라우드 계정도 없이 도는 곳(PR 리뷰, 커밋 훅, 오프라인 검토)에서 씁니다.

---

## 툴 9개

| 툴 | 하는 일 |
|---|---|
| `read_plan` | 요약 — 생성/수정/재생성/삭제 개수, provider, 리소스 종류, 판정 한 줄 |
| `list_changes` | 바뀌는 리소스 목록 (`ref` r1…r6 고정) — 액션·바뀐 속성 개수·`kind` 필터 |
| `diff_resource` | 리소스 하나의 속성 diff — **목록 안쪽(보안 그룹 규칙)까지 짝지어**, 민감값은 «민감» |
| `risk_report` | 규칙 15종 → 판정(보류·주의·통과)·근거 값·**고치는 방법**. `severity` 필터 |
| `apply_order` | 쓰는 순서·지우는 순서 + **지우려는 것을 아직 참조하는 리소스** |
| `rollback_plan` | apply 전 백업 → 실패했을 때 → 끝났을 때 되돌리기 (명령은 제안) |
| `compare_plans` | plan 두 개 — 무엇이 약해졌고 무엇이 남았는지 |
| `redact_plan` | 민감값을 «민감» 으로 가린 **공유용 사본** (원본은 그대로) |
| `rule_catalog` | 규칙 목록과 **판정하지 않는 것** |

## 규칙 15종

| 등급 | 규칙 | 무엇을 잡나 |
|---|---|---|
| 치명 | `stateful-replace` | DB·버킷·볼륨·테이블이 **재생성**됨 (데이터는 따라오지 않는다) |
| 치명 | `stateful-destroy` | 데이터 리소스가 삭제됨 |
| 치명 | `open-admin-port` | 0.0.0.0/0·::/0 에 SSH(22)·RDP·DB(3306·5432)·Redis·MongoDB·K8s API 등 |
| 치명 | `open-all-ports` | `protocol=-1` + `0.0.0.0/0` (방화벽 해제) |
| 치명 | `public-bucket` | `acl = public-read` / 정책에 `Principal: "*"` |
| 치명 | `iam-wildcard` | 정책 문서에 **새로** 생긴 `Action`/`Resource` 의 `*` |
| 심각 | `destroy` | 리소스 삭제 (데이터 없는 것) |
| 심각 | `replace` | 재생성 — 주소·IP 가 바뀌고 그 사이 없다 |
| 심각 | `encryption-off` | 암호화를 true → false 로 |
| 심각 | `no-final-snapshot` | `skip_final_snapshot=true` 인 채로 DB 삭제·재생성 |
| 심각 | `deletion-protection-off` | 삭제 보호 true → false |
| 보통 | `public-ip` | 공인 IP 가 붙음 |
| 보통 | `secret-change` | 민감 속성이 바뀜 (값은 가림) |
| 보통 | `tag-loss` | 태그가 사라짐 |
| 참고 | `open-non-admin-port` | 80/443 같은 포트가 인터넷에 열림 |

**바뀐 것만 잡습니다.** 이전에도 열려 있던 `0.0.0.0/0:22` 는 그 규칙이 그대로면 다시 경고하지 않습니다
(그건 `compare_plans` 로 기준선 대비 볼 일입니다). 그래서 "이번 배포에서 새로 생긴 위험"만 남습니다.

## 실제 결과 (2026-11-22 실행)

예제는 **terraform 1.9.8 + AWS provider 3.76.1 이 실제로 계산한 plan** 입니다
(state 는 자격 증명 없이 plan 을 만들기 위해 provider 스키마에 맞춰 만든 것이고, plan 계산 자체는 terraform 이 합니다 — `examples/infra/README.md`).

| | 제안서 plan | 고친 plan |
|---|---|---|
| 바뀌는 리소스 | **6** (생성 1 · 수정 3 · 재생성 1 · 삭제 1) | **2** (생성 1 · 수정 1) |
| 사라지는 리소스 | **2** | **0** |
| 판정 | **보류** — 치명 4 · 심각 2 · 규칙 6종 | **통과** — 0건 |
| 걸린 것 | `stateful-replace`(storage_encrypted) · `open-admin-port`(22) · `public-bucket`(acl) · `iam-wildcard`(Action `*`) · `destroy`(worker) · `no-final-snapshot` | — |

- 속성 diff: `ingress[tcp/22-22].cidr_blocks[0]: 10.0.0.0/8 → 0.0.0.0/0` — 목록 순서가 바뀌어도 22번만 짚습니다.
- 재생성 diff: `storage_encrypted: false → true` + `(재생성이라 속성 37개는 적용 후에 정해집니다)`.
- **마스킹 실측**: proposal plan 28,890바이트 안에서 같은 비밀번호가 **5곳**에 평문으로 나왔습니다 —
  `resource_changes.before/after`, `planned_values`, `prior_state`, `configuration…constant_value`.
  `redact` 후 그 문자열은 0회 등장합니다.
- 속도: plan 읽기 **1.8ms** · 규칙 15종 검사 **0.6ms** (6리소스, 로컬).
- 순서: `aws_security_group.api` → `aws_db_instance.main`/`aws_instance.api` (참조 그래프가 `configuration` 의 `.id` 참조에서 나옴).

## 설치·실행

```bash
cd day-06-plan-guard
pip install -e ".[dev]"

plan-guard summary  examples/proposal-plan.json
plan-guard risk     examples/proposal-plan.json
plan-guard changes  examples/proposal-plan.json --kind delete
plan-guard diff     examples/proposal-plan.json aws_security_group.api
plan-guard order    examples/proposal-plan.json
plan-guard rollback examples/proposal-plan.json
plan-guard compare  examples/proposal-plan.json examples/fixed-plan.json
plan-guard redact   examples/proposal-plan.json -o plan.share.json
plan-guard rules
```

### MCP 서버 (stdio)

```json
{"mcpServers": {"plan-guard": {
  "command": "python", "args": ["-m", "plan_guard.server"],
  "env": {"PLAN_GUARD_ROOT": "/Users/me/infra"}}}}
```

### CI 에서

```bash
terraform plan -out=tfplan && terraform show -json tfplan > plan.json
plan-guard risk plan.json --fail-on 치명    # 치명이 하나라도 있으면 exit 2
```

### 입력 형식

`terraform show -json tfplan` 의 출력 그대로. `format_version` 1.x 만 읽고, `resource_changes` 만 잘라 온
조각도 받습니다. 없는 값(`after_unknown`)은 `(적용 후 결정)` 으로 표시합니다.

## 한계 (계산한 척하지 않는 것)

- **비용은 판정하지 않습니다.** 요금표도, 사용량도 없습니다. `plan` 에 돈이 나오지 않습니다.
- **apply 결과를 보장하지 않습니다.** provider 가 apply 시점에 정하는 값, API 오류, 타임아웃은 plan 밖입니다.
- **`-refresh=false` 로 만든 plan 은 drift 를 담지 않습니다.** plan 을 만든 방식은 plan 이 말해 주지 않으므로, 우리도 말하지 않습니다.
- **규칙은 리소스 타입 목록 안에서만 돕습니다.** AWS·GCP·Azure·DigitalOcean·Kubernetes 의 알려진 타입(보안 그룹, 버킷, DB, IAM, 볼륨)만 압니다. 처음 보는 타입은 삭제·재생성만 셉니다.
- **낡았던 위험은 다시 말하지 않습니다.** "바뀐 것만" 보기 때문입니다.
- **민감값은 terraform 이 표시한 것 + 이름 규칙(password·secret·token·key…)으로만** 가립니다. 둘 다 아닌 비밀은 남습니다. `redact` 는 사본을 만들 뿐 원본을 지우지 않습니다.
- **롤백 명령은 제안입니다.** 계정·리전·식별자를 사람이 확인해야 하고, 데이터 리소스는 "되돌리기"가 아니라 **복원**입니다.
- state 를 읽지 않습니다 — plan JSON 만 봅니다.

## 파일

```
day-06-plan-guard/
├── plan_guard/
│   ├── plan.py         # plan JSON → Plan/Change, 민감값 마스킹
│   ├── differences.py  # 속성 diff (목록은 식별자로 짝짓기)
│   ├── risks.py        # 규칙 15종
│   ├── order.py        # 참조 그래프 · 쓰는/지우는 순서 · 막히는 곳
│   ├── rollback.py     # 되돌리기 계획
│   ├── compare.py      # plan 두 개 비교
│   ├── redact.py       # 공유용 마스킹 (5곳을 모두 본다)
│   ├── report.py       # 출력 문장
│   ├── server.py       # MCP 9툴 (stdio)
│   └── cli.py          # CLI
├── examples/
│   ├── proposal-plan.json  # terraform 이 계산한 '위험한' plan
│   ├── fixed-plan.json     # 같은 state 에서 고친 plan
│   ├── sample-review.md    # 위 명령들의 실제 출력
│   └── infra/              # plan 을 만든 .tf · state · 재현 절차
├── tests/                  # 242
└── reels/                  # 릴스 생성기
```

## 테스트

```bash
python -m pytest        # 242 passed
```

`plan 52 · differences 40 · risks 49 · order 17 · rollback 18 · compare+redact 22 · cli 27 · server 17`
— in-memory MCP 클라이언트와 **stdio 서브프로세스**로 실제 서버를 띄워 부르는 테스트를 포함합니다.

## 라이선스

이 코드는 MIT. 원본 두 프로젝트(Terraform MCP **MPL-2.0**, AWS IaC MCP **Apache-2.0**)의 코드를 포함하지 않습니다.
