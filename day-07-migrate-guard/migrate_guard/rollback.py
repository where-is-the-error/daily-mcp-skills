"""되돌리기 — 역순 SQL 을 만들되, 되돌릴 수 없는 것은 그렇다고 말한다.

되돌리기 SQL 이 있다는 것과 데이터가 돌아온다는 것은 다르다.
DROP COLUMN 은 컬럼을 다시 만들 수는 있어도 값을 되살리지는 못한다.
그 구분을 결과에 그대로 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .operations import Migration, Operation

__all__ = ["RollbackStep", "rollback", "rollback_sql", "irreversible_ops"]

_HEADER = """-- migrate-guard 가 만든 되돌리기 SQL (역순)
-- 실행 전에 백업을 확인하고, 되돌릴 수 없는 단계는 주석을 읽으세요.
--   · CREATE INDEX CONCURRENTLY / VALIDATE CONSTRAINT 는 트랜잭션 밖에서 실행합니다.
--   · 값이 사라진 단계는 SQL 로 되돌릴 수 없습니다(백업에서만 복구).
"""


@dataclass
class RollbackStep:
    ref: str
    line: int
    table: str | None
    sql: str | None
    reversible: bool
    reason: str
    note: str = ""

    def render(self) -> str:
        head = f"-- {self.ref} (줄 {self.line}) {self.table or ''}".rstrip()
        lines = [head]
        if self.sql:
            body = self.sql.strip()
            if not self.reversible:
                lines.append("-- ⚠️ " + self.reason)
            elif self.reason:
                lines.append("-- " + self.reason)
            lines.append(body if body.endswith(";") else body + ";")
        else:
            lines.append("-- ⚠️ " + self.reason)
        if self.note:
            lines.append("-- " + self.note)
        return "\n".join(lines)


def _column_definition(migration: Migration, op: Operation) -> str | None:
    table = migration.schema.table(op.table or "")
    column = table.column(op.column) if table and op.column else None
    if column is None:
        return None
    bits = [column.name, column.type]
    if not column.nullable:
        bits.append("NOT NULL")
    if column.default is not None:
        bits.append(f"DEFAULT {column.default}")
    return " ".join(bits)


def _step(op: Operation, sql: str | None, reversible: bool, reason: str, note: str = "") -> RollbackStep:
    return RollbackStep(op.ref, op.line, op.table, sql, reversible, reason, note)


def rollback(migration: Migration) -> list[RollbackStep]:
    steps: list[RollbackStep] = [step for step in (_inverse(migration, op) for op in reversed(migration.ops)) if step]
    return steps


def _inverse(migration: Migration, op: Operation) -> RollbackStep | None:
    table = op.table or "?"
    column = op.column or "?"

    if op.kind in {"begin", "commit"}:
        return None
    if op.kind == "create_table":
        return _step(op, f"DROP TABLE IF EXISTS {table}", False,
                     "테이블을 지우면 그 뒤에 쌓인 행도 함께 사라진다")
    if op.kind == "drop_table":
        return _step(op, None, False, "테이블과 값이 모두 사라졌다 · 백업에서만 복구")
    if op.kind == "truncate":
        return _step(op, None, False, "모든 행이 사라졌다 · 백업에서만 복구")
    if op.kind == "add_column":
        return _step(op, f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}", True,
                     "이 컬럼에 쓰인 값도 함께 사라진다")
    if op.kind == "drop_column":
        definition = _column_definition(migration, op)
        sql = f"ALTER TABLE {table} ADD COLUMN {definition}" if definition else None
        return _step(op, sql, False,
                     "스키마만 되살아난다 · 값은 복구되지 않는다",
                     "값이 필요하면 백업에서 복원해야 한다")
    if op.kind == "alter_type":
        old = op.detail.get("from") or ""
        if not old:
            return _step(op, None, False, "이전 타입을 알 수 없다")
        reversible = op.detail.get("change") in {"SAME", "METADATA"}
        return _step(op, f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {old}",
                     reversible,
                     "역방향도 재작성이며, 축소 방향이면 값이 깨질 수 있다" if not reversible else "메타데이터만 되돌린다")
    if op.kind == "set_not_null":
        return _step(op, f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL", True, "제약만 되돌린다")
    if op.kind == "drop_not_null":
        return _step(op, f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL", True,
                     "NULL 이 들어와 있으면 실패한다")
    if op.kind == "column_default":
        return _step(op, "-- 이전 DEFAULT 를 직접 적어 실행하세요", False,
                     "이전 기본값을 파일에 기록해 두지 않았다면 알 수 없다")
    if op.kind == "rename_column":
        return _step(op, f"ALTER TABLE {table} RENAME COLUMN {column} TO {op.detail.get('to')}", True,
                     "이름만 되돌린다")
    if op.kind == "rename_table":
        return _step(op, f"ALTER TABLE {table} RENAME TO {op.detail.get('to')}", True, "이름만 되돌린다")
    if op.kind == "create_index":
        name = op.detail.get("index") or ""
        return _step(op, f"DROP INDEX CONCURRENTLY IF EXISTS {name}", True,
                     "인덱스만 지운다(트랜잭션 밖에서 실행)")
    if op.kind == "drop_index":
        return _step(op, None, False, "지운 인덱스의 정의는 파일에 없다 — 원래 CREATE 문을 다시 실행해야 한다")
    if op.kind in {"add_foreign_key", "add_check", "add_unique", "add_primary_key", "add_constraint"}:
        name = op.detail.get("constraint") or ""
        if not name:
            return _step(op, None, False, "제약 이름이 없어 지울 대상을 특정할 수 없다")
        return _step(op, f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}", True, "제약만 되돌린다")
    if op.kind == "validate_constraint":
        name = op.detail.get("constraint") or ""
        return _step(op, None, False,
                     "VALIDATE 는 되돌리는 문장이 없다 — 제약을 지우고 NOT VALID 로 다시 단다",
                     f"ALTER TABLE {table} DROP CONSTRAINT {name};" if name else "")
    if op.kind == "drop_constraint":
        return _step(op, None, False, "지운 제약의 정의를 파일에 기록해 두지 않았다면 되살릴 수 없다")
    if op.kind in {"update", "delete"}:
        return _step(op, None, False, "바뀐 값을 되돌릴 수 없다 · 백업에서만 복구")
    if op.kind == "insert":
        return _step(op, None, False, "넣은 행을 특정할 수 없다")
    if op.kind == "other":
        return None
    return _step(op, None, False, "이 문장의 반대 동작을 자동으로 만들 수 없다")


def irreversible_ops(migration: Migration) -> list[Operation]:
    return [op for op in migration.ops if op.irreversible]


def rollback_sql(migration: Migration) -> str:
    steps = rollback(migration)
    body = "\n\n".join(step.render() for step in steps)
    lost = irreversible_ops(migration)
    summary = []
    summary.append(f"-- 되돌리기 단계 {len(steps)}개 · 값이 사라진 문장 {len(lost)}개")
    if lost:
        summary.append("-- 값이 사라진 문장: " + ", ".join(f"{op.ref}({op.kind})" for op in lost))
    return _HEADER + "\n".join(summary) + "\n\n" + body + "\n"
