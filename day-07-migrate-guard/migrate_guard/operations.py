"""문장 하나를 '무엇을 하는 문장인가' 로 분류하고, 락·비용·되돌릴 수 있는지를 붙인다.

분류는 PostgreSQL 이 실제로 하는 일을 따른다:
`ALTER TABLE ... ADD COLUMN ... DEFAULT 0` 은 (11 이상에서) 메타데이터만 바꾸고,
`random()` 처럼 매 행이 다른 기본값은 테이블을 통째로 다시 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import dialect
from .dialect import Cost, CostKind, LockInfo, TypeChange
from .schema import Schema, parse_column, parse_identifier, parse_schema, schema_after
from .splitter import Statement, split_statements, split_top_level

__all__ = ["Operation", "Migration", "DEFAULT_ROWS", "analyze", "estimate_seconds"]

# 행 수를 모를 때 쓰는 가정 — 결과에 '가정' 이라고 적는다.
DEFAULT_ROWS = 100_000

_VOLATILE = re.compile(
    r"\b(random|clock_timestamp|timeofday|gen_random_uuid|uuid_generate_v4|uuidv7|uuidv4|"
    r"nextval|md5|shuffle|setseed)\s*\(",
    re.I,
)


@dataclass
class Operation:
    ref: str
    line: int
    kind: str
    sql: str                       # 한 줄로 접은 원문
    table: str | None = None
    column: str | None = None
    lock_mode: str = "ACCESS SHARE"
    cost: Cost = field(default_factory=lambda: Cost(CostKind.NONE))
    metadata_only: bool = True
    irreversible: bool = False     # 값이 사라지는가
    contends: bool = True          # 기존 트래픽과 경합하는가 (새 테이블은 아니다)
    in_transaction: bool = False
    detail: dict = field(default_factory=dict)
    note: str = ""

    @property
    def target(self) -> str:
        """화면에 보일 대상 — 표, 없으면 인덱스·제약 이름."""
        return (self.table or self.detail.get("index") or self.detail.get("constraint") or "-")

    @property
    def lock(self) -> LockInfo:
        return dialect.lock(self.lock_mode)

    @property
    def blocking(self) -> bool:
        return self.contends and (self.lock.blocks_reads or self.lock.blocks_writes)

    def estimate(self, rates: dict[CostKind, float] | None = None) -> float:
        return estimate_seconds(self.cost, rates)


def estimate_seconds(cost: Cost, rates: dict[CostKind, float] | None = None) -> float:
    table = rates or dialect.DEFAULT_RATES
    if cost.kind is CostKind.NONE or not cost.rows:
        return dialect.FIXED_SECONDS
    return dialect.FIXED_SECONDS + cost.rows / table[cost.kind]


@dataclass
class Migration:
    source: str
    statements: list[Statement]
    ops: list[Operation]
    schema: Schema                 # 적용 전
    after: Schema                  # 적용 후
    pg_version: int
    rows: dict[str, int]
    transaction_wrapped: bool
    label: str = ""                # 화면에 보일 이름(파일 이름 등)
    names: dict[str, int] = field(default_factory=dict)   # 표별 행 수 출처

    def table_rows(self, table: str | None) -> tuple[int, bool]:
        """(행 수, 실제로 아는 값인가)."""
        if not table:
            return DEFAULT_ROWS, False
        short = table.rsplit(".", 1)[-1].lower()
        if short in self.rows:
            return self.rows[short], True
        return DEFAULT_ROWS, False

    @property
    def blocking_ops(self) -> list[Operation]:
        return [op for op in self.ops if op.blocking]

    def worst(self, rates=None) -> Operation | None:
        blocking = self.blocking_ops
        if not blocking:
            return None
        return max(blocking, key=lambda op: op.estimate(rates))

    def hold_seconds(self, rates=None) -> float:
        """락을 실제로 들고 있는 시간 — 트랜잭션 하나면 마지막까지 유지된다."""
        blocking = self.blocking_ops
        if not blocking:
            return 0.0
        estimates = [op.estimate(rates) for op in blocking]
        if self.transaction_wrapped:
            return sum(estimates)
        return max(estimates)

    def op_by_ref(self, ref: str) -> Operation | None:
        for op in self.ops:
            if op.ref == ref.lower():
                return op
        return None

    @property
    def sql_ops(self) -> list[Operation]:
        """BEGIN·COMMIT 을 뺀 실제 문장 — 개수를 셀 때는 이걸 쓴다."""
        return [op for op in self.ops if op.kind not in {"begin", "commit"}]

    def tables(self) -> list[str]:
        seen: list[str] = []
        for op in self.ops:
            if op.table and op.table not in seen:
                seen.append(op.table)
        return seen


# --------------------------------------------------------------------- helpers
def _dml_table(sql: str) -> str | None:
    patterns = (
        r"^\s*UPDATE\s+(?:ONLY\s+)?([\w.\"]+)",
        r"^\s*DELETE\s+FROM\s+(?:ONLY\s+)?([\w.\"]+)",
        r"^\s*INSERT\s+INTO\s+([\w.\"]+)",
        r"^\s*TRUNCATE\s+(?:TABLE\s+)?(?:ONLY\s+)?([\w.\"]+)",
        r"^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([\w.\"]+)",
    )
    for pattern in patterns:
        match = re.match(pattern, sql, re.I)
        if match:
            return parse_identifier(match.group(1))
    return None


def _has_where(sql: str) -> bool:
    match = re.search(r"\bWHERE\b(.+)$", sql, re.I | re.S)
    if not match:
        return False
    return bool(match.group(1).strip())


def _is_volatile(expression: str | None) -> bool:
    return bool(expression and _VOLATILE.search(expression))


def _constraint_kind(definition: str) -> str:
    upper = definition.upper()
    if "FOREIGN KEY" in upper or "REFERENCES" in upper:
        return "foreign_key"
    if "PRIMARY KEY" in upper:
        return "primary_key"
    if upper.lstrip().startswith("UNIQUE") or " UNIQUE" in upper:
        return "unique"
    if "CHECK" in upper:
        return "check"
    return "other"


# --------------------------------------------------------------------- 분류
def analyze(
    source: str,
    *,
    baseline: Schema | None = None,
    rows: dict[str, int] | None = None,
    pg_version: int = 16,
    rates: dict[CostKind, float] | None = None,
    label: str = "",
) -> Migration:
    """마이그레이션 텍스트 하나를 분석한다 — 실행은 하지 않는다."""
    statements = split_statements(source)
    schema = baseline if baseline is not None else Schema()
    working = schema_after(schema, [])          # deep copy
    stats = {k.lower(): int(v) for k, v in (rows or {}).items()}

    ops: list[Operation] = []
    depth = 0
    saw_begin = False
    saw_commit = False
    for statement in statements:
        op = _classify(statement, working, stats, pg_version, depth > 0)
        if op.kind == "begin":
            depth += 1
            saw_begin = True
        elif op.kind == "commit":
            depth = max(0, depth - 1)
            saw_commit = True
        else:
            from .schema import apply_statement

            apply_statement(working, statement)
        ops.append(op)

    wrapped = saw_begin
    after = schema_after(schema, statements)
    return Migration(
        source=source,
        statements=statements,
        ops=ops,
        schema=schema,
        after=after,
        pg_version=pg_version,
        rows=stats,
        transaction_wrapped=wrapped,
        label=label,
        names={},
    )


def _rows_for(migration_rows: dict[str, int], table: str | None) -> tuple[int, bool]:
    if not table:
        return DEFAULT_ROWS, False
    short = table.rsplit(".", 1)[-1].lower()
    if short in migration_rows:
        return migration_rows[short], True
    return DEFAULT_ROWS, False


def _classify(
    statement: Statement,
    schema: Schema,
    rows: dict[str, int],
    pg_version: int,
    in_txn: bool,
) -> Operation:
    sql = statement.code.strip().rstrip(";").strip()
    one = re.sub(r"\s+", " ", sql).strip()
    upper = one.upper()
    base = Operation(ref=statement.ref, line=statement.line, kind="other", sql=one, in_transaction=in_txn)

    if re.match(r"^(BEGIN|START\s+TRANSACTION)\b", upper):
        base.kind = "begin"
        base.contends = False
        base.lock_mode = "ACCESS SHARE"
        return base
    if re.match(r"^(COMMIT|END|ROLLBACK|ABORT)\b", upper):
        base.kind = "commit"
        base.contends = False
        base.lock_mode = "ACCESS SHARE"
        return base

    # ---------------------------------------------------------------- CREATE TABLE
    if re.match(r"^CREATE\s+(UNLOGGED\s+|TEMP(ORARY)?\s+)?TABLE\b", upper):
        from .schema import parse_create_table

        table = parse_create_table(sql)
        base.kind = "create_table"
        base.table = table.name if table else None
        base.lock_mode = "ACCESS EXCLUSIVE"
        base.metadata_only = True
        base.contends = False
        base.cost = Cost(CostKind.NONE)
        base.note = "새 테이블에만 잠금 — 기존 트래픽과 경합하지 않는다"
        return base

    # ---------------------------------------------------------------- ALTER TABLE
    if re.match(r"^ALTER\s+TABLE\b", upper):
        return _classify_alter(base, one, schema, rows, pg_version)

    # ---------------------------------------------------------------- INDEX
    if re.match(r"^CREATE\s+(UNIQUE\s+)?INDEX\b", upper):
        from .schema import parse_create_index

        index = parse_create_index(sql)
        base.kind = "create_index"
        base.table = index.table if index else None
        base.column = ", ".join(index.columns) if index and index.columns else None
        concurrent = bool(index and index.concurrently)
        base.detail = {
            "index": index.name if index else "",
            "unique": bool(index and index.unique),
            "concurrently": concurrent,
            "expression": bool(index and index.expression),
            "where": index.where if index else None,
        }
        base.lock_mode = "SHARE UPDATE EXCLUSIVE" if concurrent else "SHARE"
        base.metadata_only = False
        row_count, known = _rows_for(rows, base.table)
        base.cost = Cost(CostKind.INDEX, row_count, "인덱스 빌드")
        base.detail["rows_known"] = known
        if concurrent:
            base.note = "트랜잭션 안에서는 실행할 수 없다"
        return base

    if re.match(r"^DROP\s+INDEX\b", upper):
        concurrent = bool(re.match(r"^DROP\s+INDEX\s+CONCURRENTLY\b", upper))
        base.kind = "drop_index"
        name_match = re.search(r"DROP\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+EXISTS\s+)?([\w.\"]+)", one, re.I)
        base.detail = {"index": parse_identifier(name_match.group(1)) if name_match else "", "concurrently": concurrent}
        base.lock_mode = "SHARE UPDATE EXCLUSIVE" if concurrent else "ACCESS EXCLUSIVE"
        base.metadata_only = True
        base.cost = Cost(CostKind.NONE)
        return base

    # ---------------------------------------------------------------- DROP TABLE
    if re.match(r"^DROP\s+TABLE\b", upper):
        base.kind = "drop_table"
        base.table = _dml_table(one)
        base.lock_mode = "ACCESS EXCLUSIVE"
        base.metadata_only = True
        base.irreversible = True
        base.cost = Cost(CostKind.NONE)
        return base

    # ---------------------------------------------------------------- TRUNCATE
    if re.match(r"^TRUNCATE\b", upper):
        base.kind = "truncate"
        base.table = _dml_table(one)
        base.lock_mode = "ACCESS EXCLUSIVE"
        base.metadata_only = True
        base.irreversible = True
        base.cost = Cost(CostKind.NONE)
        return base

    # ---------------------------------------------------------------- DML
    if re.match(r"^UPDATE\b", upper):
        base.kind = "update"
        base.table = _dml_table(one)
        base.lock_mode = "ROW EXCLUSIVE"
        base.metadata_only = False
        has_where = _has_where(one)
        row_count, known = _rows_for(rows, base.table)
        base.cost = Cost(CostKind.WRITE, row_count if not has_where else max(1, row_count // 100),
                         "전체 갱신" if not has_where else "조건 갱신")
        base.detail = {"where": has_where, "rows_known": known}
        base.irreversible = not has_where
        return base
    if re.match(r"^DELETE\b", upper):
        base.kind = "delete"
        base.table = _dml_table(one)
        base.lock_mode = "ROW EXCLUSIVE"
        base.metadata_only = False
        has_where = _has_where(one)
        row_count, known = _rows_for(rows, base.table)
        base.cost = Cost(CostKind.WRITE, row_count if not has_where else max(1, row_count // 100),
                         "전체 삭제" if not has_where else "조건 삭제")
        base.detail = {"where": has_where, "rows_known": known}
        base.irreversible = not has_where
        return base
    if re.match(r"^INSERT\b", upper):
        base.kind = "insert"
        base.table = _dml_table(one)
        base.lock_mode = "ROW EXCLUSIVE"
        base.metadata_only = False
        base.cost = Cost(CostKind.WRITE, 1, "행 삽입")
        return base

    # ---------------------------------------------------------------- 그 밖
    if re.match(r"^(SET|RESET|SHOW|SELECT|DO|COMMENT|GRANT|REVOKE|ANALYZE|VACUUM|CREATE EXTENSION|"
                r"CREATE SEQUENCE|CREATE VIEW|CREATE TYPE|CREATE SCHEMA|ALTER SEQUENCE)\b", upper):
        base.kind = "other"
        base.metadata_only = True
        base.contends = False
        base.lock_mode = "ACCESS SHARE"
        return base

    base.kind = "other"
    base.contends = False
    base.metadata_only = True
    return base


_ALTER_TARGET = re.compile(
    r"^ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?([\w.\"]+)\s+(.+)$", re.I | re.S
)


def _classify_alter(base: Operation, sql: str, schema: Schema, rows: dict[str, int], pg_version: int) -> Operation:
    match = _ALTER_TARGET.match(sql)
    if not match:
        base.kind = "other"
        base.contends = False
        return base
    table_name = parse_identifier(match.group(1))
    action = match.group(2).strip()
    upper_action = action.upper()
    table = schema.table(table_name)
    base.table = table_name
    base.lock_mode = "ACCESS EXCLUSIVE"
    base.cost = Cost(CostKind.NONE)
    base.metadata_only = True
    row_count, known = _rows_for(rows, table_name)

    # --- RENAME
    rename_column = re.match(r"^RENAME\s+(?:COLUMN\s+)?([\w\"]+)\s+TO\s+([\w\"]+)", action, re.I)
    if rename_column:
        base.kind = "rename_column"
        base.column = parse_identifier(rename_column.group(1))
        base.detail = {"to": parse_identifier(rename_column.group(2))}
        return base
    if re.match(r"^RENAME\s+TO\b", action, re.I):
        base.kind = "rename_table"
        base.detail = {"to": action.split()[-1].strip('"')}
        return base

    # --- DROP COLUMN
    drop_column = re.match(r"^DROP\s+(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?([\w\"]+)", action, re.I)
    if drop_column and not upper_action.startswith(("DROP CONSTRAINT", "DROP DEFAULT", "DROP NOT NULL")):
        base.kind = "drop_column"
        base.column = parse_identifier(drop_column.group(1))
        base.irreversible = True
        return base

    # --- ADD COLUMN
    add_column = re.match(r"^ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(.+)$", action, re.I | re.S)
    if add_column and not upper_action.startswith(("ADD CONSTRAINT", "ADD PRIMARY", "ADD UNIQUE", "ADD CHECK",
                                                   "ADD FOREIGN", "ADD EXCLUDE")):
        definition = add_column.group(1).strip()
        column = parse_column(definition)
        base.kind = "add_column"
        base.column = column.name if column else None
        default = column.default if column else None
        base.detail = {
            "type": column.type if column else "",
            "default": default,
            "nullable": column.nullable if column else True,
            "volatile_default": _is_volatile(default),
            "references": column.references if column else None,
            "pg_version": pg_version,
            "rows_known": known,
        }
        if default is not None and _is_volatile(default):
            base.cost = Cost(CostKind.REWRITE, row_count, "휘발성 기본값 → 전체 재작성")
            base.metadata_only = False
        elif default is not None and pg_version < 11:
            base.cost = Cost(CostKind.REWRITE, row_count, "11 미만은 기본값 있는 컬럼 추가가 재작성")
            base.metadata_only = False
        else:
            base.metadata_only = True
        if column and column.references:
            base.note = "참조 테이블에도 공유 락이 걸린다"
        return base

    # --- ALTER COLUMN
    alter_column = re.match(r"^ALTER\s+(?:COLUMN\s+)?([\w\"]+)\s+(.+)$", action, re.I | re.S)
    if alter_column:
        name = parse_identifier(alter_column.group(1))
        rest = alter_column.group(2).strip()
        base.column = name
        current = table.column(name) if table else None

        type_match = re.match(r"(?:SET\s+DATA\s+)?TYPE\s+(.+?)(?:\s+COLLATE\s+.+?)?(?:\s+USING\s+(.+))?$",
                              rest, re.I | re.S)
        if type_match:
            new_type = re.sub(r"\s+", " ", type_match.group(1)).strip()
            using = type_match.group(2)
            old_type = current.type if current else ""
            change, why = dialect.type_change(old_type, new_type) if old_type else (TypeChange.REWRITE, "적용 전 타입을 모른다")
            base.kind = "alter_type"
            base.detail = {
                "from": old_type,
                "to": new_type,
                "change": change.name,
                "using": using,
                "why": why,
                "rows_known": known,
            }
            base.metadata_only = change in (TypeChange.SAME, TypeChange.METADATA) and not using
            if base.metadata_only:
                base.cost = Cost(CostKind.NONE)
            else:
                base.cost = Cost(CostKind.REWRITE, row_count, "테이블 재작성")
            if using:
                base.detail["why"] = f"{why} · USING 식이 있어 항상 재작성"
                base.metadata_only = False
                base.cost = Cost(CostKind.REWRITE, row_count, "USING 식 → 전체 재작성")
            return base

        if re.match(r"^SET\s+NOT\s+NULL", rest, re.I):
            base.kind = "set_not_null"
            has_check = _has_not_null_check(table, name)
            base.detail = {"check": has_check, "rows_known": known}
            if has_check:
                base.metadata_only = True
                base.cost = Cost(CostKind.NONE)
            else:
                base.metadata_only = False
                base.cost = Cost(CostKind.SCAN, row_count, "전체 스캔")
            return base

        if re.match(r"^DROP\s+NOT\s+NULL", rest, re.I):
            base.kind = "drop_not_null"
            return base

        if re.match(r"^SET\s+DEFAULT", rest, re.I) or re.match(r"^DROP\s+DEFAULT", rest, re.I):
            base.kind = "column_default"
            return base

        base.kind = "alter_column"
        return base

    # --- CONSTRAINT
    add_constraint = re.match(r"^ADD\s+(.+)$", action, re.I | re.S)
    if add_constraint:
        definition = add_constraint.group(1).strip()
        kind = _constraint_kind(definition)
        not_valid = bool(re.search(r"\bNOT\s+VALID\b", definition, re.I))
        name_match = re.match(r'CONSTRAINT\s+("(?:[^"]|"")+"|[\w$]+)', definition, re.I)
        constraint_name = parse_identifier(name_match.group(1)) if name_match else ""
        base.detail = {
            "constraint": constraint_name,
            "constraint_kind": kind,
            "not_valid": not_valid,
            "rows_known": known,
            "definition": re.sub(r"\s+", " ", definition),
        }
        if kind in {"foreign_key", "check"}:
            base.kind = "add_foreign_key" if kind == "foreign_key" else "add_check"
            base.lock_mode = "SHARE ROW EXCLUSIVE"
            if not_valid:
                base.metadata_only = True
                base.cost = Cost(CostKind.NONE)
            else:
                base.metadata_only = False
                base.cost = Cost(CostKind.SCAN, row_count, "기존 행 검증")
                base.note = "검증까지 하면 기존 행을 모두 읽는다"
            return base
        if kind in {"primary_key", "unique"}:
            base.kind = "add_unique" if kind == "unique" else "add_primary_key"
            base.metadata_only = False
            base.cost = Cost(CostKind.INDEX, row_count, "인덱스 빌드 + 검증")
            return base
        base.kind = "add_constraint"
        return base

    if re.match(r"^VALIDATE\s+CONSTRAINT", action, re.I):
        base.kind = "validate_constraint"
        base.lock_mode = "SHARE UPDATE EXCLUSIVE"
        base.metadata_only = False
        base.cost = Cost(CostKind.SCAN, row_count, "기존 행 검증")
        name_match = re.search(r"VALIDATE\s+CONSTRAINT\s+([\w\"]+)", action, re.I)
        base.column = None
        base.detail = {"constraint": parse_identifier(name_match.group(1)) if name_match else ""}
        return base

    if re.match(r"^DROP\s+CONSTRAINT", action, re.I):
        base.kind = "drop_constraint"
        name_match = re.search(r"DROP\s+CONSTRAINT\s+(?:IF\s+EXISTS\s+)?([\w\"]+)", action, re.I)
        base.detail = {"constraint": parse_identifier(name_match.group(1)) if name_match else ""}
        return base

    base.kind = "alter_table"
    return base


def _has_not_null_check(table, column: str) -> bool:
    """`CHECK (col IS NOT NULL)` 가 이미 있으면 12 이상은 스캔을 건너뛴다."""
    if table is None:
        return False
    for definition in table.constraints.values():
        if re.search(r"CHECK\s*\(", definition, re.I) and re.search(
            rf"\b{re.escape(column)}\b\s+IS\s+NOT\s+NULL", definition, re.I
        ):
            return True
    return False


def load_migration(
    path_or_sql: str,
    *,
    baseline_sql: str | None = None,
    rows: dict[str, int] | None = None,
    pg_version: int = 16,
) -> Migration:
    """파일 경로거나 SQL 문자열이면 그대로 분석한다."""
    from pathlib import Path

    candidate = Path(path_or_sql)
    is_file = candidate.is_file()
    text = candidate.read_text(encoding="utf-8") if is_file else path_or_sql
    baseline = parse_schema(baseline_sql) if baseline_sql else None
    return analyze(text, baseline=baseline, rows=rows, pg_version=pg_version,
                   label=candidate.name if is_file else "마이그레이션")
