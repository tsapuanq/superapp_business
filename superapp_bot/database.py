import json
import threading
import time
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from config import DATABASE_URL, USERS_FILE
from state import user_state

# ─── Connection pool ──────────────────────────────────────────────────────────
# ThreadedConnectionPool is safe to use across multiple threads (Gunicorn --threads)

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(2, 10, DATABASE_URL)
    return _pool


@contextmanager
def get_db():
    """Thread-safe connection from pool. Auto-commits or rolls back."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ─── Dirty context (flushed to DB periodically) ───────────────────────────────

_context_lock = threading.Lock()
_dirty_context: dict[str, dict] = {}
_last_context_flush: float = 0
CONTEXT_FLUSH_INTERVAL = 60

# ─── Users cache ──────────────────────────────────────────────────────────────

_users_cache: dict | None = None
_users_loaded_at: float = 0
USERS_TTL = 30


# ─── Schema & migration ───────────────────────────────────────────────────────

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id      BIGINT PRIMARY KEY,
                    username     TEXT    DEFAULT '',
                    profile      TEXT    DEFAULT '{}',
                    feedback     TEXT    DEFAULT '{}',
                    last_context TEXT,
                    push_history TEXT    DEFAULT '[]'
                )
            """)


def migrate_json():
    """One-time migration from users.json → PostgreSQL (skipped if rows already exist)."""
    if not USERS_FILE.exists():
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM users")
            if cur.fetchone()[0] > 0:
                return
        try:
            data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
            with conn.cursor() as cur:
                for uid, entry in data.items():
                    cur.execute("""
                        INSERT INTO users (user_id, username, profile, feedback, last_context, push_history)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id) DO NOTHING
                    """, (
                        int(uid),
                        entry.get("username", ""),
                        json.dumps(entry.get("profile", {}), ensure_ascii=False),
                        json.dumps(entry.get("feedback", {}), ensure_ascii=False),
                        json.dumps(entry["last_context"], ensure_ascii=False) if entry.get("last_context") else None,
                        json.dumps(entry.get("push_history", []), ensure_ascii=False),
                    ))
            print(f"[DB] Migrated {len(data)} users from JSON")
        except Exception as e:
            print(f"[DB] Migration error: {e}")
            raise


# ─── Cache helpers ────────────────────────────────────────────────────────────

def _invalidate_cache():
    global _users_loaded_at
    _users_loaded_at = 0


# ─── User CRUD ────────────────────────────────────────────────────────────────

def load_users() -> dict:
    global _users_cache, _users_loaded_at
    if _users_cache is None or (time.time() - _users_loaded_at) > USERS_TTL:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT user_id, username, profile, feedback, last_context, push_history FROM users"
                )
                rows = cur.fetchall()
        _users_cache = {}
        for row in rows:
            _users_cache[str(row["user_id"])] = {
                "username":     row["username"],
                "profile":      json.loads(row["profile"] or "{}"),
                "feedback":     json.loads(row["feedback"] or "{}"),
                "last_context": json.loads(row["last_context"]) if row["last_context"] else None,
                "push_history": json.loads(row["push_history"] or "[]"),
            }
        _users_loaded_at = time.time()
    return _users_cache


def save_user(user_id: int, username: str, answers: dict):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, username, profile, feedback, push_history)
                VALUES (%s, %s, %s, '{}', '[]')
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    profile  = EXCLUDED.profile
            """, (user_id, username, json.dumps(answers, ensure_ascii=False)))
    _invalidate_cache()


def delete_user(user_id: int):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
    _invalidate_cache()


def record_feedback(user_id: int, liked: bool):
    from datalake import target_categories  # local import avoids circular dependency
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT profile, feedback FROM users WHERE user_id=%s", (user_id,))
            row = cur.fetchone()
        if not row:
            return

        profile = json.loads(row["profile"] or "{}")
        fb = json.loads(row["feedback"] or "{}")

        top_cat = user_state.get(user_id, {}).get("last_top_cat")
        if not top_cat:
            cats = target_categories(profile)
            top_cat = cats[0] if cats else "FINANCE"

        if top_cat not in fb:
            fb[top_cat] = {"likes": 0, "dislikes": 0}
        if liked:
            fb[top_cat]["likes"] += 1
        else:
            fb[top_cat]["dislikes"] += 1

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET feedback=%s WHERE user_id=%s",
                (json.dumps(fb, ensure_ascii=False), user_id)
            )
    _invalidate_cache()


def flush_context_if_needed(force: bool = False):
    global _last_context_flush
    with _context_lock:
        if not _dirty_context:
            return
        if not force and (time.time() - _last_context_flush) < CONTEXT_FLUSH_INTERVAL:
            return
        ctx_snapshot = _dirty_context.copy()
        _dirty_context.clear()
        _last_context_flush = time.time()

    with get_db() as conn:
        with conn.cursor() as cur:
            for uid, ctx in ctx_snapshot.items():
                cur.execute(
                    "UPDATE users SET last_context=%s WHERE user_id=%s",
                    (json.dumps(ctx, ensure_ascii=False), int(uid))
                )


def category_boost(user_id: int, users: dict | None = None) -> dict[str, float]:
    if users is not None:
        fb = users.get(str(user_id), {}).get("feedback", {})
    else:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT feedback FROM users WHERE user_id=%s", (user_id,))
                row = cur.fetchone()
        fb = json.loads(row["feedback"] or "{}") if row else {}

    boosts = {}
    for cat, counts in fb.items():
        likes = counts.get("likes", 0)
        dislikes = counts.get("dislikes", 0)
        total = likes + dislikes
        if total == 0:
            continue
        ratio = (likes - dislikes) / total
        boosts[cat] = 1.0 + 0.5 * ratio
    return boosts


def get_user_count() -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            return cur.fetchone()[0]


def update_push_history(user_id: int, new_history: list):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET push_history=%s WHERE user_id=%s",
                (json.dumps(new_history, ensure_ascii=False), user_id)
            )
