import tempfile
import unittest
from pathlib import Path
from stat import S_IMODE
from types import SimpleNamespace
from unittest.mock import Mock, patch

from subtranslator import (
    SubtitleEventHandler,
    SubtitleTranslator,
    state,
)

SRT_CONTENT = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"


class SubtitleTranslatorTests(unittest.TestCase):
    def setUp(self):
        self.translator = SubtitleTranslator(
            api_key="test-key",
            proxy_url="https://api.example.test/v1/chat/completions",
            model="user-model",
            max_workers=2,
            target_lang="zh",
        )

    def tearDown(self):
        self.translator.close()

    def test_segment_failure_falls_back_to_original_text(self):
        initial_log_count = len(state.translation_content_logs)
        self.translator.translate_text = Mock(
            side_effect=RuntimeError("simulated API failure")
        )
        result = self.translator.translate_subtitle_content(
            SRT_CONTENT,
            file_path="example.srt",
        )
        self.assertEqual(result.failed_indices, (0,))
        self.assertEqual(result.success_rate, 0)
        self.assertIn("Hello", result.content)
        self.assertNotIn("PLACEHOLDER", result.content)
        self.assertEqual(len(state.translation_content_logs), initial_log_count)

    def test_api_failure_retries_only_the_failed_request(self):
        failed_response = Mock(status_code=400, headers={})
        failed_response.json.return_value = {
            "error": {"code": "bad_input", "message": "invalid subtitle"}
        }
        successful_response = Mock(status_code=200)
        successful_response.json.return_value = {
            "choices": [{"message": {"content": "你好"}}]
        }
        session = Mock()
        session.post.side_effect = [failed_response, successful_response]
        self.translator._get_session = Mock(return_value=session)

        with patch("subtranslator.time.sleep"):
            translated = self.translator.translate_text("Hello", retry_count=1)

        self.assertEqual(translated, "你好")
        self.assertEqual(session.post.call_count, 2)

    def test_successful_segment_is_not_resent_when_another_segment_retries(self):
        request_counts = {"First": 0, "Second": 0}

        def post(_url, json, timeout):
            self.assertEqual(timeout, 30)
            text = json["messages"][1]["content"].rsplit("\n", 1)[-1]
            request_counts[text] += 1
            if text == "Second" and request_counts[text] == 1:
                response = Mock(status_code=400, headers={})
                response.json.return_value = {
                    "error": {"message": "temporary rejection"}
                }
                return response
            response = Mock(status_code=200)
            response.json.return_value = {
                "choices": [{"message": {"content": f"译文 {text}"}}]
            }
            return response

        session = Mock()
        session.post.side_effect = post
        self.translator._get_session = Mock(return_value=session)
        self.translator.api_retry_count = 1
        content = (
            "1\n00:00:01,000 --> 00:00:02,000\nFirst\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\nSecond\n"
        )

        with patch("subtranslator.time.sleep"):
            result = self.translator.translate_subtitle_content(content)

        self.assertEqual(result.failed_indices, ())
        self.assertEqual(request_counts, {"First": 1, "Second": 2})

    def test_ninety_nine_percent_translation_is_saved_as_partial_success(self):
        segments = []
        for index in range(100):
            segments.append(
                f"{index + 1}\n00:00:{index % 60:02d},000 --> "
                f"00:00:{index % 60:02d},500\nLine {index + 1}"
            )
        content = "\n\n".join(segments) + "\n"

        def translate(text):
            if text == "Line 100":
                raise RuntimeError("simulated API failure")
            return f"译文 {text}"

        self.translator.translate_text = Mock(side_effect=translate)
        self.translator._wait_for_file_stable = Mock(return_value=True)

        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "example.en.srt"
            source_path.write_text(content, encoding="utf-8")

            self.assertTrue(self.translator.translate_subtitle_file(str(source_path)))
            output_path = Path(temporary_directory) / "example.zh.srt"
            output = output_path.read_text(encoding="utf-8")
            self.assertIn("译文 Line 99\nLine 99", output)
            self.assertIn("Line 100", output)
            self.assertNotIn("PLACEHOLDER", output)

    def test_failed_file_is_not_written_or_reported_as_success(self):
        self.translator.translate_text = Mock(
            side_effect=RuntimeError("simulated API failure")
        )
        self.translator._wait_for_file_stable = Mock(return_value=True)

        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "example.en.srt"
            source_path.write_text(SRT_CONTENT, encoding="utf-8")

            self.assertFalse(self.translator.translate_subtitle_file(str(source_path)))
            self.assertFalse((Path(temporary_directory) / "example.zh.srt").exists())

    def test_supported_input_encodings_are_read(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            samples = {
                "utf8-bom.srt": ("字幕", "utf-8-sig"),
                "utf16.srt": ("字幕", "utf-16"),
                "gb18030.srt": ("字幕", "gb18030"),
            }
            for filename, (content, encoding) in samples.items():
                path = directory / filename
                path.write_text(content, encoding=encoding)
                self.assertEqual(
                    self.translator._read_subtitle(path),
                    content,
                )

    def test_atomic_write_replaces_complete_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "output.srt"
            output_path.write_text("old", encoding="utf-8")

            self.translator._atomic_write(output_path, "new")

            self.assertEqual(output_path.read_text(encoding="utf-8"), "new")
            self.assertEqual(S_IMODE(output_path.stat().st_mode), 0o644)
            self.assertEqual(list(output_path.parent.glob("*.tmp")), [])


class SubtitleEventHandlerTests(unittest.TestCase):
    def test_moved_file_is_scheduled(self):
        translator = SimpleNamespace(max_workers=1)
        handler = SubtitleEventHandler(translator, [".srt"])
        handler._schedule_file = Mock()
        try:
            event = SimpleNamespace(
                is_directory=False,
                dest_path="/media/example.srt",
            )
            handler.on_moved(event)
            handler._schedule_file.assert_called_once_with("/media/example.srt")
        finally:
            handler.shutdown()

    def test_failed_file_is_retried_before_counting_final_failure(self):
        translator = SimpleNamespace(
            max_workers=1,
            translate_subtitle_file=Mock(return_value=False),
        )
        handler = SubtitleEventHandler(translator, [".srt"])
        handler._schedule_file = Mock()
        try:
            with tempfile.TemporaryDirectory() as temporary_directory:
                source_path = str(Path(temporary_directory) / "example.srt")
                Path(source_path).write_text(SRT_CONTENT, encoding="utf-8")
                handler.pending_files[source_path] = Mock()
                initial_failed_count = state.stats["total_failed"]

                handler._process_file(source_path)

                handler._schedule_file.assert_called_once_with(
                    source_path,
                    delay=30,
                )
                self.assertNotIn(source_path, handler.processed_files)
                self.assertEqual(
                    state.stats["total_failed"],
                    initial_failed_count,
                )
        finally:
            handler.shutdown()

    def test_exhausted_retry_counts_one_final_failure(self):
        translator = SimpleNamespace(
            max_workers=1,
            translate_subtitle_file=Mock(return_value=False),
        )
        handler = SubtitleEventHandler(translator, [".srt"])
        handler.max_retries = 0
        try:
            with tempfile.TemporaryDirectory() as temporary_directory:
                source_path = str(Path(temporary_directory) / "example.srt")
                Path(source_path).write_text(SRT_CONTENT, encoding="utf-8")
                handler.pending_files[source_path] = Mock()
                initial_failed_count = state.stats["total_failed"]

                handler._process_file(source_path)

                self.assertEqual(
                    state.stats["total_failed"],
                    initial_failed_count + 1,
                )
        finally:
            handler.shutdown()


if __name__ == "__main__":
    unittest.main()
