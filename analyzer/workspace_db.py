"""SQLite-backed workspace for interactive SQL playground tables and sample data."""

from __future__ import annotations

import math
import random
import re
import sqlite3
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from .lexer import KEYWORDS, tokenize

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DB_PATH = BASE_DIR / "playground.sqlite3"
SUPPORTED_COLUMN_TYPES = {
    "INTEGER",
    "VARCHAR",
    "TEXT",
    "DECIMAL",
    "REAL",
    "BOOLEAN",
    "DATE",
}
DEFAULT_TABLES = {
    "users": [
        {"name": "id", "type": "INTEGER", "primary_key": True, "not_null": True},
        {"name": "username", "type": "VARCHAR", "not_null": True, "unique": True},
        {"name": "email", "type": "VARCHAR", "not_null": True, "unique": True},
        {"name": "age", "type": "INTEGER", "not_null": True},
        {"name": "role", "type": "VARCHAR", "not_null": False},
    ],
    "orders": [
        {"name": "id", "type": "INTEGER", "primary_key": True, "not_null": True},
        {"name": "user_id", "type": "INTEGER", "not_null": True, "references": "users.id"},
        {"name": "total", "type": "DECIMAL", "not_null": True},
        {"name": "status", "type": "VARCHAR", "not_null": True},
    ],
}
DEFAULT_SAMPLE_ROWS = {
    "users": [
        (1, "alice", "alice@example.test", 24, "student"),
        (2, "ben", "ben@example.test", 17, "viewer"),
        (3, "casey", "casey@example.test", 32, "admin"),
    ],
    "orders": [
        (1, 1, 89.50, "shipped"),
        (2, 3, 145.00, "processing"),
    ],
}


def _quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _normalize_type(raw_type: str | None) -> str:
    if not raw_type:
        return "TEXT"
    upper = raw_type.upper().strip()
    if upper.startswith("INT"):
        return "INTEGER"
    if upper.startswith("CHAR"):
        return "VARCHAR"
    if upper.startswith("TEXT"):
        return "TEXT"
    if upper.startswith("DEC") or upper.startswith("NUM"):
        return "DECIMAL"
    if upper.startswith("BOOL"):
        return "BOOLEAN"
    if upper.startswith("DATE"):
        return "DATE"
    if upper.startswith("REAL") or upper.startswith("FLOAT"):
        return "REAL"
    return upper


def _connect(read_only: bool = False):
    if read_only:
        uri = WORKSPACE_DB_PATH.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
    else:
        connection = sqlite3.connect(WORKSPACE_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _validate_table_name(name: str) -> str:
    value = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("Table names must use letters, numbers or underscores and cannot start with a digit.")
    if value.lower().startswith("__workspace_") or value.lower().startswith("sqlite_"):
        raise ValueError("Table names beginning with '__workspace_' or 'sqlite_' are reserved.")
    if value.upper() in KEYWORDS:
        raise ValueError(f"'{value}' is a reserved SQL keyword and cannot be used as a table name.")
    return value


def _validate_column_name(name: str) -> str:
    value = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("Column names must use letters, numbers or underscores and cannot start with a digit.")
    if value.upper() in KEYWORDS:
        raise ValueError(f"'{value}' is a reserved SQL keyword and cannot be used as a column name.")
    if value.lower() in {"rowid", "_rowid_", "oid", "__workspace_rowid"}:
        raise ValueError(f"'{value}' is reserved by SQLite and cannot be used as a column name.")
    return value


def _normalize_columns(columns: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    primary_key_count = 0
    for raw in columns:
        if not isinstance(raw, dict):
            raise ValueError("Each column definition must be an object.")
        name = _validate_column_name(raw.get("name", ""))
        if name.lower() in seen_names:
            raise ValueError(f"Duplicate column name '{name}' is not allowed.")
        seen_names.add(name.lower())
        column_type = str(raw.get("type") or "TEXT").upper().strip()
        if column_type not in SUPPORTED_COLUMN_TYPES:
            raise ValueError(f"Unsupported column type '{column_type}'.")
        constraints = {}
        for key in ("primary_key", "not_null", "unique"):
            value = raw.get(key, False)
            if not isinstance(value, bool):
                raise ValueError(f"Column constraint '{key}' must be true or false.")
            constraints[key] = value
        normalized_column = {
            "name": name,
            "type": _normalize_type(column_type),
            "primary_key": constraints["primary_key"],
            "not_null": constraints["not_null"] or constraints["primary_key"],
            "unique": constraints["unique"],
            "references": raw.get("references") or None,
        }
        if normalized_column["primary_key"]:
            primary_key_count += 1
        normalized.append(normalized_column)
    if primary_key_count > 1:
        raise ValueError("Only one primary key column is supported in the workspace editor.")
    return normalized


def _build_create_table_sql(table_name: str, columns: list[dict[str, Any]]) -> str:
    pieces: list[str] = []
    for column in columns:
        clause = [f"{_quote_identifier(column['name'])} {column['type']}"]
        if column["primary_key"]:
            clause.append("PRIMARY KEY")
        if column["not_null"]:
            clause.append("NOT NULL")
        if column["unique"]:
            clause.append("UNIQUE")
        if column["references"]:
            reference = str(column["references"]).strip()
            if "." not in reference:
                raise ValueError(f"Foreign key reference on '{column['name']}' must look like 'table.column'.")
            parent_table, parent_column = reference.split(".", 1)
            clause.append(f"REFERENCES {_quote_identifier(parent_table)}({_quote_identifier(parent_column)})")
        pieces.append(" ".join(clause))
    return f"CREATE TABLE {_quote_identifier(table_name)} ({', '.join(pieces)});"


def list_tables() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT GLOB 'sqlite_*' AND name NOT GLOB '__workspace_*' ORDER BY name"
        ).fetchall()
    return [row["name"] for row in rows]


def create_table(table_name: str, columns: list[dict[str, Any]], replace: bool = False):
    table_name = _validate_table_name(table_name)
    normalized_columns = _normalize_columns(columns)
    if not normalized_columns:
        raise ValueError("At least one column is required.")
    existing_tables = {name.lower(): name for name in list_tables()}
    if table_name.lower() in existing_tables and not replace:
        raise ValueError(f"Table '{table_name}' already exists. Update or delete it before creating a new table with the same name.")
    if replace and table_name.lower() in existing_tables:
        return update_table(
            table_name,
            normalized_columns,
            previous_name=existing_tables[table_name.lower()],
        )
    _validate_foreign_key_definitions(table_name, normalized_columns)
    with _connect() as conn:
        conn.execute(_build_create_table_sql(table_name, normalized_columns))
    return get_table_definition(table_name)


def update_table(table_name: str, columns: list[dict[str, Any]], previous_name: str | None = None):
    table_name = _validate_table_name(table_name)
    old_name = _validate_table_name(previous_name) if previous_name else table_name
    tables = {name.lower(): name for name in list_tables()}
    if old_name.lower() not in tables:
        raise ValueError(f"Table '{old_name}' does not exist.")
    old_name = tables[old_name.lower()]
    if table_name.lower() != old_name.lower() and table_name.lower() in tables:
        raise ValueError(f"Table '{table_name}' already exists.")
    normalized_columns = _normalize_columns(columns)
    if not normalized_columns:
        raise ValueError("At least one column is required.")
    if table_name.lower() != old_name.lower():
        for column in normalized_columns:
            reference = column["references"]
            if reference and reference.split(".", 1)[0].lower() == old_name.lower():
                _, parent_column = reference.split(".", 1)
                column["references"] = f"{table_name}.{parent_column}"
    _validate_foreign_key_definitions(table_name, normalized_columns, ignore_table=old_name)

    temporary_name = f"__workspace_edit_{uuid.uuid4().hex}"
    with _connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute("BEGIN IMMEDIATE")
            old_columns = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({_quote_identifier(old_name)})")
            }
            new_columns = {column["name"] for column in normalized_columns}
            shared_columns = sorted(old_columns & new_columns)
            conn.execute(_build_create_table_sql(temporary_name, normalized_columns))
            if shared_columns:
                names = ", ".join(_quote_identifier(name) for name in shared_columns)
                conn.execute(
                    f"INSERT INTO {_quote_identifier(temporary_name)} ({names}) "
                    f"SELECT {names} FROM {_quote_identifier(old_name)}"
                )
            conn.execute(f"DROP TABLE {_quote_identifier(old_name)}")
            conn.execute(
                f"ALTER TABLE {_quote_identifier(temporary_name)} "
                f"RENAME TO {_quote_identifier(table_name)}"
            )
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise ValueError("The table changes would break existing foreign-key relationships.")
            conn.commit()
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise ValueError(
                f"Table changes cannot preserve existing records because a constraint would be violated: {error}."
            ) from error
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
    return get_table_definition(table_name)


def _validate_foreign_key_definitions(
    table_name: str,
    columns: list[dict[str, Any]],
    ignore_table: str | None = None,
):
    current_tables = {name.lower(): name for name in list_tables()}
    for column in columns:
        reference = column["references"]
        if not reference:
            continue
        if not isinstance(reference, str) or reference.count(".") != 1:
            raise ValueError(
                f"Foreign key reference on '{column['name']}' must look like 'table.column'."
            )
        parent_table, parent_column = reference.split(".", 1)
        _validate_table_name(parent_table)
        _validate_column_name(parent_column)
        if parent_table.lower() == table_name.lower():
            parent_columns = {item["name"].lower(): item["type"] for item in columns}
        elif ignore_table and parent_table.lower() == ignore_table.lower():
            parent_columns = {
                row["name"].lower(): _normalize_type(row["type"])
                for row in _table_info(current_tables.get(parent_table.lower(), ignore_table))
            }
        elif parent_table.lower() in current_tables:
            parent_columns = {
                row["name"].lower(): _normalize_type(row["type"])
                for row in _table_info(current_tables[parent_table.lower()])
            }
        else:
            raise ValueError(f"Foreign key target table '{parent_table}' does not exist.")
        if parent_column.lower() not in parent_columns:
            raise ValueError(
                f"Foreign key target column '{parent_table}.{parent_column}' does not exist."
            )
        if not _foreign_key_types_compatible(parent_columns[parent_column.lower()], column["type"]):
            raise ValueError(
                f"Foreign key column '{column['name']}' must use the same data type as "
                f"'{parent_table}.{parent_column}'."
            )
        if parent_table.lower() == table_name.lower() and parent_column.lower() == column["name"].lower():
            raise ValueError("A column cannot reference itself as a foreign key.")


def _table_info(table_name: str):
    with _connect() as conn:
        return conn.execute(
            f"PRAGMA table_info({_quote_identifier(table_name)})"
        ).fetchall()


def _foreign_key_types_compatible(parent_type: str, child_type: str) -> bool:
    strings = {"TEXT", "VARCHAR"}
    return parent_type == child_type or (
        parent_type in strings and child_type in strings
    )


def drop_table(table_name: str):
    safe_name = _validate_table_name(table_name)
    if safe_name not in list_tables():
        raise ValueError(f"Table '{safe_name}' does not exist.")
    with _connect() as conn:
        conn.execute(f"DROP TABLE {_quote_identifier(safe_name)}")
    return {"deleted": safe_name}


def get_table_definition(table_name: str) -> dict[str, Any]:
    safe_name = _validate_table_name(table_name)
    if safe_name not in list_tables():
        raise ValueError(f"Table '{safe_name}' does not exist.")
    with _connect() as conn:
        column_rows = conn.execute(f"PRAGMA table_info({_quote_identifier(safe_name)})").fetchall()
        foreign_key_rows = conn.execute(f"PRAGMA foreign_key_list({_quote_identifier(safe_name)})").fetchall()
        ddl_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (safe_name,),
        ).fetchone()
        preview_rows = conn.execute(f"SELECT * FROM {_quote_identifier(safe_name)} LIMIT 25").fetchall()
        row_count = conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(safe_name)}").fetchone()[0]
        index_rows = conn.execute(f"PRAGMA index_list({_quote_identifier(safe_name)})").fetchall()

    unique_columns: set[str] = set()
    with _connect() as conn:
        for index_row in index_rows:
            if index_row["unique"]:
                info_rows = conn.execute(f"PRAGMA index_info({_quote_identifier(index_row['name'])})").fetchall()
                for info_row in info_rows:
                    unique_columns.add(info_row["name"])

    table_columns: list[dict[str, Any]] = []
    fk_by_column = {row["from"]: f"{row['table']}.{row['to']}" for row in foreign_key_rows}
    for column in column_rows:
        table_columns.append({
            "cid": column["cid"],
            "name": column["name"],
            "type": _normalize_type(column["type"]),
            "not_null": bool(column["notnull"]),
            "primary_key": bool(column["pk"]),
            "unique": column["name"] in unique_columns,
            "references": fk_by_column.get(column["name"]),
        })
    return {
        "name": safe_name,
        "columns": table_columns,
        "ddl": ddl_row["sql"] if ddl_row and ddl_row["sql"] else "",
        "rows": [dict(row) for row in preview_rows],
        "row_count": row_count,
    }


def get_table_rows(table_name: str, limit: int = 25):
    safe_name = _validate_table_name(table_name)
    if safe_name not in list_tables():
        raise ValueError(f"Table '{safe_name}' does not exist.")
    definition = get_table_definition(safe_name)
    primary_key = next(
        (column["name"] for column in definition["columns"] if column["primary_key"]),
        None,
    )
    with _connect(read_only=True) as conn:
        order_by = _quote_identifier(primary_key) if primary_key else "rowid"
        rows = conn.execute(
            f"SELECT rowid AS __workspace_rowid, * FROM {_quote_identifier(safe_name)} "
            f"ORDER BY {order_by} LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        return {
            "columns": [column["name"] for column in definition["columns"]],
            "primary_key": primary_key,
            "rows": [],
            "row_count": 0,
        }
    return {
        "columns": [column["name"] for column in definition["columns"]],
        "primary_key": primary_key,
        "rows": [dict(row) for row in rows],
        "row_count": len(rows),
    }


def _validated_record_values(table_name: str, values: Any, partial: bool = False):
    if not isinstance(values, dict):
        raise ValueError("Record values must be provided as an object.")
    definition = get_table_definition(table_name)
    by_name = {column["name"]: column for column in definition["columns"]}
    unknown = set(values) - set(by_name)
    if unknown:
        raise ValueError(f"Unknown column(s): {', '.join(sorted(unknown))}.")
    if not partial:
        missing = [
            name for name, column in by_name.items()
            if column["not_null"] and not (
                column["primary_key"] and column["type"] == "INTEGER"
            )
            and name not in values
        ]
        if missing:
            raise ValueError(f"Required column(s) are missing: {', '.join(missing)}.")

    validated = {}
    for name, value in values.items():
        column_type = by_name[name]["type"]
        if value is None or value == "":
            if by_name[name]["not_null"] or by_name[name]["primary_key"]:
                raise ValueError(f"'{name}' cannot be empty.")
            validated[name] = None
        elif column_type == "INTEGER":
            if isinstance(value, bool):
                raise ValueError(f"'{name}' must be an integer.")
            try:
                parsed = int(value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"'{name}' must be an integer.") from error
            if str(value).strip() not in (str(parsed), f"+{parsed}"):
                raise ValueError(f"'{name}' must be an integer.")
            validated[name] = parsed
        elif column_type in {"DECIMAL", "REAL"}:
            if isinstance(value, bool):
                raise ValueError(f"'{name}' must be a number.")
            try:
                number = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"'{name}' must be a number.") from error
            if not math.isfinite(number):
                raise ValueError(f"'{name}' must be a finite number.")
            validated[name] = number
        elif column_type == "BOOLEAN":
            if value in (True, 1, "1", "true", "TRUE"):
                validated[name] = 1
            elif value in (False, 0, "0", "false", "FALSE"):
                validated[name] = 0
            else:
                raise ValueError(f"'{name}' must be true or false.")
        elif column_type == "DATE":
            try:
                validated[name] = date.fromisoformat(str(value)).isoformat()
            except ValueError as error:
                raise ValueError(f"'{name}' must be a valid ISO date (YYYY-MM-DD).") from error
        else:
            validated[name] = str(value)
    return validated


def _friendly_integrity_error(error: sqlite3.IntegrityError) -> ValueError:
    message = str(error)
    if "UNIQUE constraint failed" in message or "PRIMARY KEY" in message:
        detail = message.split(": ", 1)[-1]
        return ValueError(f"A record already uses this unique or primary-key value ({detail}).")
    if "FOREIGN KEY constraint failed" in message:
        return ValueError("The foreign-key value must match an existing record in the referenced table.")
    if "NOT NULL constraint failed" in message:
        return ValueError(f"A required value is missing ({message.split(': ', 1)[-1]}).")
    return ValueError(f"Record violates a database constraint: {message}.")


def insert_record(table_name: str, values: dict[str, Any]):
    safe_name = _validate_table_name(table_name)
    record = _validated_record_values(safe_name, values)
    if not record:
        raise ValueError("Enter at least one value before inserting a record.")
    columns = list(record)
    sql = (
        f"INSERT INTO {_quote_identifier(safe_name)} "
        f"({', '.join(_quote_identifier(column) for column in columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})"
    )
    try:
        with _connect() as conn:
            cursor = conn.execute(sql, [record[column] for column in columns])
            rowid = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise _friendly_integrity_error(error) from error
    return {"rowid": rowid, "record": record}


def update_record(table_name: str, locator: dict[str, Any], values: dict[str, Any]):
    safe_name = _validate_table_name(table_name)
    definition = get_table_definition(safe_name)
    primary_key = next(
        (column["name"] for column in definition["columns"] if column["primary_key"]),
        None,
    )
    locator_column = primary_key or "rowid"
    locator_value = locator.get(locator_column)
    if locator_value is None:
        raise ValueError(f"A value for '{locator_column}' is required to identify the record.")
    record = _validated_record_values(safe_name, values, partial=True)
    if not record:
        raise ValueError("Enter at least one value to update.")
    assignments = ", ".join(f"{_quote_identifier(name)} = ?" for name in record)
    try:
        with _connect() as conn:
            cursor = conn.execute(
                f"UPDATE {_quote_identifier(safe_name)} SET {assignments} "
                f"WHERE {_quote_identifier(locator_column)} = ?",
                [*record.values(), locator_value],
            )
    except sqlite3.IntegrityError as error:
        raise _friendly_integrity_error(error) from error
    if cursor.rowcount == 0:
        raise ValueError("The selected record no longer exists.")
    return {"updated": cursor.rowcount}


def delete_record(table_name: str, locator: dict[str, Any]):
    safe_name = _validate_table_name(table_name)
    definition = get_table_definition(safe_name)
    primary_key = next(
        (column["name"] for column in definition["columns"] if column["primary_key"]),
        None,
    )
    locator_column = primary_key or "rowid"
    locator_value = locator.get(locator_column)
    if locator_value is None:
        raise ValueError(f"A value for '{locator_column}' is required to identify the record.")
    try:
        with _connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM {_quote_identifier(safe_name)} "
                f"WHERE {_quote_identifier(locator_column)} = ?",
                (locator_value,),
            )
    except sqlite3.IntegrityError as error:
        raise _friendly_integrity_error(error) from error
    if cursor.rowcount == 0:
        raise ValueError("The selected record no longer exists.")
    return {"deleted": cursor.rowcount}


def load_schema_catalog() -> dict[str, dict[str, str]]:
    schema: dict[str, dict[str, str]] = {}
    for table_name in list_tables():
        with _connect() as conn:
            rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
        columns = {row["name"].lower(): _normalize_type(row["type"]) for row in rows}
        schema[table_name.lower()] = columns
    return schema


def get_workspace_snapshot() -> dict[str, Any]:
    tables = []
    for table_name in list_tables():
        definition = get_table_definition(table_name)
        row_data = get_table_rows(table_name, 25)
        tables.append({
            "name": table_name,
            "columns": definition["columns"],
            "ddl": definition["ddl"],
            "row_count": definition["row_count"],
            "primary_key": row_data["primary_key"],
            "preview": row_data["rows"],
        })
    return {"tables": tables, "schema": load_schema_catalog()}


def reset_workspace() -> dict[str, Any]:
    connection = _connect()
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        tables = [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT GLOB 'sqlite_*' AND name NOT GLOB '__workspace_*'"
            )
        ]
        for table_name in tables:
            connection.execute(f"DROP TABLE {_quote_identifier(table_name)}")
        connection.execute(
            "INSERT INTO __workspace_metadata (key, value) VALUES ('reset_by_user', 'true') "
            "ON CONFLICT(key) DO UPDATE SET value = 'true'"
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.close()
    return {"status": "ok", "message": "The playground database was reset successfully."}


def _initialise_workspace():
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS __workspace_metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        has_user_tables = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name NOT GLOB 'sqlite_*' AND name NOT GLOB '__workspace_*' LIMIT 1"
        ).fetchone()
        reset_by_user = conn.execute(
            "SELECT value FROM __workspace_metadata WHERE key = 'reset_by_user'"
        ).fetchone()
        if not has_user_tables and not (reset_by_user and reset_by_user["value"] == "true"):
            for table_name, definitions in DEFAULT_TABLES.items():
                conn.execute(_build_create_table_sql(
                    table_name,
                    _normalize_columns(definitions),
                ))
                rows = DEFAULT_SAMPLE_ROWS[table_name]
                column_names = ", ".join(
                    _quote_identifier(column["name"])
                    for column in _normalize_columns(definitions)
                )
                placeholders = ", ".join("?" for _ in rows[0])
                conn.executemany(
                    f"INSERT INTO {_quote_identifier(table_name)} ({column_names}) "
                    f"VALUES ({placeholders})",
                    rows,
                )
        conn.execute(
            "INSERT INTO __workspace_metadata (key, value) VALUES ('initialized', 'true') "
            "ON CONFLICT(key) DO UPDATE SET value = 'true'"
        )


_initialise_workspace()


def _sample_name_pool(kind: str) -> list[str]:
    pools = {
        "VARCHAR": [
            "Alice", "Brian", "Carmen", "Daniel", "Ella", "Frank", "Grace", "Hugo", "Ivy", "Jack",
            "Kara", "Leo", "Maya", "Nia", "Oscar", "Pia", "Quinn", "Ruby", "Sam", "Tara",
        ],
        "TEXT": [
            "Alpha", "Beta", "Gamma", "Delta", "Echo", "Foxtrot", "Harbor", "Iris", "Juniper", "Kepler",
            "Lumen", "Maple", "Nimble", "Oak", "Piper", "Quill", "Raven", "Sage", "Thorn", "Ultraviolet",
        ],
        "CATEGORY": ["Books", "Games", "Travel", "Sales", "Support", "Design", "Learning", "Finance", "Ops", "Research"],
        "ROLE": ["admin", "viewer", "editor", "student", "manager"],
    }
    return pools.get(kind, pools["TEXT"])


def _dependency_order(
    selected_tables: list[str],
    connection: sqlite3.Connection | None = None,
) -> list[str]:
    order: list[str] = []
    remaining = set(selected_tables)
    while remaining:
        ready = []
        for table_name in sorted(remaining):
            if connection is None:
                with _connect() as conn:
                    foreign_key_rows = conn.execute(
                        f"PRAGMA foreign_key_list({_quote_identifier(table_name)})"
                    ).fetchall()
            else:
                foreign_key_rows = connection.execute(
                    f"PRAGMA foreign_key_list({_quote_identifier(table_name)})"
                ).fetchall()
            parent_tables = {row["table"] for row in foreign_key_rows}
            if parent_tables.issubset(set(order)) or not parent_tables.intersection(remaining):
                ready.append(table_name)
        if not ready:
            order.extend(sorted(remaining))
            break
        for table_name in ready:
            remaining.remove(table_name)
            order.append(table_name)
    return order


def _generated_value(
    column: dict[str, Any],
    table_name: str,
    row_index: int,
    parent_values: dict[str, list[dict[str, Any]]],
    used_values: dict[str, set[Any]],
    connection: sqlite3.Connection,
):
    name = column["name"]
    column_type = _normalize_type(column["type"])
    unique_values = used_values.setdefault(f"{table_name}.{name}", set())
    foreign_keys = connection.execute(
        f"PRAGMA foreign_key_list({_quote_identifier(table_name)})"
    ).fetchall()
    foreign_key = next((item for item in foreign_keys if item["from"] == name), None)
    if foreign_key:
        parent_table, parent_column = foreign_key["table"], foreign_key["to"]
        candidates = parent_values.get(parent_table, [])
        if candidates:
            values = [candidate[parent_column] for candidate in candidates]
        else:
            parent_rows = connection.execute(
                f"SELECT {_quote_identifier(parent_column)} FROM {_quote_identifier(parent_table)}"
            ).fetchall()
            values = [row[0] for row in parent_rows]
        if column.get("unique"):
            values = [value for value in values if value not in unique_values]
        if values:
            value = random.choice(values)
            unique_values.add(value)
            return value
        if column["notnull"]:
            reason = (
                "does not have enough unused values for this UNIQUE foreign key"
                if column.get("unique")
                else "has no records"
            )
            raise ValueError(
                f"Cannot generate rows for '{table_name}': foreign-key table "
                f"'{parent_table}' {reason}. Select it too or insert parent records first."
            )
        return None

    if column["pk"]:
        if column_type == "INTEGER":
            current = connection.execute(
                f"SELECT MAX({_quote_identifier(name)}) FROM {_quote_identifier(table_name)}"
            ).fetchone()[0]
            value = (current or 0) + 1
            unique_values.add(value)
            return value
        candidate = f"{table_name}_{row_index + 1}"
        suffix = 2
        while candidate in unique_values:
            candidate = f"{table_name}_{row_index + 1}_{suffix}"
            suffix += 1
        unique_values.add(candidate)
        return candidate

    if column_type == "INTEGER":
        value = random.randint(1, 9999)
    elif column_type in {"VARCHAR", "TEXT"}:
        pool = (
            "ROLE" if "role" in name.lower()
            else "VARCHAR" if "name" in name.lower()
            else "CATEGORY"
        )
        base = random.choice(_sample_name_pool(pool))
        value = base
    elif column_type == "DECIMAL":
        value = round(random.uniform(10.0, 5000.0), 2)
    elif column_type == "REAL":
        value = round(random.uniform(0.0, 1000.0), 2)
    elif column_type == "BOOLEAN":
        if column.get("unique"):
            available = {0, 1} - unique_values
            if not available:
                raise ValueError(
                    f"Cannot generate more than two unique BOOLEAN values for '{table_name}.{name}'."
                )
            value = random.choice(tuple(available))
        else:
            value = random.randint(0, 1)
    elif column_type == "DATE":
        value = (
            date(2020, 1, 1) + timedelta(days=random.randint(1, 1500))
        ).isoformat()
    else:
        value = row_index + 1

    if column.get("unique"):
        used = unique_values
        base_value = value
        suffix = row_index
        while value in used:
            if column_type in {"INTEGER", "DECIMAL", "REAL"}:
                value += 1
            else:
                suffix += 1
                value = f"{base_value}_{suffix}"
    unique_values.add(value)
    return value


def _insert_generated_rows(
    connection: sqlite3.Connection,
    table_names: list[str],
    rows_per_table: int,
):
    generated_counts = {}
    parent_values: dict[str, list[dict[str, Any]]] = {}
    used_values: dict[str, set[Any]] = {}
    for table_name in _dependency_order(table_names, connection):
        column_rows = connection.execute(
            f"PRAGMA table_info({_quote_identifier(table_name)})"
        ).fetchall()
        columns = [dict(row) for row in column_rows]
        unique_columns = set()
        for index in connection.execute(
            f"PRAGMA index_list({_quote_identifier(table_name)})"
        ).fetchall():
            if index["unique"]:
                unique_columns.update(
                    info["name"]
                    for info in connection.execute(
                        f"PRAGMA index_info({_quote_identifier(index['name'])})"
                    ).fetchall()
                )
        for column in columns:
            column["unique"] = column["name"] in unique_columns
            if column["pk"] or column["unique"]:
                existing_values = connection.execute(
                    f"SELECT {_quote_identifier(column['name'])} "
                    f"FROM {_quote_identifier(table_name)}"
                ).fetchall()
                used_values.setdefault(
                    f"{table_name}.{column['name']}", set()
                ).update(row[0] for row in existing_values)
        generated = []
        for row_index in range(rows_per_table):
            values = {
                column["name"]: _generated_value(
                    column, table_name, row_index, parent_values, used_values, connection
                )
                for column in columns
            }
            names = list(values)
            connection.execute(
                f"INSERT INTO {_quote_identifier(table_name)} "
                f"({', '.join(_quote_identifier(name) for name in names)}) "
                f"VALUES ({', '.join('?' for _ in names)})",
                [values[name] for name in names],
            )
            generated.append(values)
        generated_counts[table_name] = len(generated)
        parent_values[table_name] = generated
    return generated_counts


def generate_sample_data(
    table_names: list[str] | str | None,
    rows_per_table: int = 10,
    manual_rows: dict[str, list[dict[str, Any]]] | None = None,
):
    selected = [table_names] if isinstance(table_names, str) else (table_names or list_tables())
    selected = list(dict.fromkeys(str(name) for name in selected))
    if not selected:
        raise ValueError("Select at least one table to generate sample data.")
    try:
        rows_per_table = int(rows_per_table)
    except (TypeError, ValueError) as error:
        raise ValueError("Rows per table must be an integer from 1 to 50.") from error
    if not 1 <= rows_per_table <= 50:
        raise ValueError("Rows per table must be between 1 and 50.")
    existing_tables = set(list_tables())
    missing = set(selected) - existing_tables
    if missing:
        raise ValueError(f"Table(s) do not exist: {', '.join(sorted(missing))}.")
    try:
        with _connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            generated = _insert_generated_rows(connection, selected, rows_per_table)
            connection.commit()
    except sqlite3.IntegrityError as error:
        raise _friendly_integrity_error(error) from error
    return {
        "generated": generated,
        "message": f"Sample rows generated for {sum(generated.values())} records.",
    }


THEME_TABLES = {
    "university": ["Students", "Courses", "Enrollments", "Instructors", "Departments"],
    "e-commerce": ["Customers", "Products", "Orders", "OrderItems", "Categories"],
    "library": ["Members", "Books", "Loans", "Authors", "Publishers"],
    "company": ["Employees", "Departments", "Projects", "Assignments", "Clients"],
    "hospital": ["Patients", "Doctors", "Appointments", "Departments", "Treatments"],
    "random": ["Records", "Details", "Entries", "Events", "Catalog"],
}

THEME_LABEL_COLUMNS = {
    "university": ["name", "title", "status", "department"],
    "e-commerce": ["name", "sku", "status", "category"],
    "library": ["title", "isbn", "status", "author"],
    "company": ["name", "code", "status", "department"],
    "hospital": ["name", "code", "status", "department"],
    "random": ["name", "code", "status", "category"],
}


def preview_random_schema(
    theme: str = "random",
    table_count: int = 4,
    columns_per_table: int = 5,
    relationships: bool = True,
    mode: str = "add",
):
    theme = str(theme).lower().strip()
    if theme not in THEME_TABLES:
        raise ValueError(f"Choose a supported schema theme: {', '.join(THEME_TABLES)}.")
    try:
        table_count = int(table_count)
        columns_per_table = int(columns_per_table)
    except (TypeError, ValueError) as error:
        raise ValueError("Table and column counts must be integers.") from error
    if not 1 <= table_count <= 10:
        raise ValueError("Choose between 1 and 10 tables.")
    if not 2 <= columns_per_table <= 12:
        raise ValueError("Choose between 2 and 12 columns per table.")
    if mode not in {"add", "replace"}:
        raise ValueError("Choose whether to add to or replace the current workspace.")

    table_names = THEME_TABLES[theme]
    names = [
        table_names[index] if index < len(table_names) else f"{table_names[-1]}{index + 1}"
        for index in range(table_count)
    ]
    existing = {name.lower() for name in list_tables()} if mode == "add" else set()
    allocated: set[str] = set()
    actual_names = []
    renamed = {}
    for name in names:
        candidate = name
        suffix = 2
        while candidate.lower() in existing or candidate.lower() in allocated:
            candidate = f"{name}_{suffix}"
            suffix += 1
        if candidate != name:
            renamed[name] = candidate
        allocated.add(candidate.lower())
        actual_names.append(candidate)

    table_definitions = []
    label_columns = THEME_LABEL_COLUMNS[theme]
    for index, name in enumerate(actual_names):
        columns = [
            {
                "name": "id",
                "type": "INTEGER",
                "primary_key": True,
                "not_null": True,
                "unique": False,
                "references": None,
            }
        ]
        if relationships and index > 0:
            parent = actual_names[index - 1]
            columns.append({
                "name": f"{parent.rstrip('s').lower()}_id",
                "type": "INTEGER",
                "primary_key": False,
                "not_null": True,
                "unique": False,
                "references": f"{parent}.id",
            })
        remaining = columns_per_table - len(columns)
        for column_index in range(remaining):
            label = label_columns[column_index % len(label_columns)]
            if column_index == 0:
                column_name = label
                column_type = "VARCHAR"
                unique = label in {"email", "sku", "isbn", "code"}
            elif column_index == 1:
                column_name, column_type, unique = "created_date", "DATE", False
            elif column_index == 2:
                column_name, column_type, unique = "active", "BOOLEAN", False
            elif column_index == 3:
                column_name, column_type, unique = "score", "DECIMAL", False
            else:
                column_name = f"attribute_{column_index + 1}"
                column_type, unique = "TEXT", False
            if any(column["name"] == column_name for column in columns):
                column_name = f"{column_name}_{column_index + 1}"
            columns.append({
                "name": column_name,
                "type": column_type,
                "primary_key": False,
                "not_null": True,
                "unique": unique,
                "references": None,
            })
        table_definitions.append({"name": name, "columns": columns})

    return {
        "theme": theme,
        "tables": table_definitions,
        "renamed_conflicts": renamed,
        "mode": mode,
        "relationships": bool(relationships),
    }


def create_random_schema(
    tables: list[dict[str, Any]],
    mode: str = "add",
    confirm_replace: bool = False,
    rows_per_table: int = 0,
    generate_samples: bool = False,
):
    if mode not in {"add", "replace"}:
        raise ValueError("Choose whether to add to or replace the current workspace.")
    if mode == "replace" and confirm_replace is not True:
        raise ValueError(
            "Replacing the workspace requires explicit confirmation. Existing tables and records were not changed."
        )
    if not isinstance(tables, list) or not tables:
        raise ValueError("The random schema preview must include at least one table.")
    try:
        rows_per_table = int(rows_per_table or 0)
    except (TypeError, ValueError) as error:
        raise ValueError("Sample rows per table must be an integer from 1 to 50.") from error
    if generate_samples and not 1 <= rows_per_table <= 50:
        raise ValueError("Sample rows per table must be between 1 and 50.")

    definitions = []
    seen_names: set[str] = set()
    for raw in tables:
        if not isinstance(raw, dict):
            raise ValueError("Each proposed table must be an object.")
        name = _validate_table_name(raw.get("name", ""))
        if name.lower() in seen_names:
            raise ValueError(f"Duplicate proposed table name '{name}'.")
        seen_names.add(name.lower())
        columns = _normalize_columns(raw.get("columns", []))
        if not columns:
            raise ValueError(f"Table '{name}' must have at least one column.")
        definitions.append({"name": name, "columns": columns})

    generated_names = {item["name"] for item in definitions}
    existing_names = set(list_tables())
    conflicts = {
        name for name in generated_names
        if name.lower() in {existing.lower() for existing in existing_names}
    }
    if mode == "add" and conflicts:
        raise ValueError(
            f"Table name conflict(s): {', '.join(sorted(conflicts))}. Preview again to assign unique names."
        )
    generated_schema = {
        item["name"]: {column["name"]: column["type"] for column in item["columns"]}
        for item in definitions
    }
    for table in definitions:
        for column in table["columns"]:
            if not column["references"]:
                continue
            parent_table, parent_column = column["references"].split(".", 1)
            parent_columns = generated_schema.get(parent_table)
            if parent_columns is None:
                if parent_table in existing_names:
                    parent_columns = {
                        row["name"]: _normalize_type(row["type"])
                        for row in _table_info(parent_table)
                    }
                else:
                    raise ValueError(
                        f"Foreign key target table '{parent_table}' is not part of this schema or workspace."
                    )
            if parent_column not in parent_columns:
                raise ValueError(f"Foreign key target column '{parent_table}.{parent_column}' does not exist.")
            if not _foreign_key_types_compatible(parent_columns[parent_column], column["type"]):
                raise ValueError(
                    f"Foreign key column '{column['name']}' must use the same data type as "
                    f"'{parent_table}.{parent_column}'."
                )

    connection = _connect()
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        if mode == "replace":
            current_tables = [
                row["name"] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT GLOB 'sqlite_*' AND name NOT GLOB '__workspace_*'"
                )
            ]
            for name in current_tables:
                connection.execute(f"DROP TABLE {_quote_identifier(name)}")
        current_names = {
            row["name"].lower() for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT GLOB 'sqlite_*' AND name NOT GLOB '__workspace_*'"
            )
        }
        if any(table["name"].lower() in current_names for table in definitions):
            raise ValueError("A proposed table name now conflicts with the workspace. Preview the schema again.")
        for table in definitions:
            connection.execute(_build_create_table_sql(table["name"], table["columns"]))

        generated_counts = {}
        if generate_samples:
            generated_counts = _insert_generated_rows(
                connection, [item["name"] for item in definitions], rows_per_table
            )
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError("The proposed schema or sample data contains an invalid foreign-key relationship.")
        connection.commit()
    except sqlite3.IntegrityError as error:
        connection.rollback()
        raise _friendly_integrity_error(error) from error
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.close()

    return {
        "tables": [item["name"] for item in definitions],
        "generated": generated_counts,
        "message": (
            f"Created {len(definitions)} table(s)"
            + (f" and {sum(generated_counts.values())} sample record(s)." if generate_samples else ".")
        ),
    }


def execute_select_query(query: str, limit: int = 200):
    normalized = (query or "").strip()
    if not normalized:
        raise ValueError("A SQL SELECT statement is required.")
    if len(normalized) > 16_384:
        raise ValueError("Query is too long for playground execution (maximum 16 KB).")
    tokens = tokenize(normalized)
    semicolons = [
        index for index, token in enumerate(tokens)
        if token.type == ";"
    ]
    if len(semicolons) > 1 or (
        semicolons and any(token.type != "EOF" for token in tokens[semicolons[0] + 1:])
    ):
        raise ValueError("Only a single SQL statement is allowed in the playground.")
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    if not normalized.upper().startswith("SELECT"):
        raise ValueError("The playground execution mode only supports SELECT statements.")
    max_rows = min(max(int(limit), 1), 200)
    deadline = time.monotonic() + 2.0
    with _connect(read_only=True) as conn:
        conn.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0,
            10_000,
        )
        try:
            cursor = conn.execute(normalized)
            columns = [description[0] for description in cursor.description or []]
            rows = cursor.fetchmany(max_rows + 1)
        except sqlite3.OperationalError as error:
            if "interrupted" in str(error).lower():
                raise ValueError("Query exceeded the 2-second execution limit.") from error
            raise ValueError(f"SQLite could not execute the query: {error}") from error
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return {
        "columns": columns,
        "rows": [dict(row) for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "row_limit": max_rows,
    }
