# 실제 출력 (2026-11-22, terraform 1.9.8 + AWS provider 3.76.1 이 만든 plan)

## 1) 제안서 plan — `plan-guard risk examples/proposal-plan.json`

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
- 고치기: acl 은 private 로 두고, 정말 공개할 객체만 별도 경로·버킷으로 나누세요.

**치명 · 데이터가 있는 리소스가 재생성됨** — `aws_db_instance.main`
- 근거: aws_db_instance · 재생성 · 바꾼 속성 storage_encrypted (데이터 리소스)
- 고치기: 새 리소스를 만들어 옮기고(스냅샷 복원·버킷 복사), 이번 plan 에서는 바꾸지 마세요. 제자리 변경이 되는 속성인지 provider 문서를 확인하세요.

**심각 · 리소스가 삭제됨** — `aws_instance.worker`
- 근거: aws_instance 삭제
- 고치기: 지워도 되는지 확인하세요. 남겨야 하면 설정에 다시 넣고(또는 `terraform state rm` 은 마지막 수단) plan 을 다시 만드세요.

**심각 · 스냅샷 없이 DB 를 지움** — `aws_db_instance.main`
- 근거: skip_final_snapshot = true
- 고치기: apply 전에 손으로 스냅샷을 뜨거나 skip_final_snapshot = false 로 두고 final_snapshot_identifier 를 지정하세요.
```

## 2) 리소스 하나 — `plan-guard diff examples/proposal-plan.json aws_security_group.api`

```text
# aws_security_group.api [수정] r6

바뀜 1 · 생김 0 · 사라짐 0
- ingress[tcp/22-22].cidr_blocks[0]: 10.0.0.0/8 → 0.0.0.0/0
```

## 3) 순서 — `plan-guard order examples/proposal-plan.json`

```text
# 적용 순서

쓰는 순서 (의존하는 것 먼저):
  1. aws_iam_policy.app [수정]
  2. aws_s3_bucket.assets [수정]
  3. aws_security_group.api [수정]
  4. aws_db_instance.main [재생성]  ← aws_security_group.api
  5. aws_instance.api [생성]  ← aws_security_group.api

지우는 순서 (참조하는 것 먼저):
  1. aws_instance.worker [삭제]
  2. aws_db_instance.main [재생성]
```

## 4) 되돌리기 — `plan-guard rollback examples/proposal-plan.json`

```text
# 되돌리기 계획
- 사라지는 리소스 2개 (데이터 1개) — apply 전에 백업 필요

### 1. apply 전에 (지금 상태를 붙잡아 둔다)
    terraform state pull > before-deploy.tfstate      # state 백업(손으로 보관)
    cp {plan 파일} before-plan.json                    # 이 plan 도 보관

### 2. 사라지는 것 2개 — 미리 백업
  - aws_db_instance.main [재생성]
    이전 값: identifier=acme-prod-db, name=acme, username=acme, password=«민감», engine=postgres
    제안: aws rds create-db-snapshot --db-instance-identifier acme-prod-db --db-snapshot-identifier acme-prod-db-pre-{날짜}
  - aws_instance.worker [삭제]
    이전 값: instance_type=t3.small, ami=ami-0d5bb1d3b6b3f2e5a
    제안: aws ec2 create-image --instance-id i-0d4c2b1a9f8e7d6c5 --name pre-deploy-{날짜} --no-reboot

### 3. 문제가 생겼을 때 되돌리기
    a) apply 가 실패했으면: terraform apply 는 실패한 리소스까지만 바꿨습니다. plan 을 다시 만들어 확인하세요.
    b) apply 가 끝났으면: 아래 값을 설정에서 이전으로 돌리고 plan 을 다시 만드세요.
  - aws_db_instance.main
    storage_encrypted = false  (지금 값 true)
    c) 데이터 리소스는 '되돌리기'가 아니라 '복원'입니다 — 2번에서 뜬 스냅샷으로 새 리소스를 만드세요.

주의: 위 명령의 식별자·날짜는 plan 값에서 만든 제안입니다. 실행 전에 계정·리전을 확인하세요.
```

## 5) 고친 뒤 — `plan-guard compare examples/proposal-plan.json examples/fixed-plan.json`

```text
# 두 plan 비교  (examples/proposal-plan.json → examples/fixed-plan.json)

- 판정: **보류** → **통과**
- 치명 4 → 0 · 심각 2 → 0 · 보통 0 → 0
- 리소스 변경: 6 → 2
- 사라지는 리소스: 2 → 0

## 약해진 것 (좋아짐)
- aws_db_instance.main: 재생성 → 수정
- aws_iam_policy.app: 수정 → 변화 없음
- aws_instance.worker: 삭제 → 변화 없음
- aws_s3_bucket.assets: 수정 → 변화 없음
- aws_security_group.api: 수정 → 변화 없음

주의: plan 두 개가 같은 state 에서 나왔는지 확인하세요. state 가 다르면 비교가 어긋납니다.
```

## 6) 고친 plan 자체 — `plan-guard risk examples/fixed-plan.json`

```text
# apply 전 확인
판정 **통과** · 걸린 규칙 없음

이 plan 에서 새로 생기는 삭제·재생성·공개 설정을 찾지 못했습니다.
(이미 있던 위험은 이 도구가 다시 경고하지 않습니다 — 바뀐 것만 봅니다.)
```
