import sqlite3
from datetime import datetime

DB_PATH = "reviews.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            project_name TEXT,
            ruleset TEXT,
            scale_note TEXT,
            result_json TEXT
        )
        """)
        conn.commit()

def save_review(project_name, ruleset, scale_note, result_json):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO reviews (created_at, project_name, ruleset, scale_note, result_json) VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), project_name, ruleset, scale_note, result_json),
        )
        conn.commit()
        return cur.lastrowid
