import tempfile
import unittest
from pathlib import Path
from stat import S_IMODE
from types import SimpleNamespace
from unittest.mock import Mock

from subtranslator import (
    SubtitleEventHandler,
    SubtitleTranslationError,
    SubtitleTranslator,
    state,
)

SRT_CONTENT = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"


class SubtitleTranslatorTests(unittest.TestCase):
    def setUp(self):
        self.translator = SubtitleTranslator(
            api_key="test-key",
            max_workers=2,
            target_lang="zh",
        )

    def tearDown(self):
        self.translator.close()

    def test_segment_failure_fails_the_whole_translation(self):
        initial_log_count = len(state.translation_content_logs)
        self.translator.translate_text = Mock(
            side_effect=RuntimeError("simulated API failure")
        )
        with self.assertRaises(SubtitleTranslationError):
            self.translator.translate_subtitle_content(
                SRT_CONTENT,
                file_path="example.srt",
            )
        self.assertEqual(len(state.translation_content_logs), initial_log_count)

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
