"""Exercise the CLI with local captures and malformed inputs."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch


CLI = Path(__file__).resolve().parents[1] / "chat_render_drift.py"


class PathApiTests(unittest.TestCase):
    def test_windows_reserved_check_prefers_current_api(self):
        spec = importlib.util.spec_from_file_location("chat_render_drift", CLI)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        reserved = Mock(side_effect=lambda part: part == "NUL")
        windows_os = SimpleNamespace(name="nt", path=SimpleNamespace(isreserved=reserved))
        with (
            patch.object(cli, "os", windows_os),
            patch.object(cli.PureWindowsPath, "is_reserved", create=True,
                         side_effect=AssertionError("legacy API called")),
        ):
            cli.check_path(r"C:\captures\sample.json")
            with self.assertRaisesRegex(cli.InvalidCapture, "^invalid_file$"):
                cli.check_path("NUL")
        self.assertEqual(reserved.call_args_list, [call("captures"), call("sample.json"), call("NUL")])


class CliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.baseline = self.root / "baseline-private-name.json"
        self.candidate = self.root / "candidate-private-name.json"
        self.capture(self.baseline, "private message", [91, 17])
        self.capture(self.candidate, "private message", [91, 17])

    def capture(self, path, text, ids):
        payload = json.dumps({"rendered_text": text, "token_ids": ids}, ensure_ascii=False)
        path.write_bytes(payload.encode("utf-8"))

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-I", str(CLI), *args],
            cwd=self.root,
            capture_output=True,
            timeout=10,
        )

    def compare(self, code):
        result = self.run_cli(self.baseline, self.candidate)
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, b"")
        return json.loads(result.stdout)

    def assert_error(self, result, error, side=None):
        report = {"error": error}
        if side is not None:
            report["side"] = side
        expected = json.dumps(report, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        self.assertEqual((result.returncode, result.stdout, result.stderr), (2, b"", expected))

    def test_same_capture_emits_exact_metadata_only(self):
        result = self.run_cli(self.baseline, self.candidate)
        digest = hashlib.sha256(b"private message").hexdigest()
        expected = (
            '{"rendered_text":{"baseline_bytes":15,"baseline_sha256":"' + digest
            + '","candidate_bytes":15,"candidate_sha256":"' + digest
            + '","first_difference":null},"token_ids":{"baseline_count":2,'
            '"candidate_count":2,"first_difference":null}}\n'
        ).encode()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, expected, b""))

    def test_json_escaping_object_order_and_outer_whitespace_are_irrelevant(self):
        self.capture(self.baseline, "\u00e9\U0001f600", [0, 4294967295])
        self.candidate.write_bytes(b' {"token_ids":[-0,4294967295],'
                                   b'"rendered_text":"\\u00e9\\ud83d\\ude00"}\r\n')
        report = self.compare(0)
        self.assertEqual(report["rendered_text"]["baseline_bytes"], 6)

    def test_utf8_offset_can_point_inside_a_multibyte_character(self):
        self.capture(self.baseline, "Aé", [1])
        self.capture(self.candidate, "Aê", [1])
        report = self.compare(1)
        rendered = report["rendered_text"]
        self.assertEqual(rendered["first_difference"], 2)
        self.assertEqual((rendered["baseline_bytes"], rendered["candidate_bytes"]), (3, 3))
        self.assertEqual(rendered["candidate_sha256"], hashlib.sha256("Aê".encode()).hexdigest())
        self.assertIsNone(report["token_ids"]["first_difference"])

    def test_token_drift_with_same_text(self):
        self.capture(self.candidate, "private message", [91, 18])
        report = self.compare(1)
        self.assertIsNone(report["rendered_text"]["first_difference"])
        self.assertEqual(report["token_ids"], {
            "baseline_count": 2, "candidate_count": 2, "first_difference": 1,
        })

    def test_prefix_drift_with_each_side_ending_first(self):
        self.capture(self.baseline, "é", [3, 4])
        self.capture(self.candidate, "é\r\n", [3])
        report = self.compare(1)
        self.assertEqual(report["rendered_text"]["first_difference"], 2)
        self.assertEqual(report["token_ids"]["first_difference"], 1)

    def test_empty_text_and_tokens_are_allowed(self):
        self.capture(self.baseline, "", [])
        self.capture(self.candidate, "", [])
        report = self.compare(0)
        self.assertEqual(report["rendered_text"]["baseline_sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(report["token_ids"]["baseline_count"], 0)
        self.capture(self.candidate, " ", [0])
        report = self.compare(1)
        self.assertEqual(report["rendered_text"]["first_difference"], 0)
        self.assertEqual(report["token_ids"]["first_difference"], 0)

    def test_unicode_composition_and_line_endings_remain_distinct(self):
        self.capture(self.baseline, "e\u0301\r\n", [])
        self.capture(self.candidate, "é\n", [])
        self.assertEqual(self.compare(1)["rendered_text"]["first_difference"], 0)
        self.capture(self.candidate, "e\u0301\n", [])
        self.assertEqual(self.compare(1)["rendered_text"]["first_difference"], 3)

    def test_duplicate_fields_rejected_after_key_unescaping(self):
        self.candidate.write_bytes(b'{"rendered_text":"first","rendered_\\u0074ext":"second","token_ids":[]}')
        self.assert_error(self.run_cli(self.baseline, self.candidate), "duplicate_key", "candidate")

    def test_schema_requires_exact_fields_and_value_types(self):
        for payload, error in (
            (b'[]', "invalid_fields"),
            (b'{"rendered_text":"secret"}', "invalid_fields"),
            (b'{"rendered_text":"secret","token_ids":[],"sensitive-extra":1}', "invalid_fields"),
            (b'{"rendered_text":null,"token_ids":[]}', "invalid_rendered_text"),
            (b'{"rendered_text":"secret","token_ids":"1"}', "invalid_token_ids"),
        ):
            with self.subTest(error=error, payload=payload):
                self.baseline.write_bytes(payload)
                self.assert_error(self.run_cli(self.baseline, self.candidate), error, "baseline")

    def test_only_nonnegative_uint32_integers_are_tokens(self):
        for token in (b"true", b"false", b"1.0", b"1e0", b"-1", b"4294967296",
                      b"9" * 5000, b'"91"', b"null", b"[]"):
            with self.subTest(token=token[:20]):
                self.candidate.write_bytes(b'{"rendered_text":"secret","token_ids":[' + token + b"]}")
                self.assert_error(self.run_cli(self.baseline, self.candidate), "invalid_token_id", "candidate")

    def test_invalid_json_and_encoding_errors_are_sanitized(self):
        for payload, error in (
            (b'{"rendered_text":"\xed\xa0\x80","token_ids":[]}', "invalid_utf8"),
            (b'\xef\xbb\xbf{"rendered_text":"sensitive","token_ids":[]}', "invalid_json"),
            (b'{"rendered_text":"\\ud800","token_ids":[]}', "invalid_rendered_text"),
            (b'{"rendered_text":"\\udfff","token_ids":[]}', "invalid_rendered_text"),
            (b'{"rendered_text":"sensitive","token_ids":[NaN]}', "invalid_json"),
            (b'{"rendered_text":"sensitive","token_ids":[Infinity]}', "invalid_json"),
            (b'{"rendered_text":"sensitive","token_ids":[01]}', "invalid_json"),
            (b'{"rendered_text":"sensitive","token_ids":[]} trailing', "invalid_json"),
            (b"[" * 2000 + b"]" * 2000, "invalid_json"),
        ):
            with self.subTest(payload=payload[:100]):
                self.candidate.write_bytes(payload)
                self.assert_error(self.run_cli(self.baseline, self.candidate), error, "candidate")

    def test_file_byte_limit_inclusive(self):
        data = b'{"rendered_text":"","token_ids":[]}'
        self.candidate.write_bytes(data.ljust(4 * 1024 * 1024))
        self.compare(1)
        with self.candidate.open("ab") as stream:
            stream.write(b" ")
        self.assert_error(self.run_cli(self.baseline, self.candidate), "file_limit", "candidate")

    def test_token_count_limit_inclusive(self):
        self.capture(self.candidate, "", [4294967295] * 200_000)
        self.assertEqual(self.compare(1)["token_ids"]["candidate_count"], 200_000)
        self.capture(self.candidate, "", [0] * 200_001)
        self.assert_error(self.run_cli(self.baseline, self.candidate), "token_limit", "candidate")

    def test_invalid_paths_do_not_leak_arguments(self):
        for path in (self.root, self.root / "missing-private-name.json", "-"):
            with self.subTest(path=path):
                args = [self.baseline, path] if path != "-" else ["--", self.baseline, path]
                self.assert_error(self.run_cli(*args), "invalid_file", "candidate")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_fifo_is_rejected_without_opening_it_for_read(self):
        fifo = self.root / "private-fifo.json"
        os.mkfifo(fifo)
        self.assert_error(self.run_cli(self.baseline, fifo), "invalid_file", "candidate")

    @unittest.skipUnless(os.name == "nt", "requires Windows path syntax")
    def test_windows_device_and_unc_paths_are_rejected(self):
        for path in ("NUL", "COM1.txt", "\\\\.\\NUL", "\\\\fake-host\\share\\x.json",
                     str(self.baseline) + ":private-stream"):
            with self.subTest(path=path):
                self.assert_error(self.run_cli(self.baseline, path), "invalid_file", "candidate")

    def test_usage_errors_and_help(self):
        for args in ([], [self.baseline], [self.baseline, self.candidate, "extra-private"],
                     ["--unknown-private", self.baseline]):
            with self.subTest(args=args):
                self.assert_error(self.run_cli(*args), "usage")
        result = self.run_cli("--help")
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertIn(b"BASELINE.json CANDIDATE.json", result.stdout)

    def test_option_separator_allows_dash_prefixed_filenames(self):
        self.capture(self.root / "-candidate.json", "private message", [91, 17])
        result = self.run_cli(self.baseline, "--", "-candidate.json")
        self.assertEqual((result.returncode, result.stderr), (0, b""))

    def test_closed_output_pipe_returns_two_without_traceback(self):
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        try:
            result = subprocess.run(
                [sys.executable, "-I", str(CLI), str(self.baseline), str(self.candidate)],
                stdout=write_fd,
                stderr=subprocess.PIPE,
                timeout=10,
            )
        finally:
            os.close(write_fd)
        self.assertEqual((result.returncode, result.stderr), (2, b""))


if __name__ == "__main__":
    unittest.main()
