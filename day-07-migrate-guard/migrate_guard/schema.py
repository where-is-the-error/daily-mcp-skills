"""스키마 모델 — `CREATE TABLE` 을 읽어 표·컬럼·제약으로 만들고, 마이그레이션을 적용해 본다.

여기서 하는 일은 "실행" 이 아니라 "읽기" 다. 마이그레이션 파일을 기준 스키마에
적용해 보면, 파일만 봐서는 보이지 않는 것이 보인다 — 어떤 컬럼이 사라지는지,
타입이 어떻게 바뀌는지, 인덱스가 어디에 걸리는지.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .splitter import Statement, match_paren, split_statements, split_top_level

__all__ = [
    "Column",
    "Table",
    "Index",
    "Schema",
    "parse_schema",
    "apply_statement",
    "schema_after",
    "SchemaDiff",
    "diff_schema",
    "parse_identifier",
]


def parse_identifier(text: str) -> str:
    """`"public"."Users"` → `public.Users`, 맨 이름은 소문자로 접는다."""
    parts: list[str] = []
    for chunk in text.strip().split("."):
        chunk = chunk.strip()
        if chunk.startswith('"') and chunk.endswith('"') and len(chunk) >= 2:
            parts.append(chunk[1:-1].replace('""', '"'))
        else:
            parts.append(chunk.lower())
    return ".".join(parts)


def bare(name: str) -> str:
    """스키마 이름을 뗀 마지막 조각 — 표를 짝지을 때 쓴다."""
    return name.rsplit(".", 1)[-1]


@dataclass
class Column:
    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False
    unique: bool = False
    references: str | None = None
    generated: bool = False

    def same_as(self, other: "Column") -> bool:
        return (
            normalize_type(self.type) == normalize_type(other.type)
            and self.nullable == other.nullable
            and normalize_expr(self.default) == normalize_expr(other.default)
            and self.primary_key == other.primary_key
            and self.generated == other.generated
        )


def normalize_type(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def normalize_expr(text: str | None) -> str | None:
    if text is None:
        return None
    return re.sub(r"\s+", " ", text.strip().lower())


@dataclass
class Table:
    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    constraints: dict[str, str] = field(default_factory=dict)   # 이름 → 정의

    def column(self, name: str) -> Column | None:
        return self.columns.get(name.lower())

    def add(self, column: Column) -> None:
        self.columns[column.name.lower()] = column

    def drop(self, name: str) -> bool:
        return self.columns.pop(name.lower(), None) is not None

    def rename(self, old: str, new: str) -> bool:
        col = self.columns.pop(old.lower(), None)
        if col is None:
            return False
        col.name = new.lower()
        self.columns[col.name] = col
        return True

    @property
    def primary_key(self) -> list[str]:
        return [c.name for c in self.columns.values() if c.primary_key]


@dataclass
class Index:
    name: str
    table: str
    columns: list[str] = field(default_factory=list)
    unique: bool = False
    concurrently: bool = False
    method: str = "btree"
    where: str | None = None
    expression: bool = False

    def key(self) -> tuple:
        return (
            self.table,
            tuple(self.columns),
            self.unique,
            self.method,
            normalize_expr(self.where),
        )


@dataclass
class Schema:
    tables: dict[str, Table] = field(default_factory=dict)
    indexes: dict[str, Index] = field(default_factory=dict)

    def table(self, name: str) -> Table | None:
        key = name.lower()
        if key in self.tables:
            return self.tables[key]
        short = bare(key)
        for candidate, table in self.tables.items():
            if bare(candidate) == short:
                return table
        return None

    def add_table(self, table: Table) -> None:
        self.tables[table.name.lower()] = table

    def drop_table(self, name: str) -> Table | None:
        table = self.table(name)
        if table is None:
            return None
        self.tables.pop(table.name.lower(), None)
        for index_name in [k for k, v in self.indexes.items() if bare(v.table) == bare(table.name)]:
            self.indexes.pop(index_name, None)
        return table

    def rename_table(self, old: str, new: str) -> bool:
        table = self.table(old)
        if table is None:
            return False
        self.tables.pop(table.name.lower(), None)
        table.name = new.lower()
        self.tables[table.name] = table
        for index in self.indexes.values():
            if bare(index.table) == bare(new) or bare(index.table) == bare(old):
                index.table = table.name
        return True

    @property
    def column_count(self) -> int:
        return sum(len(t.columns) for t in self.tables.values())


# --------------------------------------------------------------------- 컬럼 정의
_CONSTRAINT_WORDS = (
    "NOT", "NULL", "DEFAULT", "PRIMARY", "UNIQUE", "REFERENCES",
    "CHECK", "COLLATE", "GENERATED", "CONSTRAINT", "DEFERRABLE", "INITIALLY",
)
_CONSTRAINT_RE = re.compile(r"\b(?:" + "|".join(_CONSTRAINT_WORDS) + r")\b", re.I)
_NAME_RE = re.compile(r'\s*(?:"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_$]*)')


def _cut_at_constraint(rest: str) -> tuple[str, str]:
    """타입 부분과 제약 부분을 자른다 — 괄호 밖의 첫 제약 키워드에서."""
    depth = 0
    i, n = 0, len(rest)
    while i < n:
        ch = rest[i]
        if ch == "'":
            j = rest.find("'", i + 1)
            i = n if j == -1 else j + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            match = _CONSTRAINT_RE.match(rest, i)
            if match and (i == 0 or not rest[i - 1].isalnum() and rest[i - 1] not in "_$"):
                return rest[:i].strip(), rest[i:]
        i += 1
    return rest.strip(), ""


def parse_column(definition: str) -> Column | None:
    """`email varchar(255) NOT NULL DEFAULT ''` → Column."""
    text = definition.strip()
    match = _NAME_RE.match(text)
    if not match:
        return None
    name = parse_identifier(match.group(0).strip())
    rest = text[match.end():].strip()
    type_text, constraints = _cut_at_constraint(rest)
    if not type_text:
        return None

    upper = constraints.upper()
    nullable = not re.search(r"\bNOT\s+NULL\b", upper)
    primary = bool(re.search(r"\bPRIMARY\s+KEY\b", upper))
    unique = bool(re.search(r"\bUNIQUE\b", upper))
    default = None
    default_match = re.search(r"\bDEFAULT\s+(.+?)(?=\s+(?:NOT\s+NULL|NULL|PRIMARY|UNIQUE|CHECK|REFERENCES|COLLATE|GENERATED|CONSTRAINT|DEFERRABLE|INITIALLY)\b|$)",
                              constraints, re.I | re.S)
    if default_match:
        default = default_match.group(1).strip()
    elif re.search(r"\bGENERATED\b.*\bAS\s*\(", constraints, re.I | re.S):
        start = constraints.upper().find(" AS (")
        if start != -1:
            open_index = constraints.find("(", start)
            close = match_paren(constraints, open_index)
            if close != -1:
                default = constraints[open_index:close + 1].strip()
    references = None
    ref_match = re.search(r"\bREFERENCES\s+([\w.\"]+)", constraints, re.I)
    if ref_match:
        references = parse_identifier(ref_match.group(1))

    return Column(
        name=name,
        type=normalize_type(type_text),
        nullable=nullable and not primary,
        default=default,
        primary_key=primary,
        unique=unique,
        references=references,
        generated=bool(re.search(r"\bGENERATED\b", constraints, re.I)),
    )


# --------------------------------------------------------------------- CREATE TABLE
_CREATE_TABLE = re.compile(
    r"^CREATE\s+(?:UNLOGGED\s+|TEMP(?:ORARY)?\s+|GLOBAL\s+|LOCAL\s+)*TABLE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>(?:\"[^\"]+\"|[\w$]+)(?:\.(?:\"[^\"]+\"|[\w$]+))?)",
    re.I | re.S,
)


def parse_create_table(sql: str) -> Table | None:
    match = _CREATE_TABLE.match(sql.strip())
    if not match:
        return None
    name = parse_identifier(match.group("name"))
    open_index = sql.find("(", match.end())
    if open_index == -1:
        return None
    close = match_paren(sql, open_index)
    if close == -1:
        return None
    body = sql[open_index + 1:close]

    table = Table(name=name)
    for piece in split_top_level(body):
        head = piece.split(None, 1)[0].upper() if piece.split() else ""
        first = piece.strip().upper()
        if first.startswith(("PRIMARY KEY", "UNIQUE", "CHECK", "FOREIGN KEY", "EXCLUDE", "CONSTRAINT", "LIKE")):
            constraint_name = f"__inline_{len(table.constraints)}"
            named = re.match(r'CONSTRAINT\s+("(?:[^"]|"")+"|[\w$]+)\s+(.*)', piece, re.I | re.S)
            if named:
                constraint_name = parse_identifier(named.group(1))
                piece = named.group(2)
            table.constraints[constraint_name] = re.sub(r"\s+", " ", piece.strip())
            pk = re.match(r"PRIMARY\s+KEY\s*\(([^)]*)\)", piece.strip(), re.I | re.S)
            if pk:
                for col in split_top_level(pk.group(1)):
                    column = table.column(parse_identifier(col))
                    if column:
                        column.primary_key = True
                        column.nullable = False
            unique = re.match(r"UNIQUE\s*\(([^)]*)\)", piece.strip(), re.I | re.S)
            if unique:
                for col in split_top_level(unique.group(1)):
                    column = table.column(parse_identifier(col))
                    if column:
                        column.unique = True
            continue
        if head in {"CONSTRAINT"}:
            continue
        column = parse_column(piece)
        if column is not None:
            table.add(column)
    return table


# --------------------------------------------------------------------- CREATE INDEX
_CREATE_INDEX = re.compile(
    r"^CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?P<concurrent>CONCURRENTLY\s+)?"
    r"(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>(?:\"[^\"]+\"|[\w$]+)(?:\.(?:\"[^\"]+\"|[\w$]+))?)\s+"
    r"ON\s+(?:ONLY\s+)?(?P<table>(?:\"[^\"]+\"|[\w$]+)(?:\.(?:\"[^\"]+\"|[\w$]+))?)"
    r"(?:\s+USING\s+(?P<method>[\w$]+))?"
    r"\s*(?P<rest>.*)$",
    re.I | re.S,
)


def parse_create_index(sql: str) -> Index | None:
    match = _CREATE_INDEX.match(sql.strip())
    if not match:
        return None
    rest = match.group("rest")
    open_index = rest.find("(")
    columns: list[str] = []
    expression = False
    if open_index != -1:
        close = match_paren(rest, open_index)
        body = rest[open_index + 1:close] if close != -1 else rest[open_index + 1:]
        for piece in split_top_level(body):
            cleaned = piece.strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", cleaned):
                columns.append(cleaned.lower())
            elif cleaned.lower().endswith(" desc") and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*\s+desc", cleaned, re.I):
                columns.append(cleaned.split()[0].lower())
            else:
                expression = True
        rest = rest[close + 1:] if close != -1 else ""
    where = None
    where_match = re.search(r"\bWHERE\s+(.+)$", rest, re.I | re.S)
    if where_match:
        where = re.sub(r"\s+", " ", where_match.group(1).strip())
    return Index(
        name=parse_identifier(match.group("name")),
        table=parse_identifier(match.group("table")),
        columns=columns,
        unique=bool(match.group("unique")),
        concurrently=bool(match.group("concurrent")),
        method=(match.group("method") or "btree").lower(),
        where=where,
        expression=expression,
    )


# --------------------------------------------------------------------- ALTER 적용
_ALTER_TABLE = re.compile(
    r"^ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?"
    r"(?P<name>(?:\"[^\"]+\"|[\w$]+)(?:\.(?:\"[^\"]+\"|[\w$]+))?)\s+(?P<action>.*)$",
    re.I | re.S,
)
_ADD_COLUMN = re.compile(r"^ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(?P<def>.+)$", re.I | re.S)
_DROP_COLUMN = re.compile(r"^DROP\s+(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?(?P<name>\"[^\"]+\"|[\w$]+)", re.I)
_RENAME_COLUMN = re.compile(
    r"^RENAME\s+(?:COLUMN\s+)?(?P<old>\"[^\"]+\"|[\w$]+)\s+TO\s+(?P<new>\"[^\"]+\"|[\w$]+)", re.I
)
_RENAME_TABLE = re.compile(r"^RENAME\s+TO\s+(?P<new>\"[^\"]+\"|[\w$]+)", re.I)
_ALTER_COLUMN = re.compile(
    r"^ALTER\s+(?:COLUMN\s+)?(?P<name>\"[^\"]+\"|[\w$]+)\s+(?P<action>.*)$", re.I | re.S
)
_ADD_CONSTRAINT = re.compile(r"^ADD\s+(?P<def>.+)$", re.I | re.S)


def apply_statement(schema: Schema, statement: Statement | str) -> None:
    """문장 하나를 스키마 모델에 적용한다 (실행하지 않는다)."""
    sql = statement.code if isinstance(statement, Statement) else statement
    sql = sql.strip().rstrip(";").strip()
    upper = sql.upper()

    if upper.startswith("CREATE TABLE") or re.match(r"^CREATE\s+(UNLOGGED|TEMP)", upper):
        table = parse_create_table(sql)
        if table is not None:
            schema.add_table(table)
        return

    if upper.startswith("CREATE") and " INDEX " in upper + " ":
        index = parse_create_index(sql)
        if index is not None:
            schema.indexes[index.name] = index
        return

    if upper.startswith("DROP INDEX"):
        match = re.search(r"DROP\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+EXISTS\s+)?(.+?)(?:\s+CASCADE|\s+RESTRICT)?$",
                          sql, re.I | re.S)
        if match:
            for piece in split_top_level(match.group(1)):
                schema.indexes.pop(parse_identifier(piece), None)
        return

    if upper.startswith("DROP TABLE"):
        match = re.search(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(.+?)(?:\s+CASCADE|\s+RESTRICT)?$", sql, re.I | re.S)
        if match:
            for piece in split_top_level(match.group(1)):
                schema.drop_table(parse_identifier(piece))
        return

    if upper.startswith("ALTER TABLE"):
        match = _ALTER_TABLE.match(sql)
        if not match:
            return
        table = schema.table(parse_identifier(match.group("name")))
        if table is None:
            return
        action = match.group("action").strip()
        _apply_alter(schema, table, action)


def _apply_alter(schema: Schema, table: Table, action: str) -> None:
    rename_table = _RENAME_TABLE.match(action)
    if rename_table:
        schema.rename_table(table.name, parse_identifier(rename_table.group("new")))
        return
    rename_column = _RENAME_COLUMN.match(action)
    if rename_column:
        table.rename(parse_identifier(rename_column.group("old")), parse_identifier(rename_column.group("new")))
        return
    if re.match(r"DROP\s+CONSTRAINT", action, re.I):
        _apply_constraint(table, action)
        return
    drop_column = _DROP_COLUMN.match(action)
    if drop_column:
        table.drop(parse_identifier(drop_column.group("name")))
        return
    add_column = _ADD_COLUMN.match(action)
    if add_column:
        definition = add_column.group("def").strip()
        if definition.upper().startswith(("CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN")):
            _apply_constraint(table, definition)
            return
        column = parse_column(definition)
        if column is not None:
            table.add(column)
        return
    alter_column = _ALTER_COLUMN.match(action)
    if alter_column:
        column = table.column(parse_identifier(alter_column.group("name")))
        if column is None:
            return
        rest = alter_column.group("action").strip()
        type_match = re.match(r"(?:SET\s+DATA\s+)?TYPE\s+(.+?)(?:\s+USING\s+.+)?$", rest, re.I | re.S)
        if type_match:
            column.type = normalize_type(type_match.group(1))
            return
        if re.match(r"SET\s+NOT\s+NULL", rest, re.I):
            column.nullable = False
            return
        if re.match(r"DROP\s+NOT\s+NULL", rest, re.I):
            column.nullable = True
            return
        default_match = re.match(r"SET\s+DEFAULT\s+(.+)$", rest, re.I | re.S)
        if default_match:
            column.default = default_match.group(1).strip()
            return
        if re.match(r"DROP\s+DEFAULT", rest, re.I):
            column.default = None
            return
        return
    if action.upper().startswith(("ADD ", "DROP CONSTRAINT")):
        _apply_constraint(table, action)


def _apply_constraint(table: Table, definition: str) -> None:
    text = definition.strip()
    drop = re.match(r"DROP\s+CONSTRAINT\s+(?:IF\s+EXISTS\s+)?(\"[^\"]+\"|[\w$]+)", text, re.I)
    if drop:
        table.constraints.pop(parse_identifier(drop.group(1)), None)
        return
    body = re.sub(r"^ADD\s+", "", text, flags=re.I).strip()
    name = f"__inline_{len(table.constraints)}"
    named = re.match(r'CONSTRAINT\s+("(?:[^"]|"")+"|[\w$]+)\s+(.*)', body, re.I | re.S)
    if named:
        name = parse_identifier(named.group(1))
        body = named.group(2).strip()
    if re.match(r"PRIMARY\s+KEY", body, re.I):
        pk = re.search(r"\(([^)]*)\)", body, re.S)
        if pk:
            for col in split_top_level(pk.group(1)):
                column = table.column(parse_identifier(col))
                if column:
                    column.primary_key = True
                    column.nullable = False
    table.constraints[name] = re.sub(r"\s+", " ", body)


# --------------------------------------------------------------------- 전체
def parse_schema(source: str) -> Schema:
    """기준 스키마 파일 하나(또는 여러 파일을 이어 붙인 것)를 읽는다."""
    schema = Schema()
    for statement in split_statements(source):
        apply_statement(schema, statement)
    return schema


def schema_after(schema: Schema, statements: list[Statement]) -> Schema:
    """기준 스키마에 마이그레이션 문장들을 차례로 적용한 '적용 후' 스키마."""
    import copy

    after = copy.deepcopy(schema)
    for statement in statements:
        apply_statement(after, statement)
    return after


# --------------------------------------------------------------------- 비교
@dataclass
class ColumnChange:
    table: str
    column: str
    field: str
    before: str
    after: str


@dataclass
class SchemaDiff:
    tables_added: list[str] = field(default_factory=list)
    tables_removed: list[str] = field(default_factory=list)
    columns_added: list[tuple[str, str]] = field(default_factory=list)
    columns_removed: list[tuple[str, str]] = field(default_factory=list)
    columns_changed: list[ColumnChange] = field(default_factory=list)
    indexes_added: list[str] = field(default_factory=list)
    indexes_removed: list[str] = field(default_factory=list)
    indexes_changed: list[tuple[str, str]] = field(default_factory=list)
    constraints_added: list[tuple[str, str]] = field(default_factory=list)
    constraints_removed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not any(
            (
                self.tables_added, self.tables_removed, self.columns_added, self.columns_removed,
                self.columns_changed, self.indexes_added, self.indexes_removed,
                self.indexes_changed, self.constraints_added, self.constraints_removed,
            )
        )


def _render_column(column: Column) -> str:
    bits = [column.type]
    bits.append("NULL" if column.nullable else "NOT NULL")
    if column.default is not None:
        bits.append(f"DEFAULT {column.default}")
    return " ".join(bits)


def diff_schema(before: Schema, after: Schema) -> SchemaDiff:
    diff = SchemaDiff()
    before_names = {bare(n): n for n in before.tables}
    after_names = {bare(n): n for n in after.tables}

    for short, full in after_names.items():
        if short not in before_names:
            diff.tables_added.append(after.tables[full].name)
    for short, full in before_names.items():
        if short not in after_names:
            diff.tables_removed.append(before.tables[full].name)

    for short in sorted(set(before_names) & set(after_names)):
        old = before.table(short)
        new = after.table(short)
        assert old is not None and new is not None
        for name, column in new.columns.items():
            previous = old.columns.get(name)
            if previous is None:
                diff.columns_added.append((new.name, column.name))
                continue
            for field, a, b in (
                ("type", normalize_type(previous.type), normalize_type(column.type)),
                ("nullable", str(previous.nullable), str(column.nullable)),
                ("default", str(normalize_expr(previous.default)), str(normalize_expr(column.default))),
                ("primary_key", str(previous.primary_key), str(column.primary_key)),
            ):
                if a != b:
                    diff.columns_changed.append(ColumnChange(new.name, column.name, field, a, b))
        for name, column in old.columns.items():
            if name not in new.columns:
                diff.columns_removed.append((old.name, column.name))
        for name, definition in new.constraints.items():
            if old.constraints.get(name) != definition:
                diff.constraints_added.append((new.name, name))
        for name in old.constraints:
            if name not in new.constraints:
                diff.constraints_removed.append((old.name, name))

    for name, index in after.indexes.items():
        previous = before.indexes.get(name)
        if previous is None:
            diff.indexes_added.append(name)
        elif previous.key() != index.key():
            diff.indexes_changed.append((name, _describe_index_change(previous, index)))
    for name in before.indexes:
        if name not in after.indexes:
            diff.indexes_removed.append(name)
    return diff


def _describe_index_change(before: Index, after: Index) -> str:
    bits = []
    if before.table != after.table:
        bits.append(f"{before.table} → {after.table}")
    if before.columns != after.columns:
        bits.append(f"({', '.join(before.columns)}) → ({', '.join(after.columns)})")
    if before.unique != after.unique:
        bits.append(f"unique {before.unique} → {after.unique}")
    if normalize_expr(before.where) != normalize_expr(after.where):
        bits.append(f"where {before.where} → {after.where}")
    return " · ".join(bits) or "정의 변경"
