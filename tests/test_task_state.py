import tempfile
import unittest
from pathlib import Path

from local_tools.task_state import TaskStore


class TaskStateTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "state.sqlite3"
        self.store = TaskStore(self.path)

    def test_resume_from_new_store_keeps_requirements_and_progress(self):
        state = self.store.create("Keep the pelican's long bill.", ["Draft SVG", "Deliver HTML"])
        task_id = state["task_id"]
        self.store.complete(task_id, 1, "SVG geometry drafted.")
        self.store.record_delivery(task_id, "pelican.html", {"status": "saved", "path": "pelican.html"})

        reopened = TaskStore(self.path)
        loaded = reopened.get(task_id)
        self.assertEqual(loaded["requirements"], "Keep the pelican's long bill.")
        self.assertEqual(loaded["steps"][0]["note"], "SVG geometry drafted.")
        self.assertEqual(loaded["next_step"], 2)
        self.assertEqual(loaded["recent_tool_results"][0]["status"], "saved")
        self.assertEqual(reopened.recent()[0]["task_id"], task_id)
        self.assertEqual(reopened.complete(task_id, 2)["status"], "completed")

    def test_repeated_completion_preserves_original_note(self):
        task_id = self.store.create("A task", ["Draft"])["task_id"]
        self.store.complete(task_id, 1, "Original note")
        updated = self.store.complete(task_id, 1, "Duplicate update")
        self.assertEqual(updated["steps"][0]["note"], "Original note")

    def test_invalid_progress_and_unknown_tasks_are_rejected(self):
        task_id = self.store.create("A task", ["Draft"])["task_id"]
        with self.assertRaises(ValueError):
            self.store.complete(task_id, 2)
        with self.assertRaises(LookupError):
            self.store.record_delivery("missing", "file.html", {"status": "saved"})
        self.assertEqual(self.store.get(task_id)["next_step"], 1)

    def test_failed_delivery_records_result_without_completing_step(self):
        task_id = self.store.create("A task", ["Deliver"])["task_id"]
        self.store.record_delivery(task_id, "file.html", {"status": "truncated", "finish_reason": "length"})
        state = self.store.get(task_id)
        self.assertEqual(state["next_step"], 1)
        self.assertEqual(state["recent_tool_results"][0]["finish_reason"], "length")
