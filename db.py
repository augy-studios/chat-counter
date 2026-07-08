import os
import re

from sqlcipher3 import dbapi2 as sqlite3

from config import DB_ENCRYPTION_KEY

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'db')
os.makedirs(DB_DIR, exist_ok=True)
DB_FILE = os.path.join(DB_DIR, 'chatcounter.db')

_HEX_KEY_RE = re.compile(r'^[0-9a-fA-F]{64}$')


def get_connection():
    if not DB_ENCRYPTION_KEY:
        raise RuntimeError("DB_ENCRYPTION_KEY is not set in token.env")
    if not _HEX_KEY_RE.match(DB_ENCRYPTION_KEY):
        raise RuntimeError("DB_ENCRYPTION_KEY must be a 64-character hex string (32 bytes)")
    conn = sqlite3.connect(DB_FILE)
    # DB_ENCRYPTION_KEY is a 64-char hex string (32 bytes); pass it as a raw key
    # via SQLCipher's x'...' syntax so it's used directly instead of being run
    # through PBKDF2 as a passphrase.
    conn.execute(f"PRAGMA key = \"x'{DB_ENCRYPTION_KEY}'\"")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            messages INTEGER NOT NULL DEFAULT 0,
            words INTEGER NOT NULL DEFAULT 0,
            characters INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, guild_id)
        );
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            word TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            is_dict INTEGER NOT NULL DEFAULT 0,
            UNIQUE(guild_id, word)
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            datetime_now TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS known_users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def load_stats():
    """Returns {(user_id, guild_id): rec} to seed the in-memory stats cache."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM messages").fetchall()
    conn.close()
    return {
        (row["user_id"], row["guild_id"]): {
            "id": row["id"],
            "entry_id": row["entry_id"],
            "user_id": row["user_id"],
            "guild_id": row["guild_id"],
            "messages": row["messages"],
            "words": row["words"],
            "characters": row["characters"],
        }
        for row in rows
    }


def load_words():
    """Returns {(guild_id, word): rec} to seed the in-memory words_stats cache."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM words").fetchall()
    conn.close()
    return {
        (row["guild_id"], row["word"]): {
            "id": row["id"],
            "word_id": row["word_id"],
            "guild_id": row["guild_id"],
            "word": row["word"],
            "count": row["count"],
            "is_dict": bool(row["is_dict"]),
        }
        for row in rows
    }


def record_message(message_rec, word_recs):
    """Persists one message's updated stats plus any changed word counts in a single transaction."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO messages (entry_id, user_id, guild_id, messages, words, characters)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, guild_id) DO UPDATE SET
            messages=excluded.messages,
            words=excluded.words,
            characters=excluded.characters
        """,
        (
            message_rec["entry_id"], message_rec["user_id"], message_rec["guild_id"],
            message_rec["messages"], message_rec["words"], message_rec["characters"],
        ),
    )
    row = conn.execute(
        "SELECT id FROM messages WHERE user_id = ? AND guild_id = ?",
        (message_rec["user_id"], message_rec["guild_id"]),
    ).fetchone()
    message_rec["id"] = row["id"]

    for w in word_recs:
        conn.execute(
            """
            INSERT INTO words (word_id, guild_id, word, count, is_dict)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, word) DO UPDATE SET
                count=excluded.count,
                is_dict=excluded.is_dict
            """,
            (w["word_id"], w["guild_id"], w["word"], w["count"], int(w["is_dict"])),
        )
        row = conn.execute(
            "SELECT id FROM words WHERE guild_id = ? AND word = ?",
            (w["guild_id"], w["word"]),
        ).fetchone()
        w["id"] = row["id"]

    conn.commit()
    conn.close()


def delete_user_stats(user_id):
    """Deletes a user's per-guild message/word/character counts. Returns the number of rows removed.

    Word-usage stats are aggregated per guild only (not attributable to a single user),
    so they are unaffected by this call.
    """
    conn = get_connection()
    cur = conn.execute("DELETE FROM messages WHERE user_id = ?", (str(user_id),))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted


def get_session_ids():
    conn = get_connection()
    rows = conn.execute("SELECT session_id FROM sessions").fetchall()
    conn.close()
    return {row["session_id"] for row in rows}


def add_session(session_id, datetime_now):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO sessions (session_id, datetime_now) VALUES (?, ?)",
        (session_id, datetime_now),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_all_sessions():
    conn = get_connection()
    rows = conn.execute("SELECT id, session_id, datetime_now FROM sessions ORDER BY id").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def upsert_known_user(user_id, username):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO known_users (user_id, username) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username
        """,
        (str(user_id), username),
    )
    conn.commit()
    conn.close()


def get_known_users():
    conn = get_connection()
    rows = conn.execute("SELECT user_id, username FROM known_users ORDER BY username").fetchall()
    conn.close()
    return [f"{row['username']} ({row['user_id']})" for row in rows]
