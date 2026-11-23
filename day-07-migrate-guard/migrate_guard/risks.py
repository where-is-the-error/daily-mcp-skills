"""규칙 — 마이그레이션에서 실제로 사고가 나는 자리들.

각 규칙은 (1) 무엇이 문제인지, (2) 왜 그런지, (3) 어떻게 고치는지를 갖는다.
근거에는 항상 숫자를 붙인다 — "위험함" 이 아니라 "1,400,000행 재작성 · 23초".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import dialect
from .dialect import SEVERITY_ORDER, CostKind, Severity
from .fmt import duration, rows as fmt_rows
from .operations import Migration, Operation

__all__ = ["Rule", "Finding", "CATALOG", "findings", "verdict", "summary_counts", "by_severity", "SEVERITY_ORDER"]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: Severity
    title: str
    why: str
    fix: str


@dataclass
class Finding:
    rule: Rule
    ref: str
    line: int
    table: str | None
    summary: str
    evidence: list[str] = field(default_factory=list)

    @property
    def severity(self) -> Severity:
        return self.rule.severity

    @property
    def rule_id(self) -> str:
        return self.rule.rule_id

    @property
    def fix(self) -> str:
        return self.rule.fix


def _rule(rule_id: str, severity: Severity, title: str, why: str, fix: str) -> Rule:
    return Rule(rule_id, severity, title, why, fix)


CATALOG: list[Rule] = [
    _rule("drop-table", Severity.치명, "테이블을 통째로 지운다",
          "DROP TABLE 은 데이터와 스키마를 함께 없앤다. 되돌릴 값이 남지 않는다.",
          "두 배포로 나눈다: 먼저 이름을 바꿔 남겨 두고(_deprecated_이름), 한 주 뒤에 지운다."),
    _rule("drop-column", Severity.치명, "컬럼 값을 지운다",
          "DROP COLUMN 은 즉시 끝나지만 값은 사라진다. 그 컬럼을 읽던 코드는 그 순간 실패한다.",
          "먼저 코드에서 참조를 지우고(확장 단계), 값을 백업한 뒤 다음 배포에서 지운다."),
    _rule("drop-column-cleanup", Severity.보통, "예고된 정리 단계의 컬럼 삭제",
          "이름을 바꿔 남겨 둔 컬럼을 이제 지운다. 값은 이 시점에 사라지므로 백업이 필요하다.",
          "백업본을 확인하고, 참조가 0건인 것을 확인한 뒤 실행한다."),
    _rule("truncate", Severity.치명, "테이블을 비운다",
          "TRUNCATE 는 조건을 받지 않는다. 모든 행이 한 문장에 사라진다.",
          "TRUNCATE 대신 조건이 있는 DELETE 를 배치로 돌리고, 백업을 먼저 뜬다."),
    _rule("delete-without-where", Severity.치명, "조건 없는 DELETE",
          "WHERE 가 없는 DELETE 는 모든 행을 지운다. 실수로 실행되면 되돌릴 수 없다.",
          "WHERE 를 넣고, 지울 키를 먼저 SELECT 로 확인한다."),
    _rule("update-without-where", Severity.치명, "조건 없는 UPDATE",
          "WHERE 가 없는 UPDATE 는 모든 행을 다시 쓴다. WAL·블로트·복제 지연이 함께 온다.",
          "배치로 나누고(예: 5,000행씩), WHERE 로 범위를 좁힌다."),
    _rule("add-column-not-null-no-default", Severity.심각, "기본값 없는 NOT NULL 컬럼 추가",
          "테이블에 행이 있으면 기존 행의 값을 정할 수 없어 문장이 실패한다.",
          "NULL 허용으로 추가하고, 백필한 뒤 SET NOT NULL 로 닫는다."),
    _rule("volatile-default-rewrite", Severity.심각, "휘발성 기본값이 테이블을 다시 쓴다",
          "random()·gen_random_uuid()·nextval() 처럼 행마다 값이 달라지는 기본값은 "
          "모든 행에 값을 채워 넣어야 해서 테이블 전체를 다시 쓴다.",
          "컬럼을 기본값 없이 추가하고, 백필한 뒤 DEFAULT 를 붙인다."),
    _rule("rewrite-type", Severity.심각, "타입 변경이 테이블을 다시 쓴다",
          "재작성은 새 파일에 모든 행을 복사한다. 그동안 ACCESS EXCLUSIVE 락이 유지되어 "
          "읽기까지 막힌다.",
          "새 컬럼을 추가해 백필하고, 코드가 둘 다 읽게 만든 뒤 마지막에 바꾼다."),
    _rule("type-narrowing", Severity.치명, "값이 깨질 수 있는 타입 변경",
          "bigint → integer, varchar(255) → varchar(64) 같은 축소는 범위를 넘는 값에서 실패하거나 잘린다.",
          "먼저 대상 값이 범위 안에 있는지 세어 보고, 통과할 때만 바꾼다."),
    _rule("lock-blocks-reads", Severity.심각, "읽기까지 막는 잠금이 오래 유지된다",
          "ACCESS EXCLUSIVE 락은 그 테이블의 SELECT 까지 줄 세운다. 서비스가 멈춘 것처럼 보인다.",
          "lock_timeout 을 짧게 걸고, 재작성이 필요한 변경은 확장·백필·전환으로 나눈다."),
    _rule("set-not-null-scan", Severity.심각, "SET NOT NULL 이 전체를 훑는다",
          "기존 행에 NULL 이 없는지 확인해야 해서 테이블을 한 번 읽는다. 그동안 락을 쥔다.",
          "CHECK (col IS NOT NULL) NOT VALID 를 먼저 달고 VALIDATE 한 뒤 SET NOT NULL 한다."),
    _rule("create-index-blocks-writes", Severity.심각, "인덱스 생성이 쓰기를 막는다",
          "CREATE INDEX 는 SHARE 락을 잡아 빌드가 끝날 때까지 INSERT·UPDATE·DELETE 를 막는다.",
          "CREATE INDEX CONCURRENTLY 를 쓴다(트랜잭션 밖에서)."),
    _rule("concurrent-in-transaction", Severity.심각, "트랜잭션 안의 CONCURRENTLY",
          "CREATE INDEX CONCURRENTLY 는 트랜잭션 블록 안에서 실행할 수 없다. 그대로 두면 문장이 실패한다.",
          "BEGIN/COMMIT 밖으로 빼거나, 마이그레이션 도구의 트랜잭션 래핑을 끈다."),
    _rule("fk-without-not-valid", Severity.심각, "외래키가 두 테이블을 잠그고 훑는다",
          "NOT VALID 없이 추가하면 기존 행을 모두 검증한다. 참조하는 쪽과 참조되는 쪽 모두 잠긴다.",
          "ADD CONSTRAINT ... NOT VALID 로 먼저 달고, VALIDATE CONSTRAINT 로 나중에 검증한다."),
    _rule("add-unique-locks", Severity.심각, "제약 추가가 인덱스를 만든다",
          "PRIMARY KEY·UNIQUE 제약은 인덱스를 새로 빌드한다. 빌드 동안 쓰기가 막힌다.",
          "CREATE UNIQUE INDEX CONCURRENTLY 로 인덱스를 먼저 만들고, 그 인덱스를 제약으로 붙인다."),
    _rule("check-without-not-valid", Severity.보통, "CHECK 제약이 기존 행을 훑는다",
          "기존 행을 모두 검증한다. 테이블이 크면 오래 걸린다.",
          "NOT VALID 로 달고 VALIDATE CONSTRAINT 로 나눈다."),
    _rule("rename-column-breaks-clients", Severity.보통, "컬럼 이름 변경은 배포 중 코드를 깬다",
          "구버전 코드가 이전 이름으로 읽고 있으면 이름을 바꾼 순간 실패한다.",
          "새 컬럼을 추가해 둘 다 쓰게 만들고, 코드 배포가 끝난 뒤 옛 컬럼을 지운다."),
    _rule("rename-table-breaks-clients", Severity.보통, "테이블 이름 변경은 배포 중 코드를 깬다",
          "구버전 코드·뷰·외부 리포트가 이전 이름을 본다.",
          "뷰를 하나 만들어 이전 이름을 유지하고, 소비자가 옮긴 뒤에 정리한다."),
    _rule("drop-index", Severity.보통, "인덱스를 지우면 쿼리가 느려진다",
          "지운 인덱스를 쓰던 쿼리는 전체 스캔으로 떨어진다.",
          "지우기 전에 pg_stat_user_indexes.idx_scan 으로 사용량을 확인한다."),
    _rule("locks-held-to-commit", Severity.심각, "트랜잭션 하나라 락이 끝까지 유지된다",
          "BEGIN ... COMMIT 안에서는 앞 문장이 잡은 락이 커밋까지 풀리지 않는다. "
          "뒤 문장이 오래 걸리면 앞의 짧은 DDL 도 그만큼 오래 잠근다.",
          "문장을 트랜잭션 밖으로 나누고, 오래 걸리는 작업은 별도 실행으로 뺀다."),
    _rule("dml-in-migration", Severity.참고, "마이그레이션에 데이터 변경이 섞여 있다",
          "스키마 변경과 데이터 변경을 한 트랜잭션에 두면 락 유지 시간이 두 배가 되고, "
          "실패했을 때 되돌리는 범위도 커진다.",
          "데이터 변경은 배치 작업으로 분리한다."),
    _rule("no-lock-timeout", Severity.참고, "락 대기 상한이 없다",
          "앞선 트랜잭션이 락을 쥐고 있으면 이 문장은 무한정 기다린다. 그 뒤 요청이 모두 쌓인다.",
          "파일 맨 앞에 SET lock_timeout = '3s'; 를 둔다(실패하면 재시도)."),
    _rule("drop-constraint", Severity.참고, "제약을 지운다",
          "무결성 검사가 사라진다. 데이터가 조용히 어긋나기 시작한다.",
          "지우기 전에 그 제약이 막고 있던 위반이 없는지 확인한다."),
]


_BY_ID = {rule.rule_id: rule for rule in CATALOG}


def rule(rule_id: str) -> Rule:
    return _BY_ID[rule_id]


def _is_cleanup(column: str) -> bool:
    """예고된 정리 단계에서 지우는 이름 — 두 배포에 나눠 지운 흔적."""
    lowered = column.lower()
    return lowered.startswith("_deprecated") or lowered.endswith(("_old", "_backup"))


def _finding(rule_id: str, op: Operation, summary: str, evidence: list[str]) -> Finding:
    return Finding(
        rule=rule(rule_id),
        ref=op.ref,
        line=op.line,
        table=op.table,
        summary=summary,
        evidence=evidence,
    )


def _rows_note(migration: Migration, op: Operation) -> tuple[int, str]:
    count, known = migration.table_rows(op.table)
    source = "실제 행 수" if known else "가정"
    return count, f"{fmt_rows(count)}행 ({source})"


def _cost_note(migration: Migration, op: Operation, rates=None) -> str:
    seconds = op.estimate(rates)
    if op.cost.kind is CostKind.NONE:
        return "메타데이터만 · " + duration(seconds)
    return f"{op.cost.note or op.cost.kind.name} {fmt_rows(op.cost.rows)}행 · 약 {duration(seconds)} (모델)"


# --------------------------------------------------------------------- 문장별
def _op_findings(migration: Migration, op: Operation, rates=None) -> list[Finding]:
    out: list[Finding] = []
    rows, rows_text = _rows_note(migration, op)
    cost_text = _cost_note(migration, op, rates)

    if op.kind == "drop_table":
        rule_id = "drop-column-cleanup" if _is_cleanup(op.table or "") else "drop-table"
        out.append(_finding(rule_id, op, f"{op.table} 테이블 삭제", [rows_text, "되돌리기: 값 복구 불가"]))
    elif op.kind == "drop_column":
        column = migration.schema.table(op.table or "")
        current = column.column(op.column) if column and op.column else None
        evidence = [f"{op.table}.{op.column}"]
        if current:
            evidence.append(f"타입 {current.type} · NULL {'허용' if current.nullable else '불가'}")
        evidence.append("되돌리기: 스키마만 복원 가능, 값은 없음")
        if _is_cleanup(op.column or ""):
            out.append(_finding("drop-column-cleanup", op, f"{op.table}.{op.column} 정리 삭제", evidence))
        else:
            out.append(_finding("drop-column", op, f"{op.table}.{op.column} 컬럼 삭제", evidence))
    elif op.kind == "truncate":
        out.append(_finding("truncate", op, f"{op.table} 전체 비우기", [rows_text, "되돌리기: 불가"]))
    elif op.kind == "delete" and not op.detail.get("where"):
        out.append(_finding("delete-without-where", op,
                            f"{op.table} 전체 삭제",
                            [rows_text, cost_text, "되돌리기: 불가"]))
    elif op.kind == "update" and not op.detail.get("where"):
        out.append(_finding("update-without-where", op,
                            f"{op.table} 전체 갱신",
                            [rows_text, cost_text, "되돌리기: 이전 값 없음"]))
    elif op.kind == "add_column":
        column = op.column or "?"
        if op.detail.get("volatile_default"):
            out.append(_finding("volatile-default-rewrite", op,
                                f"{op.table}.{column} 기본값이 매 행을 다시 쓴다",
                                [f"DEFAULT {op.detail.get('default')}", rows_text, cost_text]))
        if not op.detail.get("nullable", True) and op.detail.get("default") is None and rows > 0:
            out.append(_finding("add-column-not-null-no-default", op,
                                f"{op.table}.{column} NOT NULL 인데 기본값이 없다",
                                [rows_text, "기존 행의 값을 정할 수 없어 실패"]))
    elif op.kind == "alter_type":
        change = op.detail.get("change")
        evidence = [
            f"{op.detail.get('from') or '?'} → {op.detail.get('to')}",
            op.detail.get("why") or "",
            rows_text,
            cost_text,
        ]
        if change == "RISKY":
            out.append(_finding("type-narrowing", op, f"{op.table}.{op.column} 타입 축소", evidence))
        elif change == "REWRITE":
            out.append(_finding("rewrite-type", op, f"{op.table}.{op.column} 타입 변경이 재작성", evidence))
    elif op.kind == "set_not_null":
        if not op.detail.get("check"):
            out.append(_finding("set-not-null-scan", op,
                                f"{op.table}.{op.column} NOT NULL 검증",
                                ["기존 CHECK 제약 없음", rows_text, cost_text]))
    elif op.kind == "create_index":
        if op.detail.get("concurrently"):
            if op.in_transaction:
                out.append(_finding("concurrent-in-transaction", op,
                                    "트랜잭션 안의 CREATE INDEX CONCURRENTLY",
                                    ["이 위치에서는 실행할 수 없다"]))
        else:
            out.append(_finding("create-index-blocks-writes", op,
                                f"{op.table} 인덱스 빌드",
                                [f"({op.column or ''})".replace("()", "(식)"), rows_text, cost_text]))
    elif op.kind == "add_foreign_key":
        if not op.detail.get("not_valid"):
            out.append(_finding("fk-without-not-valid", op,
                                f"{op.table} 외래키 검증",
                                [op.detail.get("definition", ""), rows_text, cost_text]))
    elif op.kind in {"add_unique", "add_primary_key"}:
        out.append(_finding("add-unique-locks", op,
                            f"{op.table} {op.detail.get('constraint_kind')} 제약",
                            [op.detail.get("definition", ""), rows_text, cost_text]))
    elif op.kind == "add_check":
        if not op.detail.get("not_valid"):
            out.append(_finding("check-without-not-valid", op,
                                f"{op.table} CHECK 검증", [rows_text, cost_text]))
    elif op.kind == "rename_column":
        out.append(_finding("rename-column-breaks-clients", op,
                            f"{op.table}.{op.column} → {op.detail.get('to')}",
                            ["같은 시각에 배포 중인 코드가 이전 이름을 본다"]))
    elif op.kind == "rename_table":
        out.append(_finding("rename-table-breaks-clients", op,
                            f"{op.table} → {op.detail.get('to')}",
                            ["뷰·리포트·구버전 코드가 이전 이름을 본다"]))
    elif op.kind == "drop_index":
        out.append(_finding("drop-index", op, "인덱스 삭제", ["사용량 확인 없이 지우면 쿼리가 느려진다"]))
    elif op.kind == "drop_constraint":
        if not (op.detail.get("constraint") or "").endswith("_not_null"):
            out.append(_finding("drop-constraint", op,
                                f"{op.table} 제약 {op.detail.get('constraint') or ''} 삭제",
                                ["무결성 검사가 사라진다"]))
    elif op.kind in {"update", "delete"} and "LIMIT" not in op.sql.upper():
        out.append(_finding("dml-in-migration", op,
                            f"{op.table} 데이터 변경",
                            [cost_text, "스키마 변경과 분리하는 편이 안전하다"]))

    # 읽기까지 막는 잠금이 오래 유지되는 문장
    if op.blocking and op.lock.blocks_reads and op.estimate(rates) >= 1.0:
        out.append(_finding("lock-blocks-reads", op,
                            f"{op.target} 읽기 차단 {duration(op.estimate(rates))}",
                            [f"{op.lock_mode} · {op.lock.describe()}", cost_text]))
    return out


# --------------------------------------------------------------------- 파일 전체
def _migration_findings(migration: Migration, rates=None) -> list[Finding]:
    out: list[Finding] = []
    blocking = migration.blocking_ops
    if migration.transaction_wrapped and len(blocking) >= 2:
        total = migration.hold_seconds(rates)
        first = blocking[0]
        out.append(
            Finding(
                rule=rule("locks-held-to-commit"),
                ref=first.ref,
                line=first.line,
                table=first.table,
                summary="BEGIN ... COMMIT 하나로 묶여 있다",
                evidence=[
                    f"막는 문장 {len(blocking)}개 · 합계 {duration(total)} 동안 락 유지",
                    "가장 오래 걸리는 문장이 끝나도 커밋 전까지 앞의 락이 풀리지 않는다",
                ],
            )
        )

    has_timeout = any("LOCK_TIMEOUT" in op.sql.upper() for op in migration.ops)
    if blocking and not has_timeout:
        first = blocking[0]
        out.append(
            Finding(
                rule=rule("no-lock-timeout"),
                ref=first.ref,
                line=first.line,
                table=first.table,
                summary="SET lock_timeout 이 없다",
                evidence=["락을 못 잡으면 무한정 기다린다", "권장: SET lock_timeout = '3s';"],
            )
        )

    for op in migration.ops:
        if op.kind == "create_index" and op.detail.get("concurrently"):
            if op.in_transaction or migration.transaction_wrapped:
                out.append(_finding("concurrent-in-transaction", op,
                                    "트랜잭션 안의 CREATE INDEX CONCURRENTLY",
                                    ["BEGIN ... COMMIT 안에서는 실행할 수 없다"]))
        if op.kind == "create_index" and op.detail.get("expression") and op.detail.get("concurrently"):
            pass   # 식 인덱스도 CONCURRENTLY 가능 — 막지 않는다
    return out


def findings(migration: Migration, rates=None) -> list[Finding]:
    out: list[Finding] = []
    for op in migration.ops:
        out.extend(_op_findings(migration, op, rates))
    out.extend(_migration_findings(migration, rates))
    seen: set[tuple[str, str]] = set()
    unique: list[Finding] = []
    for finding in sorted(out, key=lambda f: (int(f.severity), f.line, f.rule_id)):
        key = (finding.rule_id, finding.ref)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def by_severity(items: list[Finding]) -> dict[Severity, list[Finding]]:
    table: dict[Severity, list[Finding]] = {s: [] for s in Severity}
    for item in items:
        table[item.severity].append(item)
    return table


def summary_counts(items: list[Finding]) -> dict[Severity, int]:
    return {s: len(v) for s, v in by_severity(items).items()}


def verdict(items: list[Finding]) -> str:
    counts = summary_counts(items)
    if counts[Severity.치명]:
        return "보류"
    if counts[Severity.심각]:
        return "주의"
    return "통과"
