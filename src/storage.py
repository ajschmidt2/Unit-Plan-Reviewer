import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import json

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

def get_project_review_history(project_name: str, limit: int = 10) -> List[Dict]:
    """Get review history for a project"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            SELECT id, created_at, ruleset, scale_note, result_json
            FROM reviews
            WHERE project_name = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_name, limit)
        )
        rows = cursor.fetchall()
        
        history = []
        for row in rows:
            payload = json.loads(row[4])
            if isinstance(payload, dict) and "review" in payload:
                review_payload = payload.get("review", {})
            else:
                review_payload = payload
            history.append(
                {
                    "id": row[0],
                    "created_at": row[1],
                    "ruleset": row[2],
                    "scale_note": row[3],
                    "result": {"review": review_payload},
                }
            )
        return history

def compare_reviews(old_review: Dict, new_review: Dict) -> Dict:
    """Compare two reviews and identify changes"""
    
    def extract_issue_signatures(result):
        """Create signatures for issues to track them across reviews"""
        signatures = set()
        for page in result.get("pages", []):
            for issue in page.get("issues", []):
                # Create a simple signature based on location and finding keywords
                sig = f"{page['page_index']}:{issue['location_hint']}:{issue['severity']}"
                signatures.add(sig)
        return signatures
    
    old_sigs = extract_issue_signatures(old_review)
    new_sigs = extract_issue_signatures(new_review)
    
    resolved = old_sigs - new_sigs
    new_issues = new_sigs - old_sigs
    persistent = old_sigs & new_sigs
    
    old_total = sum(len(p.get("issues", [])) for p in old_review.get("pages", []))
    new_total = sum(len(p.get("issues", [])) for p in new_review.get("pages", []))
    
    return {
        "old_issue_count": old_total,
        "new_issue_count": new_total,
        "resolved_count": len(resolved),
        "new_issues_count": len(new_issues),
        "persistent_count": len(persistent),
        "improvement_percentage": ((old_total - new_total) / old_total * 100) if old_total > 0 else 0,
        "resolved_signatures": list(resolved),
        "new_issue_signatures": list(new_issues),
    }
