import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from local_artifacts import generate_with_knowledge
from local_knowledge import search


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.knowledge = self.root / "knowledge"
        self.knowledge.mkdir()
        (self.knowledge / "pelican.md").write_text(
            "# Project rule\n\n鹈鹕动画 骑车页标题必须是 ZEPHYR-731。\n", encoding="utf-8"
        )
        (self.knowledge / "other.txt").write_text("仓库备份使用七日轮换。", encoding="utf-8")

    def test_chinese_query_returns_text_and_source_lines(self):
        matches = search(self.knowledge, "鹈鹕动画 骑车页标题")
        self.assertEqual(matches[0]["source"], "pelican.md")
        self.assertEqual((matches[0]["start_line"], matches[0]["end_line"]), (3, 3))
        self.assertIn("ZEPHYR-731", matches[0]["text"])

    def test_missing_match_does_not_fabricate_sources(self):
        self.assertEqual(search(self.knowledge, "数据库迁移"), [])
        generate = Mock()
        result = generate_with_knowledge("Use the project rule", "page.html", self.root / "output",
                                         self.knowledge, "数据库迁移", generate=generate)
        self.assertEqual(result["status"], "knowledge_no_match")
        generate.assert_not_called()

    def test_selected_passage_reaches_model_and_source_is_reported(self):
        generate = Mock(return_value={"done": True, "done_reason": "stop",
                                      "message": {"content": "<html>ZEPHYR-731</html>"}})
        result = generate_with_knowledge(
            "Create a page", "page.html", self.root / "output", self.knowledge,
            "鹈鹕动画 标题", references=["unrelated data " * 1000], generate=generate,
        )
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["context"]["omitted_references"], [1])
        self.assertEqual(result["knowledge_sources"][0]["source"], "pelican.md")
        self.assertTrue(result["knowledge_sources"][0]["included"])
        prompt = generate.call_args.args[0]
        self.assertIn("pelican.md:3-3", prompt)
        self.assertIn("ZEPHYR-731", prompt)
        self.assertNotIn("unrelated data", prompt)
