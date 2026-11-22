"""되돌리기 — apply 를 누르기 전에 '되돌릴 수 있는가'를 적어 둔다.

여기서 만드는 것은 **제안**이다. 실제 실행은 사람이 한다.
명령에 들어가는 식별자는 plan 의 이전 값에서만 가져오고, 민감값은 가린다.
"""

from __future__ import annotations

from .differences import key_values
from .plan import MASK, Change, Plan, is_sensitive_at, short

SNAPSHOT_HINTS = {
    "aws_db_instance": "aws rds create-db-snapshot --db-instance-identifier {id} --db-snapshot-identifier {id}-pre-{{날짜}}",
    "aws_rds_cluster": "aws rds create-db-cluster-snapshot --db-cluster-identifier {id} --db-cluster-snapshot-identifier {id}-pre-{{날짜}}",
    "aws_dynamodb_table": "aws dynamodb create-backup --table-name {id} --backup-name {id}-pre-{{날짜}}",
    "aws_ebs_volume": "aws ec2 create-snapshot --volume-id {id} --description pre-deploy",
    "aws_instance": "aws ec2 create-image --instance-id {id} --name pre-deploy-{날짜} --no-reboot",
    "aws_efs_file_system": "aws efs create-backup? 대신 aws-backup 으로 온디맨드 백업을 잡으세요",
    "aws_elasticache_cluster": "aws elasticache create-snapshot --cache-cluster-id {id} --snapshot-name {id}-pre-{{날짜}}",
    "google_sql_database_instance": "gcloud sql backups create --instance {id}",
    "google_storage_bucket": "gsutil -m rsync -r gs://{id} gs://{id}-pre-{{날짜}}",
    "azurerm_mssql_database": "az sql db copy ... (백업/복사로 먼저 보관)",
    "azurerm_storage_account": "az storage copy ... (스토리지 복사로 먼저 보관)",
}


def _identifier(change: Change) -> str:
    for key in ("identifier", "bucket", "name", "id", "table_name"):
        value = change.get_before(key)
        if isinstance(value, str) and value and not value.startswith("arn:"):
            return value
    return change.address


def _before_lines(change: Change) -> list[str]:
    picked = key_values(change, "before", limit=5)
    if not picked:
        return []
    return [f"    이전 값: {', '.join(f'{k}={short(v, 28)}' for k, v in picked)}"]


def _revert_lines(change: Change) -> list[str]:
    """이전 상태로 되돌리는 설정 한 줄 — 바뀐 속성 중 안전하게 되돌릴 수 있는 것만."""
    lines: list[str] = []
    for key in ("storage_encrypted", "acl", "instance_class", "engine_version", "deletion_protection",
                "skip_final_snapshot", "backup_retention_period", "multi_az", "enabled"):
        before = change.get_before(key)
        after = change.get_after(key)
        if before is None or before == after or after is None:
            continue
        sensitive = is_sensitive_at(change.before_sensitive, (key,))
        lines.append(f"    {key} = {'«민감»' if sensitive else short(before, 30)}  (지금 값 {short(after, 30)})")
    return lines[:4]


def steps(plan: Plan) -> list[str]:
    destructive = [c for c in plan.changes if c.destructive and c.kind != "noop"]
    lines: list[str] = []

    lines.append("### 1. apply 전에 (지금 상태를 붙잡아 둔다)")
    lines.append("    terraform state pull > before-deploy.tfstate      # state 백업(손으로 보관)")
    lines.append("    cp {plan 파일} before-plan.json                    # 이 plan 도 보관")
    if not destructive:
        lines.append("    → 지우거나 다시 만드는 리소스가 없습니다. 이대로 apply 해도 되돌릴 것이 없습니다.")
        return lines

    lines.append("")
    lines.append(f"### 2. 사라지는 것 {len(destructive)}개 — 미리 백업")
    for change in destructive:
        lines.append(f"  - {change.address} [{change.kind_label}]")
        lines.extend(_before_lines(change))
        ident = _identifier(change)
        hint = SNAPSHOT_HINTS.get(change.type)
        if hint:
            lines.append("    제안: " + hint.replace("{{날짜}}", "{날짜}").replace("{id}", ident))
        elif change.type in ("aws_s3_bucket", "google_storage_bucket"):
            lines.append(f"    제안: 버킷 안 객체를 다른 버킷/로컬로 먼저 복사하세요 (s3://{ident})")
        else:
            lines.append("    제안: 이 리소스가 가진 데이터를 provider CLI 로 먼저 내려받으세요.")

    lines.append("")
    lines.append("### 3. 문제가 생겼을 때 되돌리기")
    lines.append("    a) apply 가 실패했으면: terraform apply 는 실패한 리소스까지만 바꿨습니다. plan 을 다시 만들어 확인하세요.")
    lines.append("    b) apply 가 끝났으면: 아래 값을 설정에서 이전으로 돌리고 plan 을 다시 만드세요.")
    for change in destructive:
        reverts = _revert_lines(change)
        if reverts:
            lines.append(f"  - {change.address}")
            lines.extend(reverts)
    if not any(_revert_lines(c) for c in destructive):
        lines.append("  - (설정에서 되돌릴 속성이 없습니다. 이전 state 로 복원하는 방법밖에 없습니다.)")
    lines.append("    c) 데이터 리소스는 '되돌리기'가 아니라 '복원'입니다 — 2번에서 뜬 스냅샷으로 새 리소스를 만드세요.")
    lines.append("")
    lines.append("주의: 위 명령의 식별자·날짜는 plan 값에서 만든 제안입니다. 실행 전에 계정·리전을 확인하세요.")
    return lines


def summary_line(plan: Plan) -> str:
    destructive = [c for c in plan.changes if c.destructive]
    if not destructive:
        return "되돌릴 것 없음 (삭제·재생성 0건)"
    stateful = [c for c in destructive if c.type in {"aws_db_instance", "aws_rds_cluster", "aws_dynamodb_table",
                                                    "aws_s3_bucket", "aws_ebs_volume", "google_sql_database_instance"}]
    return f"사라지는 리소스 {len(destructive)}개 (데이터 {len(stateful)}개) — apply 전에 백업 필요"
