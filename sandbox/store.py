"""SQLite access of the sandbox (target-side code, deliberately separate from modules/common/database.py)."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def item_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "sku": row["sku"],
        "name": row["name"],
        "description": row["description"],
        "quantity": row["quantity"],
        "state": row["state"],
    }


def find_user(conn: sqlite3.Connection, username: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def create_session(conn: sqlite3.Connection, token: str, user_id: int) -> None:
    conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
    conn.commit()


def user_for_token(conn: sqlite3.Connection, token: Optional[str]) -> Optional[sqlite3.Row]:
    if not token:
        return None
    return conn.execute(
        "SELECT users.id AS id, users.username AS username, users.role AS role "
        "FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = ?",
        (token,),
    ).fetchone()


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


def set_flash(conn: sqlite3.Connection, token: str, message: str) -> None:
    conn.execute("UPDATE sessions SET flash = ? WHERE token = ?", (message, token))
    conn.commit()


def pop_flash(conn: sqlite3.Connection, token: str) -> Optional[str]:
    row = conn.execute("SELECT flash FROM sessions WHERE token = ?", (token,)).fetchone()
    if row is None or row["flash"] is None:
        return None
    conn.execute("UPDATE sessions SET flash = NULL WHERE token = ?", (token,))
    conn.commit()
    return str(row["flash"])


def list_items(conn: sqlite3.Connection, include_drafts: bool, query: Optional[str]) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM catalog_items WHERE 1 = 1"
    params: List[Any] = []
    if not include_drafts:
        sql += " AND state = 'PUBLISHED'"
    if query is not None:
        like = "%" + query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (lower(sku) LIKE ? ESCAPE '\\' OR lower(name) LIKE ? ESCAPE '\\')"
        params += [like, like]
    sql += " ORDER BY sku ASC"
    return [item_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def get_item(conn: sqlite3.Connection, sku: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM catalog_items WHERE sku = ?", (sku,)).fetchone()
    return item_to_dict(row) if row else None


def insert_draft(conn: sqlite3.Connection, values: Dict[str, Any]) -> None:
    """Insert a DRAFT. A duplicate SKU raises sqlite3.IntegrityError (uniqueness is database-enforced)."""
    conn.execute(
        "INSERT INTO catalog_items (sku, name, description, quantity, state) VALUES (?, ?, ?, ?, 'DRAFT')",
        (values["sku"], values["name"], values["description"], values["quantity"]),
    )
    conn.commit()


def update_item(conn: sqlite3.Connection, sku: str, values: Dict[str, Any]) -> int:
    columns = [c for c in ("name", "description", "quantity") if c in values]
    assignments = ", ".join("%s = ?" % c for c in columns)  # column names come from a fixed whitelist
    cur = conn.execute(
        "UPDATE catalog_items SET %s WHERE sku = ? AND state = 'DRAFT'" % assignments,
        [values[c] for c in columns] + [sku],
    )
    conn.commit()
    return cur.rowcount


def publish_item(conn: sqlite3.Connection, sku: str) -> int:
    cur = conn.execute("UPDATE catalog_items SET state = 'PUBLISHED' WHERE sku = ? AND state = 'DRAFT'", (sku,))
    conn.commit()
    return cur.rowcount
