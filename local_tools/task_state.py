"""Persist Continue task checkpoints and tool results in a local SQLite file."""
import json
import sqlite3
from contextlib import closing
from uuid import uuid4


class TaskStore:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, requirements TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS steps (
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    number INTEGER NOT NULL, description TEXT NOT NULL, note TEXT,
                    PRIMARY KEY(task_id, number)
                );
                CREATE TABLE IF NOT EXISTS tool_results (
                    task_id TEXT NOT NULL REFERENCES tasks(id), summary TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS results_by_task ON tool_results(task_id);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def create(self, requirements, steps):
        if not requirements.strip() or len(requirements) > 4000:
            raise ValueError("Requirements must contain 1–4000 characters.")
        if not 1 <= len(steps) <= 20 or any(not step.strip() or len(step) > 240 for step in steps):
            raise ValueError("Provide 1–20 steps of up to 240 characters each.")
        task_id = uuid4().hex
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO tasks VALUES (?, ?)", (task_id, requirements))
            db.executemany("INSERT INTO steps VALUES (?, ?, ?, NULL)",
                           ((task_id, number, text) for number, text in enumerate(steps, 1)))
        return self.get(task_id)

    def get(self, task_id):
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            task = db.execute("SELECT requirements FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if task is None:
                raise LookupError("Unknown task ID. Use resume_task without an ID to list recent tasks.")
            steps = [{"number": number, "description": description,
                      "status": "completed" if note is not None else "pending", "note": note}
                     for number, description, note in db.execute(
                         "SELECT number, description, note FROM steps WHERE task_id = ? ORDER BY number",
                         (task_id,))]
            count = db.execute("SELECT count(*) FROM tool_results WHERE task_id = ?", (task_id,)).fetchone()[0]
            results = [json.loads(row[0]) for row in db.execute(
                "SELECT summary FROM tool_results WHERE task_id = ? ORDER BY rowid DESC LIMIT 6", (task_id,))]
        next_step = next((step["number"] for step in steps if step["status"] == "pending"), None)
        return {"task_id": task_id, "requirements": task[0], "steps": steps,
                "status": "active" if next_step is not None else "completed", "next_step": next_step,
                "tool_result_count": count, "recent_tool_results": results}

    def recent(self):
        with closing(self.connect()) as db:
            rows = db.execute("""
                SELECT t.id, substr(t.requirements, 1, 120), count(s.number), count(s.note)
                FROM tasks t JOIN steps s ON t.id = s.task_id
                GROUP BY t.id ORDER BY t.rowid DESC LIMIT 10
            """)
            return [{"task_id": task_id, "requirements_preview": preview,
                     "completed_steps": done, "total_steps": total,
                     "status": "completed" if done == total else "active"}
                    for task_id, preview, total, done in rows]

    def complete(self, task_id, step_number, note=""):
        if len(note) > 1000:
            raise ValueError("Completion note must be at most 1000 characters.")
        with closing(self.connect()) as db, db:
            updated = db.execute(
                "UPDATE steps SET note = COALESCE(note, ?) WHERE task_id = ? AND number = ?",
                (note, task_id, step_number))
            if not updated.rowcount:
                if db.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
                    raise LookupError("Unknown task ID.")
                raise ValueError("Step number is outside this task's plan.")
        return self.get(task_id)

    def record_delivery(self, task_id, filename, result):
        summary = {"tool": "generate_html_file", "filename": filename,
                   **{key: result[key] for key in ("status", "path", "finish_reason") if key in result}}
        if isinstance(result.get("message"), str):
            summary["message"] = result["message"][:500]
        with closing(self.connect()) as db, db:
            inserted = db.execute("""
                INSERT INTO tool_results (task_id, summary)
                SELECT id, ? FROM tasks WHERE id = ?
            """, (json.dumps(summary, ensure_ascii=False), task_id))
            if not inserted.rowcount:
                raise LookupError("Unknown task ID.")
