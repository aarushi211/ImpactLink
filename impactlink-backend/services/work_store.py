import os
import uuid
import json
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL environment variable is required.")

# Reusing connection pool pattern from session.py for consistent connection management
pool = ConnectionPool(
    conninfo=DB_URL,
    min_size=1,
    max_size=10,
    check=ConnectionPool.check_connection,
    kwargs={"autocommit": True, "prepare_threshold": None}  # None = disable prepared statements (required for PgBouncer/Supabase)
)

def _init_db():
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_work (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    work_type TEXT NOT NULL,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_work ON user_work (user_id, work_type);")

_init_db()

def list_work(user_id: str, work_type: str):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, data FROM user_work WHERE user_id = %s AND work_type = %s ORDER BY updated_at DESC", 
                (user_id, work_type)
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                item = r["data"]
                item["id"] = r["id"]
                results.append(item)
            return results

def save_work(user_id: str, work_type: str, data: dict):
    work_id = data.get("id") or str(uuid.uuid4())
    data["id"] = work_id
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_work (id, user_id, work_type, data, updated_at) 
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (work_id, user_id, work_type, json.dumps(data)))
    return data

def update_work(user_id: str, work_id: str, updates: dict):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT data FROM user_work WHERE id = %s AND user_id = %s", (work_id, user_id))
            row = cur.fetchone()
            if not row:
                raise ValueError("Not found")
            data = row["data"]
            data.update(updates)
            cur.execute("UPDATE user_work SET data = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (json.dumps(data), work_id))
            return data

def delete_work(user_id: str, work_id: str):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_work WHERE id = %s AND user_id = %s", (work_id, user_id))
