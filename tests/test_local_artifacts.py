import json
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from local_tools.artifacts import deliver, generate_html, read_chat_stream


def stream(*messages, finish="stop"):
    for message in messages:
        yield json.dumps({"done": False, "message": message}).encode("utf-8")
    if finish is not None:
        yield json.dumps({"done": True, "done_reason": finish, "eval_count": 42}).encode("utf-8")


class StreamTests(unittest.TestCase):
    def test_configured_local_backend_uses_compatible_stream(self):
        response = io.BytesIO(b"\n".join(stream({"content": "<html>ok</html>"})))
        opener = Mock()
        opener.open.return_value = response
        with patch.dict(os.environ, {"LOCAL_ARTIFACT_API_BASE": "http://127.0.0.1:13305/",
                                     "LOCAL_ARTIFACT_MODEL": "qwen3.5-9b-FLM"}):
            with patch("urllib.request.build_opener", return_value=opener):
                result = generate_html("Make HTML")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:13305/api/chat")
        self.assertEqual(json.loads(request.data)["model"], "qwen3.5-9b-FLM")
        self.assertEqual(result["done_reason"], "stop")

    def test_repeated_numbers_abort_before_reading_more(self):
        def chunks():
            for index in range(500):
                if index == 200:
                    self.fail("Still reading after sustained repetition")
                yield from stream({"content": ("10", " ")[index % 2]}, finish=None)

        result = read_chat_stream(chunks())
        self.assertEqual(result["done_reason"], "degeneration")
        self.assertEqual(result["channel"], "content")
        self.assertNotIn("eval_count", result)

    def test_reasoning_repetition_has_its_own_channel(self):
        result = read_chat_stream(stream({"thinking": "now " * 40}))
        self.assertEqual(result["done_reason"], "degeneration")
        self.assertEqual(result["channel"], "thinking")

    def test_short_phrases_rotate_across_chunks(self):
        loop = ("Let me write it. Go. Now. OK. "
                "Now! Go. Let me write it. OK. ") * 5
        messages = [{"thinking": loop[i:i + 5]} for i in range(0, len(loop), 5)]
        result = read_chat_stream(stream(*messages))
        self.assertEqual(result["done_reason"], "degeneration")
        self.assertEqual(result["pattern"], "sentence_rotation")
        self.assertEqual(result["distinct_sentences"], 4)

    def test_chinese_rotation_is_detected_in_plain_content(self):
        loop = "开始写。继续。马上。好了。" * 7
        result = read_chat_stream(stream({"content": loop}))
        self.assertEqual(result["done_reason"], "degeneration")
        self.assertEqual(result["channel"], "content")

    def test_repeated_svg_labels_are_not_prose_rotation(self):
        svg = "<svg><text>" + "Go. Now. OK. Ready. " * 7 + "</text></svg>"
        result = read_chat_stream(stream(*({"content": ch} for ch in svg)))
        self.assertEqual(result["done_reason"], "stop")
        self.assertEqual(result["message"]["content"], svg)

    def test_short_sentences_with_new_information_are_not_rotation(self):
        text = " ".join(f"Inspect group {letter}." for letter in "abcdefghijklmnopqrstuvwxyz")
        result = read_chat_stream(stream({"thinking": text}))
        self.assertEqual(result["done_reason"], "stop")

    def test_normal_svg_and_separate_channels_survive(self):
        svg = '<svg><path d="M 0 0 L 10 10 L 20 20"/>' + '<circle cx="10" cy="10" r="3"/>' * 40 + '</svg>'
        messages = [{"thinking": "10 " * 20}, {"content": "10 " * 20}]
        messages.extend({"content": svg[i:i + 7]} for i in range(0, len(svg), 7))
        result = read_chat_stream(stream(*messages))
        self.assertEqual(result["message"]["content"], "10 " * 20 + svg)
        self.assertEqual(result["done_reason"], "stop")
        self.assertEqual(result["eval_count"], 42)

    def test_end_without_final_event_is_incomplete(self):
        result = read_chat_stream(stream({"content": "<html>"}, finish=None))
        self.assertFalse(result["done"])


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name)
        self.generate = Mock(return_value={
            "done": True,
            "done_reason": "stop",
            "eval_count": 12,
            "message": {"content": "<html>ok</html>"},
        })

    def run_task(self, task="Make HTML", filename="page.html", references=None):
        return deliver(task, filename, self.output, self.generate, references=references)

    def test_short_task_preserves_output_reserve(self):
        result = self.run_task()
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["context"]["output_reserved"], 4096)
        self.assertLessEqual(result["context"]["estimated_input"], 4096)
        self.generate.assert_called_once_with("Make HTML")

    def test_large_reference_is_omitted_but_task_and_small_reference_survive(self):
        task = "画鹈鹕骑自行车，保留车轮和踏板。"
        result = self.run_task(task, references=["长资料" * 2000, "两个车轮等大。"])
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["context"]["included_references"], [2])
        self.assertEqual(result["context"]["omitted_references"], [1])
        prompt = self.generate.call_args.args[0]
        self.assertIn(task, prompt)
        self.assertIn("两个车轮等大。", prompt)
        self.assertNotIn("长资料", prompt)

    def test_oversized_task_is_rejected_before_generation(self):
        result = self.run_task("必须保留的要求。" * 1000)
        self.assertEqual(result["status"], "context_overflow")
        self.assertFalse((self.output / "page.html").exists())
        self.generate.assert_not_called()

    def test_reference_changes_do_not_reuse_a_different_task_result(self):
        self.assertEqual(self.run_task(references=["Draw a red wheel."])["status"], "saved")
        self.assertEqual(self.run_task(references=["Draw a blue wheel."])["status"], "conflict")
        self.generate.assert_called_once()

    def test_truncated_output_is_not_published(self):
        self.generate.return_value["done_reason"] = "length"
        result = self.run_task()
        self.assertEqual(result["status"], "truncated")
        self.assertEqual(result["generated_tokens"], 12)
        self.assertFalse((self.output / "page.html").exists())
        self.generate.assert_called_once()

    def test_degenerate_output_is_not_published(self):
        examples = {
            "exact_repetition": "10 " * 40,
            "sentence_rotation": "开始写。继续。马上。好了。" * 7,
        }
        for pattern, content in examples.items():
            with self.subTest(pattern=pattern):
                self.generate.reset_mock()
                self.generate.return_value = read_chat_stream(stream({"content": content}))
                result = self.run_task()
                self.assertEqual(result["status"], "degeneration")
                self.assertEqual(result["pattern"], pattern)
                self.assertEqual(result["channel"], "content")
                self.assertIsNone(result["generated_tokens"])
                self.assertFalse((self.output / "page.html").exists())
                self.assertEqual(self.generate.call_count, 2)
                self.assertEqual([a["finish_reason"] for a in result["attempts"]],
                                 ["degeneration", "degeneration"])

    def test_recovers_once_and_reuses_saved_file(self):
        partial = read_chat_stream(stream({"content": "10 " * 40}))
        final = self.generate.return_value

        def generate(task):
            if task == "Make HTML":
                return partial
            self.assertIn("Make HTML", task)
            self.assertFalse((self.output / "page.html").exists())
            return final

        self.generate.side_effect = generate
        result = self.run_task()
        self.assertEqual(result["status"], "saved")
        self.assertEqual([a["finish_reason"] for a in result["attempts"]], ["degeneration", "stop"])
        self.assertEqual(Path(result["path"]).read_text(), "<html>ok</html>")
        self.assertEqual(self.run_task()["status"], "reused")
        self.assertEqual(self.generate.call_count, 2)

    def test_failure_on_second_attempt_keeps_both_records(self):
        partial = read_chat_stream(stream({"content": "10 " * 40}))
        self.generate.side_effect = [partial, TimeoutError("backend timeout")]
        result = self.run_task()
        self.assertEqual(result["status"], "backend_error")
        self.assertEqual([a["finish_reason"] for a in result["attempts"]],
                         ["degeneration", "backend_error"])
        self.assertFalse((self.output / "page.html").exists())

    def test_identical_request_reuses_existing_file(self):
        first = self.run_task()
        self.assertEqual(first["status"], "saved")
        self.assertEqual(Path(first["path"]).read_text(), "<html>ok</html>")
        self.assertEqual(self.run_task()["status"], "reused")
        self.generate.assert_called_once()

    def test_conflict_preserves_original(self):
        self.assertEqual(self.run_task()["status"], "saved")
        self.assertEqual(self.run_task(task="Different")["status"], "conflict")
        path = self.output / "page.html"
        path.write_text("human edit")
        self.assertEqual(self.run_task()["status"], "conflict")
        self.assertEqual(path.read_text(), "human edit")
        self.generate.assert_called_once()

    def test_bad_filenames_do_not_call_model(self):
        for name in ("../escape.html", "sub/file.html", "CON.html", "page.json"):
            with self.subTest(name=name):
                self.assertEqual(self.run_task(filename=name)["status"], "invalid_input")
        self.generate.assert_not_called()

    def test_backend_failure_leaves_target_available_for_retry(self):
        self.generate.side_effect = TimeoutError("backend timeout")
        self.assertEqual(self.run_task()["status"], "backend_error")
        self.assertFalse((self.output / "page.html").exists())
        self.generate.side_effect = None
        self.assertEqual(self.run_task()["status"], "saved")
