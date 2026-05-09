import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_mcp.metadata import FAQ, MagicFilter, MetaRecord, save_meta
from knowledge_mcp import metadata, reader
from knowledge_mcp import server


class TestMCPEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.knowledge_dir = self.tmp_path / "knowledge"
        self.meta_dir = self.knowledge_dir / ".knowledge_meta"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)

        self.file_one = self.knowledge_dir / "alpha.txt"
        self.file_one.write_text(
            "Alpha first line\n"
            "Second line about search token\n"
            "Third line\n",
            encoding="utf-8",
        )

        docs_dir = self.knowledge_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        self.file_two = docs_dir / "beta.md"
        self.file_two.write_text(
            "Beta intro\n"
            "Another line with token and context\n",
            encoding="utf-8",
        )

        self.patchers = [
            patch.object(reader, "KNOWLEDGE_DIR", self.knowledge_dir),
            patch.object(metadata, "KNOWLEDGE_DIR", self.knowledge_dir),
            patch.object(metadata, "KNOWLEDGE_META_DIR", self.meta_dir),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self._tmp.cleanup()

    def test_list_knowledge_files_returns_compact_payload(self) -> None:
        result = json.loads(server.list_knowledge_files())

        self.assertEqual(len(result), 2)
        for item in result:
            self.assertIn("uri", item)
            self.assertIn("total_files", item)
            self.assertIn("total_tokens", item)
            self.assertIn("summary", item)
            self.assertEqual(item["total_files"], 2)
            self.assertIsInstance(item["total_tokens"], int)
            self.assertGreater(item["total_tokens"], 0)
            self.assertTrue(item["summary"])

    def test_read_knowledge_file_reads_window(self) -> None:
        payload = json.loads(
            server.read_knowledge_file(
                uri="file://alpha.txt",
                start_line=1,
                end_line=2,
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["start_line"], 1)
        self.assertEqual(payload["end_line"], 2)
        self.assertIn("Alpha first line", payload["content"])
        self.assertIn("Second line about search token", payload["content"])

    def test_read_knowledge_file_reports_missing_path(self) -> None:
        payload = json.loads(server.read_knowledge_file(uri="file://missing.txt"))

        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)

    def test_index_knowledge_file_preserves_existing_ai_fields(self) -> None:
        rel = "alpha.txt"
        save_meta(
            rel,
            MetaRecord(
                summary="Stored summary",
                token_count=1,
                created_at="",
                file_type=".txt",
                magic_filters=[
                    MagicFilter(
                        label="Part A",
                        start_line=1,
                        end_line=2,
                        description="first section",
                    )
                ],
                faqs=[FAQ(question="Q", answer="A")],
            ),
        )

        payload = json.loads(server.index_knowledge_file(uri="file://alpha.txt"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"], "Stored summary")
        self.assertEqual(len(payload["magic_filters"]), 1)
        self.assertEqual(len(payload["faqs"]), 1)
        self.assertGreaterEqual(payload["token_count"], 1)

    def test_semantic_search_default_uris_searches_all_files(self) -> None:
        payload = json.loads(
            server.semantic_search(query="token", uris=None, top_k=5, chunk_size=2)
        )

        self.assertGreaterEqual(len(payload), 1)
        self.assertTrue(all(item["uri"].startswith("file://") for item in payload))
        self.assertTrue(all("score" in item for item in payload))

    def test_trigger_summary_generation_success_and_failure(self) -> None:
        with patch.object(server._ai, "generate_summary", return_value="Short summary"):
            payload = json.loads(server.trigger_summary_generation("file://alpha.txt"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["summary"], "Short summary")

        with patch.object(server._ai, "generate_summary", side_effect=RuntimeError("boom")):
            payload = json.loads(server.trigger_summary_generation("file://alpha.txt"))
            self.assertFalse(payload["ok"])
            self.assertIn("boom", payload["error"])

    def test_trigger_magic_filter_generation_success_and_failure(self) -> None:
        mock_filters = [
            MagicFilter(
                label="Intro",
                start_line=1,
                end_line=2,
                description="intro section",
            )
        ]
        with patch.object(server._ai, "generate_magic_filters", return_value=mock_filters):
            payload = json.loads(server.trigger_magic_filter_generation("file://alpha.txt"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["magic_filters"][0]["label"], "Intro")

        with patch.object(
            server._ai,
            "generate_magic_filters",
            side_effect=RuntimeError("failed filters"),
        ):
            payload = json.loads(server.trigger_magic_filter_generation("file://alpha.txt"))
            self.assertFalse(payload["ok"])
            self.assertIn("failed filters", payload["error"])

    def test_trigger_faq_generation_success_and_failure(self) -> None:
        mock_faqs = [FAQ(question="What is alpha?", answer="A file")]
        with patch.object(server._ai, "generate_faqs", return_value=mock_faqs):
            payload = json.loads(server.trigger_faq_generation("file://alpha.txt", n_questions=1))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["faqs"][0]["question"], "What is alpha?")

        with patch.object(server._ai, "generate_faqs", side_effect=RuntimeError("faq error")):
            payload = json.loads(server.trigger_faq_generation("file://alpha.txt", n_questions=1))
            self.assertFalse(payload["ok"])
            self.assertIn("faq error", payload["error"])

    def test_resource_list_all_matches_tool_output_shape(self) -> None:
        tool_payload = json.loads(server.list_knowledge_files())
        resource_payload = json.loads(server.resource_list_all())

        self.assertEqual(tool_payload, resource_payload)

    def test_resource_read_file_returns_first_page(self) -> None:
        payload = json.loads(server.resource_read_file("alpha.txt"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["start_line"], 1)
        self.assertIn("Alpha first line", payload["content"])


if __name__ == "__main__":
    unittest.main(verbosity=2)