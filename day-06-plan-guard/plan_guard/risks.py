"""apply 전에 봐야 할 것 — 규칙 14종.

모든 판정은 **plan 에 적힌 값만** 근거로 한다. 추측하지 않는다.
그래서 근거(`detail`)에는 항상 실제 값이 들어가고, 값이 없으면 그 규칙은 발동하지 않는다.

규칙은 '새로 생기는 위험'만 잡는다:
    이전에도 0.0.0.0/0:443 이 열려 있었다면, 그 규칙이 그대로인 한 다시 경고하지 않는다.
    (바뀐 것만 보여 주는 도구다 — 이미 있는 위험은 `baseline` 비교로 본다.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from .differences import diff_change
from .plan import Change, Plan

CRITICAL = "치명"
HIGH = "심각"
MEDIUM = "보통"
LOW = "참고"

SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}

# 데이터가 사라지면 되돌릴 수 없는 리소스 — 여기 있는 타입만 '데이터'로 센다.
STATEFUL_TYPES = {
    "aws_db_instance",
    "aws_rds_cluster",
    "aws_rds_cluster_instance",
    "aws_dynamodb_table",
    "aws_s3_bucket",
    "aws_ebs_volume",
    "aws_efs_file_system",
    "aws_elasticache_cluster",
    "aws_elasticache_replication_group",
    "aws_redshift_cluster",
    "aws_kms_key",
    "aws_secretsmanager_secret",
    "aws_docdb_cluster",
    "aws_neptune_cluster",
    "google_sql_database_instance",
    "google_storage_bucket",
    "google_bigquery_dataset",
    "google_spanner_instance",
    "azurerm_mssql_database",
    "azurerm_postgresql_flexible_server",
    "azurerm_mysql_flexible_server",
    "azurerm_storage_account",
    "azurerm_storage_container",
    "digitalocean_database_cluster",
    "kubernetes_persistent_volume_claim",
    "kubernetes_persistent_volume",
}

# 사람이 붙는 '관리용' 포트 — 인터넷에 열리면 곧 사고다.
ADMIN_PORTS = {
    22: "SSH",
    23: "telnet",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    27017: "MongoDB",
    9200: "Elasticsearch",
    9300: "Elasticsearch",
    11211: "memcached",
    2375: "Docker API",
    2376: "Docker API(TLS)",
    6443: "Kubernetes API",
    3389: "RDP",
    5984: "CouchDB",
    8080: "관리 콘솔",
}

PUBLIC_ACLS = {"public-read", "public-read-write", "website"}

FIREWALL_TYPES = {
    "aws_security_group",
    "aws_security_group_rule",
    "aws_vpc_security_group_ingress_rule",
    "google_compute_firewall",
    "azurerm_network_security_rule",
    "digitalocean_firewall",
}

OPEN_CIDRS = {"0.0.0.0/0", "::/0"}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    address: str
    title: str
    detail: str
    fix: str
    ref: str = ""

    def line(self) -> str:
        return f"[{self.severity}] {self.title} — {self.address}\n   근거: {self.detail}\n   고치기: {self.fix}"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str
    title: str
    why: str


CATALOG: tuple[Rule, ...] = (
    Rule("stateful-replace", CRITICAL, "데이터가 있는 리소스가 재생성됨", "재생성은 삭제 후 생성이다. 안에 든 데이터는 plan 이 옮겨 주지 않는다."),
    Rule("stateful-destroy", CRITICAL, "데이터가 있는 리소스가 삭제됨", "삭제된 스토리지는 plan 밖에서만 복구할 수 있다."),
    Rule("destroy", HIGH, "리소스가 삭제됨", "지금 쓰고 있는 것이 사라진다 — 다른 곳이 참조하고 있으면 apply 가 실패한다."),
    Rule("replace", HIGH, "리소스가 재생성됨", "이름·주소·IP 가 바뀌고 그 사이 잠깐 없다."),
    Rule("open-admin-port", CRITICAL, "관리 포트가 인터넷에 열림", "0.0.0.0/0 에 SSH·DB 포트를 열면 스캔 봇이 몇 분 안에 찾는다."),
    Rule("open-all-ports", CRITICAL, "모든 포트가 인터넷에 열림", "protocol=-1 + 0.0.0.0/0 은 방화벽을 사실상 없앤다."),
    Rule("public-bucket", CRITICAL, "버킷이 공개로 바뀜", "한 번 공개된 객체는 검색엔진과 스크레이퍼가 이미 가져갔다."),
    Rule("iam-wildcard", CRITICAL, "IAM 정책에 * 가 들어감", "Action/Resource 의 * 는 그 역할이 가진 모든 권한을 연다."),
    Rule("encryption-off", HIGH, "암호화가 꺼짐", "저장 데이터의 암호화를 끄면 디스크를 얻은 사람이 그대로 읽는다."),
    Rule("no-final-snapshot", HIGH, "스냅샷 없이 DB 를 지움", "skip_final_snapshot=true 는 마지막 스냅샷을 남기지 않는다."),
    Rule("deletion-protection-off", HIGH, "삭제 보호가 꺼짐", "삭제 보호를 끄면 다음 실수 한 번에 DB 가 사라진다."),
    Rule("open-non-admin-port", LOW, "인터넷에 포트가 열림", "웹 공개가 의도한 것인지 한 번 보라는 뜻이다."),
    Rule("public-ip", MEDIUM, "인스턴스에 공인 IP 가 붙음", "공인 IP 는 인터넷에서 바로 닿는 주소다."),
    Rule("secret-change", MEDIUM, "민감한 값이 바뀜", "비밀번호·키가 바뀌면 붙어 있는 앱도 같이 바뀌어야 한다. 값은 가린다."),
    Rule("tag-loss", MEDIUM, "태그가 사라짐", "태그는 청구·소유자 추적의 기준이다."),
)

CATALOG_BY_ID = {rule.rule_id: rule for rule in CATALOG}


# ------------------------------------------------------------------ 도우미
def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _is_open_cidr(value: Any) -> bool:
    return isinstance(value, str) and value.strip() in OPEN_CIDRS


def _port_range(item: dict) -> tuple[int, int] | None:
    try:
        start = int(item.get("from_port"))
        end = int(item.get("to_port"))
    except (TypeError, ValueError):
        return None
    if start == 0 and end == 0 and str(item.get("protocol", "")).lower() in ("-1", "all"):
        return (0, 65535)
    if start > end:
        start, end = end, start
    return (start, end)


def _rule_blocks(data: dict) -> list[dict]:
    """방화벽 리소스에서 '규칙 블록'만 꺼낸다 — aws ingress / google allow / azure 단일 규칙."""
    blocks: list[dict] = []
    for key in ("ingress", "ingress_with_cidr_blocks", "inbound_rule"):
        blocks.extend([b for b in _list(data.get(key)) if isinstance(b, dict)])
    return blocks


def _cidrs(item: dict) -> list[str]:
    cidrs: list[str] = []
    for key in ("cidr_blocks", "ipv6_cidr_blocks", "source_address_prefix", "source_address_prefixes",
                "source_ranges", "addresses", "values"):
        value = item.get(key)
        if isinstance(value, str):
            cidrs.append(value)
        elif isinstance(value, list):
            cidrs.extend([v for v in value if isinstance(v, str)])
    return [c for c in cidrs if _is_open_cidr(c)]


def _entries(item: dict) -> list[tuple[str, tuple[int, int] | None]]:
    """한 규칙 항목의 (프로토콜, 포트범위) 목록 — google 의 allow 블록까지."""
    protocol = str(item.get("protocol") or item.get("ip_protocol") or "").lower()
    entries: list[tuple[str, tuple[int, int] | None]] = []
    rng = _port_range(item)
    if rng is not None:
        entries.append((protocol, rng))
    else:
        for key in ("ports", "port_range", "destination_port_range"):
            value = item.get(key)
            if isinstance(value, str):
                entries.append((protocol, _parse_port_string(value)))
            elif isinstance(value, list):
                entries.extend((protocol, _parse_port_string(str(v))) for v in value)
    for block in _list(item.get("allow")):
        if not isinstance(block, dict):
            continue
        sub = str(block.get("protocol") or protocol)
        ports = block.get("ports") or []
        if not ports:
            entries.append((sub, (0, 65535)))
        for port in ports:
            entries.append((sub, _parse_port_string(str(port))))
    return [(p, r) for p, r in entries if r is not None]


def open_rules(change: Change, side: str = "after") -> set[tuple]:
    """방화벽 변경에서 '인터넷에 열린 규칙' 집합 — 이전/이후 비교용."""
    data = (change.after if side == "after" else change.before) or {}
    found: set[tuple] = set()

    if change.type in ("aws_security_group_rule", "aws_vpc_security_group_ingress_rule",
                       "azurerm_network_security_rule", "google_compute_firewall"):
        blocks = [data]
    else:
        blocks = _rule_blocks(data)

    for item in blocks:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").lower()
        if kind and kind != "ingress":
            continue
        if "access" in item and str(item.get("access")).lower() != "allow":
            continue
        direction = str(item.get("direction") or "").lower()
        if direction and direction not in ("ingress", "inbound"):
            continue
        cidrs = _cidrs(item)
        if not cidrs:
            continue
        for protocol, rng in _entries(item):
            found.add((protocol, rng, tuple(sorted(cidrs))))
    return found


def _parse_port_string(value: str) -> tuple[int, int] | None:
    value = value.strip()
    if value in ("*", "all", "any"):
        return (0, 65535)
    if "-" in value:
        left, _, right = value.partition("-")
        try:
            return (int(left), int(right))
        except ValueError:
            return None
    try:
        port = int(value)
    except ValueError:
        return None
    return (port, port)


def _admin_hits(rng: tuple[int, int] | None) -> list[str]:
    if rng is None:
        return []
    start, end = rng
    hits = [f"{port}({name})" for port, name in sorted(ADMIN_PORTS.items()) if start <= port <= end]
    if start == 0 and end >= 65535:
        return ["모든 포트"]
    return hits


def _policy_docs(change: Change, side: str) -> list[Any]:
    data = (change.after if side == "after" else change.before) or {}
    docs: list[Any] = []
    for key in ("policy", "document", "policy_document", "assume_role_policy", "json"):
        value = data.get(key)
        if isinstance(value, str):
            try:
                docs.append(json.loads(value))
            except json.JSONDecodeError:
                continue
        elif isinstance(value, dict):
            docs.append(value)
    statements = data.get("statement")
    if isinstance(statements, list):
        docs.append({"Statement": statements})
    return docs


def _wildcards(doc: Any) -> list[str]:
    """정책 문서에서 * 를 찾는다 — {'Statement': [...]} 또는 [...] 모양 모두."""
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = key.lower()
                if lowered in ("action", "resource", "notaction", "notresource"):
                    values = value if isinstance(value, list) else [value]
                    for item in values:
                        if isinstance(item, str) and item.strip() == "*":
                            hits.append(f"{path}{key}={item}")
                else:
                    walk(value, f"{path}{key}.")
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(doc, "")
    return hits


def _tags(change: Change, side: str) -> dict:
    data = (change.after if side == "after" else change.before) or {}
    tags = data.get("tags")
    return tags if isinstance(tags, dict) else {}


# ------------------------------------------------------------------ 규칙
def _rule_destroy_like(plan: Plan, change: Change) -> list[Finding]:
    out: list[Finding] = []
    if not change.deletes:
        return out
    stateful = change.type in STATEFUL_TYPES
    if change.kind == "replace":
        rule = "stateful-replace" if stateful else "replace"
        why = "데이터 리소스" if stateful else "다운타임"
        detail = f"{change.type} · 재생성"
        if change.replace_paths:
            detail += " · 바꾼 속성 " + ", ".join(".".join(p) for p in change.replace_paths[:3])
        if change.reason_label:
            detail += f" · 사유 {change.reason_label}"
        out.append(
            Finding(
                rule=rule,
                severity=CRITICAL if stateful else HIGH,
                address=change.address,
                title=CATALOG_BY_ID[rule].title,
                detail=f"{detail} ({why})",
                fix=_replace_fix(change, stateful),
                ref=change.ref,
            )
        )
    elif change.kind == "delete":
        rule = "stateful-destroy" if stateful else "destroy"
        detail = f"{change.type} 삭제"
        if change.reason_label:
            detail += f" · 사유 {change.reason_label}"
        out.append(
            Finding(
                rule=rule,
                severity=CRITICAL if stateful else HIGH,
                address=change.address,
                title=CATALOG_BY_ID[rule].title,
                detail=detail,
                fix="지워도 되는지 확인하세요. 남겨야 하면 설정에 다시 넣고(또는 `terraform state rm` 은 마지막 수단) plan 을 다시 만드세요.",
                ref=change.ref,
            )
        )
    return out


def _replace_fix(change: Change, stateful: bool) -> str:
    if stateful:
        return (
            "새 리소스를 만들어 옮기고(스냅샷 복원·버킷 복사), 이번 plan 에서는 바꾸지 마세요. "
            "제자리 변경이 되는 속성인지 provider 문서를 확인하세요."
        )
    return "이번 배포에서 빼거나 create_before_destroy 로 무중단 순서를 잡으세요."


def _rule_open_ports(plan: Plan, change: Change) -> list[Finding]:
    if change.type not in FIREWALL_TYPES or not change.writes:
        return []
    new = open_rules(change, "after")
    old = open_rules(change, "before")
    added = sorted(new - old)
    findings: list[Finding] = []
    for protocol, rng, cidrs in added:
        hits = _admin_hits(rng)
        ports = "모든 포트" if rng == (0, 65535) else (
            f"{rng[0]}" if rng and rng[0] == rng[1] else (f"{rng[0]}-{rng[1]}" if rng else "포트 미지정")
        )
        if "모든 포트" in hits:
            findings.append(
                Finding(
                    rule="open-all-ports",
                    severity=CRITICAL,
                    address=change.address,
                    title=CATALOG_BY_ID["open-all-ports"].title,
                    detail=f"{protocol or 'all'} · {ports} · 출처 {', '.join(cidrs)}",
                    fix="프로토콜과 포트를 좁히고, 출처를 사내 대역(예: 10.0.0.0/8)이나 보안 그룹 참조로 바꾸세요.",
                    ref=change.ref,
                )
            )
            continue
        if hits:
            findings.append(
                Finding(
                    rule="open-admin-port",
                    severity=CRITICAL,
                    address=change.address,
                    title=CATALOG_BY_ID["open-admin-port"].title,
                    detail=f"{protocol or 'tcp'} · {ports} · 열린 관리 포트 {', '.join(hits)} · 출처 {', '.join(cidrs)}",
                    fix="VPN·배스천 대역이나 보안 그룹 참조로 출처를 좁히세요. 정말 필요하면 앱 포트(80/443)만 공개하세요.",
                    ref=change.ref,
                )
            )
        elif rng and rng[0] >= 1:
            findings.append(
                Finding(
                    rule="open-non-admin-port",
                    severity=LOW,
                    address=change.address,
                    title="인터넷에 포트가 열림",
                    detail=f"{protocol or 'tcp'} · {ports} · 출처 {', '.join(cidrs)}",
                    fix="웹 공개가 의도한 것이면 그대로 두세요. 아니면 출처를 좁히세요.",
                    ref=change.ref,
                )
            )
    return findings


def _rule_public_bucket(plan: Plan, change: Change) -> list[Finding]:
    if not change.writes:
        return []
    before = change.get_before("acl")
    after = change.get_after("acl")
    out: list[Finding] = []
    if isinstance(after, str) and after in PUBLIC_ACLS and after != before:
        out.append(
            Finding(
                rule="public-bucket",
                severity=CRITICAL,
                address=change.address,
                title=CATALOG_BY_ID["public-bucket"].title,
                detail=f"acl: {before or '(없음)'} → {after}",
                fix="acl 은 private 로 두고, 정말 공개할 객체만 별도 경로·버킷으로 나누세요.",
                ref=change.ref,
            )
        )
    # bucket policy 에 Principal "*" + Allow
    for side in ("after",):
        for doc in _policy_docs(change, side):
            if not isinstance(doc, dict):
                continue
            for statement in _list(doc.get("Statement")):
                if not isinstance(statement, dict):
                    continue
                effect = str(statement.get("Effect", "")).lower()
                principal = statement.get("Principal")
                if effect == "allow" and (principal == "*" or (isinstance(principal, dict) and "*" in principal.values())):
                    out.append(
                        Finding(
                            rule="public-bucket",
                            severity=CRITICAL,
                            address=change.address,
                            title="버킷 정책이 모두에게 허용",
                            detail='Statement 에 Effect=Allow, Principal="*" 가 들어감',
                            fix='Principal 을 특정 계정/역할로 바꾸고, 공개 배포는 CloudFront 같은 경로로 분리하세요.',
                            ref=change.ref,
                        )
                    )
    return out


def _rule_iam_wildcard(plan: Plan, change: Change) -> list[Finding]:
    if not change.writes:
        return []
    after_hits: list[str] = []
    before_hits: set[str] = set()
    for doc in _policy_docs(change, "after"):
        after_hits.extend(_wildcards(doc))
    for doc in _policy_docs(change, "before"):
        before_hits.update(_wildcards(doc))
    new_hits = [h for h in after_hits if h not in before_hits]
    if not new_hits:
        return []
    return [
        Finding(
            rule="iam-wildcard",
            severity=CRITICAL,
            address=change.address,
            title=CATALOG_BY_ID["iam-wildcard"].title,
            detail="새로 생긴 와일드카드: " + ", ".join(sorted(set(new_hits))[:4]),
            fix='Action 은 필요한 API 목록으로, Resource 는 arn:aws:s3:::acme-prod-assets/* 처럼 대상으로 좁히세요.',
            ref=change.ref,
        )
    ]


def _rule_encryption(plan: Plan, change: Change) -> list[Finding]:
    out: list[Finding] = []
    for key in ("storage_encrypted", "encrypted", "encryption_at_rest", "at_rest_encryption_enabled"):
        before = change.get_before(key)
        after = change.get_after(key)
        if after is False and before is True:
            out.append(
                Finding(
                    rule="encryption-off",
                    severity=HIGH,
                    address=change.address,
                    title=CATALOG_BY_ID["encryption-off"].title,
                    detail=f"{key}: true → false",
                    fix=f"{key} = true 를 유지하세요. 암호화를 켜려면 새 리소스로 옮겨야 할 수 있습니다.",
                    ref=change.ref,
                )
            )
        elif after is False and before is None and change.kind == "create" and change.type in STATEFUL_TYPES:
            out.append(
                Finding(
                    rule="encryption-off",
                    severity=MEDIUM,
                    address=change.address,
                    title="새 리소스에 암호화가 꺼져 있음",
                    detail=f"{key} = false",
                    fix=f"{key} = true 로 만드세요. 만든 뒤에는 제자리에서 못 바꾸는 타입이 많습니다.",
                    ref=change.ref,
                )
            )
    return out


def _rule_db_safety(plan: Plan, change: Change) -> list[Finding]:
    if change.type not in STATEFUL_TYPES or not change.deletes:
        return []
    out: list[Finding] = []
    skip = change.get_before("skip_final_snapshot")
    if skip is None:
        skip = change.get_after("skip_final_snapshot")
    if skip is True:
        out.append(
            Finding(
                rule="no-final-snapshot",
                severity=HIGH,
                address=change.address,
                title=CATALOG_BY_ID["no-final-snapshot"].title,
                detail="skip_final_snapshot = true",
                fix="apply 전에 손으로 스냅샷을 뜨거나 skip_final_snapshot = false 로 두고 final_snapshot_identifier 를 지정하세요.",
                ref=change.ref,
            )
        )
    return out


def _rule_deletion_protection(plan: Plan, change: Change) -> list[Finding]:
    protection_before = change.get_before("deletion_protection")
    protection_after = change.get_after("deletion_protection")
    if protection_before is True and (protection_after is False or change.kind == "delete"):
        return [
            Finding(
                rule="deletion-protection-off",
                severity=HIGH,
                address=change.address,
                title=CATALOG_BY_ID["deletion-protection-off"].title,
                detail="deletion_protection: true → false" if protection_after is False else "삭제 보호가 켜진 리소스를 삭제",
                fix="삭제 보호는 그대로 두고, 정말 지울 때만 따로 빼세요.",
                ref=change.ref,
            )
        ]
    return []


def _rule_public_ip(plan: Plan, change: Change) -> list[Finding]:
    if change.get_after("associate_public_ip_address") is True and \
            change.get_before("associate_public_ip_address") is not True:
        return [
            Finding(
                rule="public-ip",
                severity=MEDIUM,
                address=change.address,
                title=CATALOG_BY_ID["public-ip"].title,
                detail="associate_public_ip_address = true",
                fix="사설 서브넷 + NAT/LB 로 두는 편이 안전합니다.",
                ref=change.ref,
            )
        ]
    return []


def _rule_secret(plan: Plan, change: Change) -> list[Finding]:
    diffs = diff_change(change, include_unknown=False)
    secret_paths = [d.path for d in diffs if d.sensitive]
    if not secret_paths:
        return []
    return [
        Finding(
            rule="secret-change",
            severity=MEDIUM,
            address=change.address,
            title=CATALOG_BY_ID["secret-change"].title,
            detail="민감 속성 " + ", ".join(secret_paths[:5]) + " (값은 가림)",
            fix="값을 바꾸면 그 값을 쓰는 앱·시크릿 저장소도 같이 갱신하고, 지금 값을 따로 백업하세요.",
            ref=change.ref,
        )
    ]


def _rule_tags(plan: Plan, change: Change) -> list[Finding]:
    if change.kind == "delete":
        return []          # 리소스가 통째로 사라지면 태그도 같이 사라지는 게 당연하다
    before = _tags(change, "before")
    after = _tags(change, "after")
    lost = sorted(set(before) - set(after))
    if not lost:
        return []
    return [
        Finding(
            rule="tag-loss",
            severity=MEDIUM,
            address=change.address,
            title=CATALOG_BY_ID["tag-loss"].title,
            detail="사라지는 태그 " + ", ".join(lost[:5]),
            fix="지우려는 태그가 맞는지 확인하세요. 청구·비용 배분에 쓰는 태그는 남기세요.",
            ref=change.ref,
        )
    ]


RULES: tuple[Callable[[Plan, Change], list[Finding]], ...] = (
    _rule_destroy_like,
    _rule_open_ports,
    _rule_public_bucket,
    _rule_iam_wildcard,
    _rule_encryption,
    _rule_db_safety,
    _rule_deletion_protection,
    _rule_public_ip,
    _rule_secret,
    _rule_tags,
)


# ------------------------------------------------------------------ 공개 API
def findings(plan: Plan) -> list[Finding]:
    """plan 전체를 훑어 위험 목록을 만든다 — 항상 같은 순서."""
    out: list[Finding] = []
    for change in plan.changes:
        if change.kind in ("noop", "read"):
            continue
        for rule in RULES:
            out.extend(rule(plan, change))
    out.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.rule, f.address))
    return out


def counts(items: list[Finding]) -> dict[str, int]:
    result = {CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0}
    for item in items:
        result[item.severity] = result.get(item.severity, 0) + 1
    return result


def verdict(items: list[Finding]) -> str:
    c = counts(items)
    if c[CRITICAL]:
        return "보류"
    if c[HIGH]:
        return "주의"
    return "통과"


def verdict_line(items: list[Finding]) -> str:
    c = counts(items)
    rule_ids = sorted({i.rule for i in items})
    return (
        f"판정 **{verdict(items)}** · 치명 {c[CRITICAL]} · 심각 {c[HIGH]} · "
        f"보통 {c[MEDIUM]} · 참고 {c[LOW]} · 규칙 {len(rule_ids)}종"
    )


def by_address(items: list[Finding]) -> dict[str, list[Finding]]:
    out: dict[str, list[Finding]] = {}
    for item in items:
        out.setdefault(item.address, []).append(item)
    return out
