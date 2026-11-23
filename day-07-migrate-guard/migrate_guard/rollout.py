"""한 번에 거는 마이그레이션을 여러 배포로 쪼갠다 — 확장(expand) → 백필(backfill) → 전환(contract).

원본은 지우지 않는다. 위험한 문장만 같은 뜻의 안전한 단계로 바꾸고,
바꾼 이유를 옆에 적는다. 남는 위험(값 손실)은 숨기지 않고 따로 모은다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dialect import CostKind, FIXED_SECONDS, parse_type
from .operations import Migration, Operation, estimate_seconds

__all__ = ["Step", "Phase", "expand_contract", "rollout_sql", "PHASE_TITLES"]

PHASE_TITLES = {
    "now": "1단계 · 지금 배포",
    "backfill": "2단계 · 백필 (트랜잭션 밖 · 나눠서)",
    "later": "3단계 · 다음 배포",
}

BATCH = 5000


@dataclass
class Step:
    sql: str
    note: str = ""
    blocks: bool = False
    seconds: float = 0.0
    changed: bool = False        # 원본과 달라진 단계인가


@dataclass
class Phase:
    key: str
    steps: list[Step] = field(default_factory=list)
    why: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return PHASE_TITLES[self.key]


def _name(*parts: str) -> str:
    raw = "_".join(p for p in parts if p)
    cleaned = re.sub(r"[^0-9A-Za-z_가-힣]", "_", raw)
    return cleaned[:63]


def _pk(migration: Migration, table_name: str | None) -> str:
    table = migration.schema.table(table_name or "")
    if table and table.primary_key:
        return table.primary_key[0]
    return "ctid"


def _meta(op: Operation) -> Step:
    return Step(op.sql.rstrip(";") + ";", blocks=op.blocking, seconds=op.estimate())


_INT_BOUNDS = {16: (-32768, 32767), 32: (-2147483648, 2147483647), 64: (-9223372036854775808, 9223372036854775807)}


def _narrowing_check(table: str, column: str, old: str, new: str) -> str:
    """축소 변환이 실패할 행이 있는지 세는 쿼리 — 타입에 맞게."""
    before, after = parse_type(old), parse_type(new)
    if before.base in {"smallint", "int2", "integer", "int", "int4", "bigint", "int8"} and \
            after.base in {"smallint", "int2", "integer", "int", "int4", "bigint", "int8"}:
        bits = {"smallint": 16, "int2": 16, "integer": 32, "int": 32, "int4": 32, "bigint": 64, "int8": 64}
        low, high = _INT_BOUNDS[bits[after.base]]
        return (f"-- 먼저 범위를 넘는 값이 있는지 센다 (0 이어야 진행)\n"
                f"SELECT count(*) FROM {table} WHERE {column} < {low} OR {column} > {high};")
    if after.base == "varchar" and after.args:
        return (f"-- 먼저 길이를 넘는 값이 있는지 센다 (0 이어야 진행)\n"
                f"SELECT count(*) FROM {table} WHERE length({column}) > {after.args[0]};")
    return (f"-- 값이 새 타입으로 변환되는지 먼저 확인한다 (0 이어야 진행)\n"
            f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL "
            f"AND pg_typeof({column}::text) IS NULL;")


def _constraint_columns(definition: str) -> list[str]:
    match = re.search(r"(?:UNIQUE|PRIMARY\s+KEY)\s*\(([^)]*)\)", definition, re.I | re.S)
    if not match:
        return []
    return [piece.strip().strip('"') for piece in match.group(1).split(",") if piece.strip()]


def expand_contract(migration: Migration, batch: int = BATCH) -> list[Phase]:
    phases = {key: Phase(key) for key in ("now", "backfill", "later")}

    def note(phase: str, text: str) -> None:
        if text not in phases[phase].why:
            phases[phase].why.append(text)

    for op in migration.ops:
        if op.kind in {"begin", "commit"}:
            continue
        table = op.table or "?"
        column = op.column or "?"
        rows = migration.table_rows(op.table)[0]

        if op.kind == "create_table":
            phases["now"].steps.append(_meta(op))
            continue

        if op.kind in {"drop_table", "truncate"}:
            if op.kind == "drop_table":
                temporary = _name("_deprecated", table)
                phases["now"].steps.append(Step(
                    f"ALTER TABLE {table} RENAME TO {temporary};",
                    note="코드에서 참조가 사라질 때까지 이름만 바꿔 남긴다",
                    seconds=FIXED_SECONDS, changed=True,
                ))
                phases["later"].steps.append(Step(f"DROP TABLE IF EXISTS {temporary};",
                                                  note="참조가 0건인 것을 확인한 뒤", seconds=FIXED_SECONDS))
                note("now", f"{table} 삭제를 이름 변경으로 미뤘다")
            else:
                phases["now"].steps.append(Step(
                    f"-- {table} 전체를 비우는 대신 나눠서 지운다\n"
                    f"DELETE FROM {table} WHERE ctid IN (SELECT ctid FROM {table} LIMIT {batch});",
                    note="같은 문장을 빈 결과가 나올 때까지 반복한다",
                    seconds=batch / 120_000 * 20, changed=True,
                ))
                note("now", "TRUNCATE 를 배치 DELETE 로 바꿨다")
            continue

        if op.kind == "add_column":
            definition = op.detail.get("type") or ""
            default = op.detail.get("default")
            needs_backfill = bool(op.detail.get("volatile_default")) or (
                default is not None and not op.detail.get("nullable", True)
            )
            if not needs_backfill:
                phases["now"].steps.append(_meta(op))
                continue
            phases["now"].steps.append(Step(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition};",
                note="기본값 없이 추가 — 메타데이터만 바뀐다",
                seconds=FIXED_SECONDS, changed=True,
            ))
            expression = default or "NULL"
            key = _pk(migration, op.table)
            phases["backfill"].steps.append(Step(
                f"UPDATE {table} SET {column} = {expression}\n"
                f" WHERE {column} IS NULL\n"
                f"   AND {key} IN (SELECT {key} FROM {table} WHERE {column} IS NULL LIMIT {batch});",
                note=f"{batch}행씩 · 같은 문장을 0행이 될 때까지 반복",
                seconds=batch / 120_000, changed=True,
            ))
            if default is not None:
                phases["later"].steps.append(Step(
                    f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {default};",
                    note="이제부터 들어오는 행에만 기본값이 붙는다", seconds=FIXED_SECONDS, changed=True,
                ))
            if not op.detail.get("nullable", True):
                phases["later"].steps.append(Step(
                    f"-- 3단계 전에 백필을 한 번 더 (1~3단계 사이에 들어온 NULL 행)\n"
                    f"UPDATE {table} SET {column} = {expression}\n"
                    f" WHERE {column} IS NULL\n"
                    f"   AND {key} IN (SELECT {key} FROM {table} WHERE {column} IS NULL LIMIT {batch});",
                    note="새로 들어온 행이 NULL 이면 여기서 채운다", seconds=batch / 120_000, changed=True,
                ))
                check = _name(table, column, "not_null")
                phases["later"].steps.append(Step(
                    f"ALTER TABLE {table} ADD CONSTRAINT {check} CHECK ({column} IS NOT NULL) NOT VALID;",
                    seconds=FIXED_SECONDS, changed=True,
                ))
                phases["later"].steps.append(Step(
                    f"ALTER TABLE {table} VALIDATE CONSTRAINT {check};",
                    note="기존 행 검증 — 이때는 쓰기를 막지 않는다",
                    seconds=estimate_seconds(_cost(CostKind.SCAN, rows)), changed=True,
                ))
                phases["later"].steps.append(Step(
                    f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL;",
                    note="검증된 CHECK 가 있으면 전체 스캔을 건너뛴다", seconds=FIXED_SECONDS, changed=True,
                ))
                phases["later"].steps.append(Step(
                    f"ALTER TABLE {table} DROP CONSTRAINT {check};", seconds=FIXED_SECONDS, changed=True,
                ))
            note("now", f"{table}.{column} 를 기본값 없이 추가하고 백필로 나눴다")
            continue

        if op.kind == "set_not_null":
            check = _name(table, column, "not_null")
            phases["now"].steps.append(Step(
                f"ALTER TABLE {table} ADD CONSTRAINT {check} CHECK ({column} IS NOT NULL) NOT VALID;",
                seconds=FIXED_SECONDS, changed=True,
            ))
            phases["now"].steps.append(Step(
                f"ALTER TABLE {table} VALIDATE CONSTRAINT {check};",
                note="쓰기를 막지 않고 기존 행을 검증한다",
                seconds=estimate_seconds(_cost(CostKind.SCAN, rows)), changed=True,
            ))
            phases["later"].steps.append(Step(
                f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL;",
                note="검증된 제약이 있으면 스캔 없이 끝난다", seconds=FIXED_SECONDS, changed=True,
            ))
            phases["later"].steps.append(Step(
                f"ALTER TABLE {table} DROP CONSTRAINT {check};", seconds=FIXED_SECONDS, changed=True,
            ))
            note("now", f"{table}.{column} NOT NULL 을 CHECK → VALIDATE → SET 으로 나눴다")
            continue

        if op.kind == "drop_index" and not re.match(r"^DROP\s+INDEX\s+CONCURRENTLY", op.sql, re.I):
            sql = re.sub(r"^DROP\s+INDEX\s+(?:IF\s+EXISTS\s+)?", "DROP INDEX CONCURRENTLY IF EXISTS ", op.sql, flags=re.I)
            phases["now"].steps.append(Step(
                sql.rstrip(";") + ";",
                note="CONCURRENTLY — 지우는 동안에도 쓰기가 지나간다 · 트랜잭션 밖",
                seconds=FIXED_SECONDS, changed=True,
            ))
            note("now", "DROP INDEX 를 CONCURRENTLY 로 바꿨다")
            continue

        if op.kind == "create_index":
            if op.detail.get("concurrently"):
                phases["now"].steps.append(Step(
                    op.sql.rstrip(";") + ";",
                    note="트랜잭션 밖에서 실행", seconds=op.estimate(), changed=False,
                ))
            else:
                sql = re.sub(r"^CREATE\s+(UNIQUE\s+)?INDEX\s+", lambda m: f"CREATE {m.group(1) or ''}INDEX CONCURRENTLY ",
                             op.sql, flags=re.I)
                phases["now"].steps.append(Step(
                    sql.rstrip(";") + ";",
                    note="CONCURRENTLY — 빌드 동안에도 쓰기가 지나간다 · 트랜잭션 밖에서",
                    seconds=op.estimate(), changed=True,
                ))
                note("now", f"{op.detail.get('index') or '인덱스'} 를 CONCURRENTLY 로 바꿨다")
            continue

        if op.kind in {"add_foreign_key", "add_check"}:
            definition = op.detail.get("definition") or ""
            if op.detail.get("not_valid"):
                phases["now"].steps.append(_meta(op))
                continue
            phases["now"].steps.append(Step(
                f"ALTER TABLE {table} ADD {definition} NOT VALID;",
                note="지금은 기존 행을 보지 않는다",
                seconds=FIXED_SECONDS, changed=True,
            ))
            phases["later"].steps.append(Step(
                f"ALTER TABLE {table} VALIDATE CONSTRAINT {op.detail.get('constraint')};",
                note="쓰기를 막지 않고 기존 행을 검증한다",
                seconds=estimate_seconds(_cost(CostKind.SCAN, rows)), changed=True,
            ))
            note("now", f"{table} {op.detail.get('constraint_kind')} 제약을 NOT VALID → VALIDATE 로 나눴다")
            continue

        if op.kind in {"add_unique", "add_primary_key"}:
            definition = op.detail.get("definition") or ""
            columns = _constraint_columns(definition)
            name = op.detail.get("constraint") or _name(table, "_".join(columns) or "key", "key")
            index_name = _name(name, "idx")
            phases["now"].steps.append(Step(
                f"CREATE UNIQUE INDEX CONCURRENTLY {index_name} ON {table} ({', '.join(columns) or '…'});",
                note="제약 대신 인덱스를 먼저 만든다 · 트랜잭션 밖",
                seconds=estimate_seconds(_cost(CostKind.INDEX, rows)), changed=True,
            ))
            phases["later"].steps.append(Step(
                f"ALTER TABLE {table} ADD CONSTRAINT {name} "
                f"{'UNIQUE' if op.kind == 'add_unique' else 'PRIMARY KEY'} USING INDEX {index_name};",
                note="이미 만든 인덱스를 제약으로 승격 — ACCESS EXCLUSIVE 는 순간이다",
                seconds=FIXED_SECONDS, changed=True,
            ))
            note("now", f"{table} {op.detail.get('constraint_kind')} 제약을 CONCURRENTLY 인덱스로 나눴다")
            continue

        if op.kind == "alter_type":
            target_type = op.detail.get("to") or ""
            new_column = _name(column, "new")
            key = _pk(migration, op.table)
            if op.detail.get("change") == "RISKY":
                phases["now"].steps.append(Step(
                    _narrowing_check(table, column, op.detail.get("from") or "", target_type),
                    note="축소 변환은 값에 따라 실패한다 · 0건일 때만 진행",
                    seconds=estimate_seconds(_cost(CostKind.SCAN, rows)), changed=True,
                ))
            phases["now"].steps.append(Step(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {new_column} {target_type};",
                note="새 컬럼은 메타데이터만", seconds=FIXED_SECONDS, changed=True,
            ))
            phases["backfill"].steps.append(Step(
                f"UPDATE {table} SET {new_column} = {column}::{target_type}\n"
                f" WHERE {new_column} IS NULL\n"
                f"   AND {key} IN (SELECT {key} FROM {table} WHERE {new_column} IS NULL LIMIT {batch});",
                note=f"{batch}행씩 · 실패한 행이 있으면 그 행만 따로 본다", seconds=batch / 120_000, changed=True,
            ))
            phases["later"].steps.append(Step(
                f"ALTER TABLE {table} RENAME COLUMN {column} TO {_name(column, 'old')};",
                note="코드가 새 컬럼을 읽기 시작한 뒤에", seconds=FIXED_SECONDS, changed=True,
            ))
            phases["later"].steps.append(Step(
                f"ALTER TABLE {table} RENAME COLUMN {new_column} TO {column};", seconds=FIXED_SECONDS, changed=True,
            ))
            phases["later"].steps.append(Step(
                f"ALTER TABLE {table} DROP COLUMN {_name(column, 'old')};",
                note="한 배포 더 지나고", seconds=FIXED_SECONDS,
            ))
            note("now", f"{table}.{column} 타입 변경을 새 컬럼 + 백필로 나눴다")
            continue

        if op.kind == "drop_column":
            temporary = _name("_deprecated", column)
            phases["now"].steps.append(Step(
                f"ALTER TABLE {table} RENAME COLUMN {column} TO {temporary};",
                note="값은 그대로 두고 이름만 바꾼다 — 코드에서 참조를 지우는 동안",
                seconds=FIXED_SECONDS, changed=True,
            ))
            phases["later"].steps.append(Step(
                f"ALTER TABLE {table} DROP COLUMN {temporary};",
                note="이 시점에 값이 사라진다 · 필요하면 먼저 백업", seconds=FIXED_SECONDS,
            ))
            note("now", f"{table}.{column} 삭제를 이름 변경으로 미뤘다")
            continue

        if op.kind == "rename_column":
            new = op.detail.get("to") or "?"
            table_obj = migration.schema.table(op.table or "")
            old_column = table_obj.column(column) if table_obj else None
            definition = f"{old_column.type}" if old_column else "…"
            key = _pk(migration, op.table)
            phases["now"].steps.append(Step(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {new} {definition};",
                note="새 이름을 먼저 만든다", seconds=FIXED_SECONDS, changed=True,
            ))
            phases["backfill"].steps.append(Step(
                f"UPDATE {table} SET {new} = {column}\n"
                f" WHERE {new} IS NULL\n"
                f"   AND {key} IN (SELECT {key} FROM {table} WHERE {new} IS NULL LIMIT {batch});",
                note="코드는 두 컬럼에 모두 쓰고, 읽기는 새 컬럼으로 옮긴다", seconds=batch / 120_000, changed=True,
            ))
            phases["later"].steps.append(Step(
                f"ALTER TABLE {table} DROP COLUMN {column};", note="구버전 코드가 사라진 뒤",
                seconds=FIXED_SECONDS,
            ))
            note("now", f"{table}.{column} 이름 변경을 새 컬럼 + 백필로 나눴다")
            continue

        if op.kind == "rename_table":
            new = op.detail.get("to") or "?"
            phases["now"].steps.append(Step(
                f"ALTER TABLE {table} RENAME TO {new};\nCREATE VIEW {table} AS SELECT * FROM {new};",
                note="이전 이름을 뷰로 유지해 구버전 코드를 살린다", seconds=FIXED_SECONDS, changed=True,
            ))
            phases["later"].steps.append(Step(
                f"DROP VIEW IF EXISTS {table};", note="모든 소비자가 새 이름으로 옮긴 뒤",
                seconds=FIXED_SECONDS,
            ))
            note("now", f"{table} 이름 변경에 이전 이름 뷰를 붙였다")
            continue

        if op.kind in {"update", "delete"} and not op.detail.get("where"):
            key = _pk(migration, op.table)
            if key == "ctid":
                target = f"ctid IN (SELECT ctid FROM {table} LIMIT {batch})"
            else:
                target = f"{key} IN (SELECT {key} FROM {table} WHERE {key} > :last_key ORDER BY {key} LIMIT {batch})"
            if op.kind == "update":
                match = re.search(r"\bSET\b(.+)$", op.sql, re.I | re.S)
                assignment = (match.group(1).strip() if match else "… = …")
                statement = f"UPDATE {table} SET {assignment} WHERE {target};"
                progress = f":last_key 를 갱신하며 마지막 {key} 까지 반복" if key != "ctid" else "같은 문장을 0행이 될 때까지 반복"
            else:
                statement = f"DELETE FROM {table} WHERE {target};"
                progress = f":last_key 를 갱신하며 마지막 {key} 까지 반복" if key != "ctid" else "같은 문장을 0행이 될 때까지 반복"
            phases["now"].steps.append(Step(
                f"-- 조건 없는 {op.kind.upper()} 대신 나눠서\n{statement}",
                note=f"{progress} · 사이사이 커밋", seconds=batch / 120_000, changed=True,
            ))
            note("now", "전체 갱신·삭제를 배치로 바꿨다")
            continue

        phases["now"].steps.append(_meta(op))

    # 메타데이터만 바뀌는 DDL 도 ACCESS EXCLUSIVE 를 순간적으로 잡는다.
    for phase in phases.values():
        for step in phase.steps:
            ddl = step.sql.strip().upper()
            if step.blocks or "CONCURRENTLY" in ddl or "VALIDATE CONSTRAINT" in ddl:
                continue
            if ddl.startswith(("ALTER TABLE", "DROP TABLE", "CREATE TABLE")):
                step.blocks = True
                step.seconds = max(step.seconds, FIXED_SECONDS)

    order = ["now", "backfill", "later"]
    return [phases[key] for key in order if phases[key].steps]


def _cost(kind: CostKind, rows: int):
    from .dialect import Cost

    return Cost(kind, rows)


def rollout_sql(migration: Migration, batch: int = BATCH) -> str:
    phases = expand_contract(migration, batch=batch)
    lines = ["-- migrate-guard 가 다시 쓴 마이그레이션 (확장 → 백필 → 전환)"]
    lines.append("-- 각 단계는 서로 다른 배포에서 실행합니다. 한 트랜잭션에 묶지 마세요.")
    for phase in phases:
        lines.append("")
        lines.append(f"-- ===== {phase.title} =====")
        for reason in phase.why:
            lines.append(f"-- 바꾼 이유: {reason}")
        for step in phase.steps:
            if step.note:
                lines.append(f"-- {step.note}")
            lines.append(step.sql.rstrip(";") + ";")
    return "\n".join(lines) + "\n"


def phase_peak(phase: Phase) -> float:
    """이 단계에서 가장 오래 잡는 락."""
    return max((step.seconds for step in phase.steps if step.blocks), default=0.0)
