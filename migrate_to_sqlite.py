"""One-off migration: import existing counter.csv/words.csv/sessions.csv/users.txt
data into the encrypted SQLite database used by db.py. Safe to re-run; existing
rows are upserted rather than duplicated. Does not delete the source files."""

import csv
import os
import re

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'db')

COUNTER_FILE = os.path.join(DB_DIR, 'counter.csv')
WORDS_FILE = os.path.join(DB_DIR, 'words.csv')
SESSION_FILE = os.path.join(BASE_DIR, 'sessions.csv')
USERS_FILE = os.path.join(BASE_DIR, 'users.txt')

USER_LINE_RE = re.compile(r'^(.*) \((\d+)\)$')


def migrate_messages(conn):
    if not os.path.exists(COUNTER_FILE):
        print(f"Skipping messages: {COUNTER_FILE} not found.")
        return
    count = 0
    with open(COUNTER_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                conn.execute(
                    """
                    INSERT INTO messages (entry_id, user_id, guild_id, messages, words, characters)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET
                        messages=excluded.messages, words=excluded.words, characters=excluded.characters
                    """,
                    (row['entry_id'], row['user_id'], row['guild_id'],
                     int(row['messages']), int(row['words']), int(row['characters'])),
                )
                count += 1
            except (KeyError, ValueError):
                continue
    print(f"Migrated {count} message-stat rows from {COUNTER_FILE}")


def migrate_words(conn):
    if not os.path.exists(WORDS_FILE):
        print(f"Skipping words: {WORDS_FILE} not found.")
        return
    count = 0
    with open(WORDS_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                is_dict = row['is_dict'] in ('True', 'true', '1')
                conn.execute(
                    """
                    INSERT INTO words (word_id, guild_id, word, count, is_dict)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, word) DO UPDATE SET
                        count=excluded.count, is_dict=excluded.is_dict
                    """,
                    (row['word_id'], row['guild_id'], row['word'], int(row['count']), int(is_dict)),
                )
                count += 1
            except (KeyError, ValueError):
                continue
    print(f"Migrated {count} word-stat rows from {WORDS_FILE}")


def migrate_sessions(conn):
    if not os.path.exists(SESSION_FILE):
        print(f"Skipping sessions: {SESSION_FILE} not found.")
        return
    count = 0
    with open(SESSION_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions (session_id, datetime_now) VALUES (?, ?)",
                    (row['session_id'], row['datetime_now']),
                )
                count += 1
            except KeyError:
                continue
    print(f"Migrated {count} session rows from {SESSION_FILE}")


def migrate_known_users(conn):
    if not os.path.exists(USERS_FILE):
        print(f"Skipping known users: {USERS_FILE} not found.")
        return
    count = 0
    with open(USERS_FILE, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = USER_LINE_RE.match(line)
            if not match:
                continue
            username, user_id = match.group(1), match.group(2)
            conn.execute(
                """
                INSERT INTO known_users (user_id, username) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET username=excluded.username
                """,
                (user_id, username),
            )
            count += 1
    print(f"Migrated {count} known-user rows from {USERS_FILE}")


def main():
    db.init_db()
    conn = db.get_connection()
    try:
        migrate_messages(conn)
        migrate_words(conn)
        migrate_sessions(conn)
        migrate_known_users(conn)
        conn.commit()
    finally:
        conn.close()
    print(f"Done. Data is now stored in {db.DB_FILE}")
    print("Once you've verified the bot works correctly against the new database, "
          "you can remove the old counter.csv, words.csv, sessions.csv, and users.txt files.")


if __name__ == '__main__':
    main()
