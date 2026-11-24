"""Offline unit tests for the public GitHub metadata exporter (no network or game files)."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_github_metadata.py"
spec = importlib.util.spec_from_file_location("github_metadata_export", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def record(number, *, pull=False):
    result = {"id": number + 100, "number": number, "title": f"Item {number}",
              "html_url": f"https://github.com/example/project/issues/{number}",
              "user": {"login": "contributor"}, "state": "open"}
    if pull:
        result["pull_request"] = {"url": "https://api.github.com/example"}
    return result


class ExportTests(unittest.TestCase):
    def test_pages_follow_exact_page_size(self):
        calls = []
        def fake_fetch(url, token=None):
            calls.append(url)
            return list(range(100)) if "page=1" in url else [101]
        with patch.object(exporter, "fetch_json", side_effect=fake_fetch):
            self.assertEqual(len(list(exporter.pages("/repos/example/project/issues"))), 101)
        self.assertEqual(len(calls), 2)
        self.assertIn("page=2", calls[1])

    def test_export_separates_issues_and_pulls_and_counts(self):
        def fake_pages(endpoint, token=None):
            if endpoint.endswith("/issues?state=all"):
                return iter([record(1), record(2, pull=True)])
            if endpoint.endswith("/issues/1/comments"):
                return iter([{"id": 5, "body": "hello", "user": {"login": "alice"}}])
            if endpoint.endswith("/pulls/2/reviews"):
                return iter([{"id": 6, "state": "APPROVED", "user": {"login": "bob"}}])
            return iter([])
        with patch.object(exporter, "pages", side_effect=fake_pages):
            result = exporter.export("example/project")
        self.assertEqual(result["counts"], {"issues": 1, "pull_requests": 1, "comments": 1, "reviews": 1})
        self.assertEqual(result["issues"][0]["comments"][0]["author"], "alice")
        self.assertEqual(result["pull_requests"][0]["reviews"][0]["author"], "bob")

    def test_duplicate_ids_fail_closed(self):
        with patch.object(exporter, "pages", return_value=iter([record(1), record(1)])):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                exporter.export("example/project")

    def test_invalid_repository_rejected(self):
        for name in ("invalid", "owner/", "/repo", "a/b/c"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                exporter.export(name)

    def test_non_list_api_response_rejected(self):
        with patch.object(exporter, "fetch_json", return_value={"message": "unexpected"}):
            with self.assertRaisesRegex(ValueError, "Expected list"):
                list(exporter.pages("/repos/example/project/issues"))


if __name__ == "__main__":
    unittest.main()
