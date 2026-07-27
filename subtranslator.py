import logging
import os
import re
import signal
import stat
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import ClassVar

import requests
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# 导入 Web UI
from config_manager import ConfigError, get_config_path, load_config
from web_ui import start_web_server, state

logger = logging.getLogger("SubtitleTranslator")


class SubtitleTranslationError(RuntimeError):
    pass


def configure_logging(log_level):
    handlers = [logging.StreamHandler(sys.stdout)]
    file_error = None
    log_path = get_config_path().parent / "subtranslator.log"

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.insert(0, logging.FileHandler(log_path, encoding="utf-8"))
    except OSError as exc:
        file_error = exc

    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )

    if file_error:
        logger.warning(
            "无法写入日志文件 %s，仅使用控制台日志: %s", log_path, file_error
        )


class SubtitleTranslator:
    LANG_NAMES: ClassVar[dict[str, str]] = {
        "zh": "中文",
        "en": "English",
        "ja": "日本語",
        "ko": "한국어",
        "fr": "Français",
        "de": "Deutsch",
        "es": "Español",
        "it": "Italiano",
        "pt": "Português",
        "ru": "Русский",
        "ar": "العربية",
        "th": "ไทย",
    }

    def __init__(
        self,
        api_key,
        proxy_url=None,
        model="gpt-4o-mini",
        max_workers=10,
        target_lang="zh",
    ):
        self.api_key = api_key
        self.proxy_url = (
            proxy_url if proxy_url else "https://api.openai.com/v1/chat/completions"
        )
        self.model = model
        self.max_workers = max_workers
        self.target_lang = target_lang
        self.target_lang_name = self.LANG_NAMES.get(target_lang, target_lang)
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="subtitle-api",
        )
        self.thread_local = threading.local()
        logger.info(
            f"初始化翻译器: 模型={model}, 代理URL={'已设置' if proxy_url else '未设置'}, 最大并发数={max_workers}"
        )
        state.add_log("INFO", f"翻译器初始化完成: {model}")

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)

    def _get_session(self):
        session = getattr(self.thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(self.headers)
            self.thread_local.session = session
        return session

    def _is_already_translated(self, content):
        """检测字幕是否已经是双语格式"""
        lines = content.strip().split("\n")
        chinese_count = 0
        non_chinese_count = 0

        for line in lines:
            if "-->" in line or line.strip().isdigit() or not line.strip():
                continue
            if re.search(r"[\u4e00-\u9fff]", line):
                chinese_count += 1
            elif re.search(r"[a-zA-Z]", line):
                non_chinese_count += 1

        total = chinese_count + non_chinese_count
        if total < 4:
            return False
        return chinese_count >= total * 0.2 and non_chinese_count >= total * 0.2

    def _wait_for_file_stable(self, file_path, timeout=10):
        """等待文件写入完成"""
        last_size = -1
        stable_count = 0
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                current_size = os.path.getsize(file_path)
                if current_size == last_size:
                    stable_count += 1
                    if stable_count >= 3:  # 连续3次大小不变
                        return True
                else:
                    stable_count = 0
                    last_size = current_size
                time.sleep(0.5)
            except OSError:
                time.sleep(0.5)

        return stable_count >= 2

    def translate_subtitle_content(self, content, file_path="unknown"):
        """翻译字幕内容，保留时间轴格式，使用并发处理，并保留原文（中文在上，原文在下）"""
        lines = content.strip().split("\n")
        result_lines = []

        text_segments = []
        segment_positions = []
        original_texts = []

        i = 0
        while i < len(lines):
            line = lines[i]
            if line.strip().isdigit():
                result_lines.append(line)
                i += 1
                continue

            if "-->" in line and re.search(r"\d{2}:\d{2}:\d{2},\d{3}", line):
                result_lines.append(line)

                text_lines = []
                i += 1
                start_pos = len(result_lines)

                while (
                    i < len(lines)
                    and lines[i].strip()
                    and not lines[i].strip().isdigit()
                    and "-->" not in lines[i]
                ):
                    text_lines.append(lines[i])
                    i += 1

                if text_lines:
                    text_to_translate = "\n".join(text_lines)
                    result_lines.append("PLACEHOLDER")

                    text_segments.append(text_to_translate)
                    segment_positions.append(start_pos)
                    original_texts.append(text_to_translate)

                if i < len(lines) and not lines[i].strip():
                    result_lines.append("")
                    i += 1
            else:
                result_lines.append(line)
                i += 1

        if text_segments:
            future_to_index = {
                self.executor.submit(self.translate_text, text): idx
                for idx, text in enumerate(text_segments)
            }
            failures = []
            translated_texts = [None] * len(text_segments)

            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    translated_text = future.result()
                    translated_texts[idx] = translated_text
                    result_lines[segment_positions[idx]] = (
                        f"{translated_text}\n{original_texts[idx]}"
                    )
                except Exception as exc:  # noqa: BLE001 - future may raise provider errors
                    logger.error("翻译片段失败: %s", exc)
                    failures.append(idx)

            if failures:
                raise SubtitleTranslationError(
                    f"{len(failures)}/{len(text_segments)} 个字幕片段翻译失败"
                )

            for original_text, translated_text in zip(
                original_texts, translated_texts, strict=True
            ):
                state.add_translation_content_log(
                    file_path=file_path,
                    original_text=original_text[:100],
                    translated_text=translated_text[:100],
                )

        return "\n".join(result_lines)

    def translate_text(self, text, retry=3):
        """调用ChatGPT API翻译文本，带重试机制"""
        if not self._needs_translation(text):
            return text

        for attempt in range(retry):
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": f"你是一个专业的字幕翻译专家。请将以下字幕翻译成{self.target_lang_name}，保持原意的同时使翻译自然流畅。不要添加任何解释或额外内容。",
                        },
                        {
                            "role": "user",
                            "content": f"翻译以下字幕内容为{self.target_lang_name}:\n{text}",
                        },
                    ],
                    "temperature": 0.3,
                }

                response = self._get_session().post(
                    self.proxy_url, json=payload, timeout=30
                )

                if response.status_code == 200:
                    result = response.json()
                    try:
                        translated_text = result["choices"][0]["message"][
                            "content"
                        ].strip()
                    except (KeyError, IndexError, TypeError, AttributeError) as exc:
                        raise SubtitleTranslationError("API 响应格式不正确") from exc
                    return translated_text
                else:
                    logger.warning(
                        f"API 返回错误 {response.status_code}, 尝试 {attempt + 1}/{retry}"
                    )
                    if attempt < retry - 1:
                        time.sleep(2**attempt)  # 指数退避
                    else:
                        raise SubtitleTranslationError(
                            f"API 错误: {response.status_code}"
                        )
            except Exception as e:
                if attempt < retry - 1:
                    logger.warning(f"翻译失败，重试 {attempt + 1}/{retry}: {e!s}")
                    time.sleep(2**attempt)
                else:
                    raise

        return text

    def _needs_translation(self, text):
        """检查文本是否需要翻译"""
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        return len(chinese_chars) < len(text) * 0.3

    def translate_subtitle_file(self, file_path):
        """翻译字幕文件"""
        state.increment_stat("in_progress")
        try:
            logger.info(f"开始处理字幕文件: {file_path}")
            state.add_log("INFO", f"开始翻译: {file_path}")
            state.add_translation_log(file_path, "starting", "等待文件稳定...", 0)
            state.add_file(file_path, "progress", "正在翻译...")

            # 等待文件稳定
            if not self._wait_for_file_stable(file_path):
                logger.warning(f"文件可能未完全写入: {file_path}")
                state.add_translation_log(
                    file_path, "translating", "文件可能未完全写入，继续处理...", 10
                )

            state.add_translation_log(file_path, "translating", "读取文件内容...", 20)
            content = self._read_subtitle(file_path)

            # 检查是否已翻译
            if self._is_already_translated(content):
                logger.info(f"文件已是双语字幕，跳过: {file_path}")
                state.add_log("INFO", f"跳过已翻译文件: {file_path}")
                state.add_translation_log(
                    file_path, "skipped", "已是双语字幕，跳过翻译", 100
                )
                state.add_file(file_path, "success", "已是双语字幕")
                return True

            state.add_translation_log(
                file_path, "translating", "正在调用 API 翻译...", 30
            )
            translated_content = self.translate_subtitle_content(
                content, file_path=file_path
            )

            state.add_translation_log(
                file_path, "translating", "翻译完成，保存文件...", 80
            )
            # 智能生成输出文件名：移除语言标识（如 .en），添加 .zh
            output_path = self._generate_output_path(file_path)

            source_mode = stat.S_IMODE(Path(file_path).stat().st_mode)
            self._atomic_write(output_path, translated_content, mode=source_mode)

            logger.info(f"翻译完成: {output_path}")
            state.add_log("INFO", f"翻译完成: {output_path}")
            state.add_translation_log(
                file_path, "success", f"已保存到 {output_path}", 100
            )
            state.increment_stat("total_translated")
            state.add_file(file_path, "success", f"已保存到 {output_path}")
            return True

        except Exception as e:  # noqa: BLE001 - file task boundary records all failures
            logger.error(f"翻译失败 {file_path}: {e!s}")
            state.add_log("ERROR", f"翻译失败 {file_path}: {e!s}")
            state.add_translation_log(file_path, "failed", f"错误: {e!s}", 0)
            state.add_file(file_path, "error", str(e))
            return False
        finally:
            state.decrement_stat("in_progress")

    @staticmethod
    def _read_subtitle(file_path):
        data = Path(file_path).read_bytes()
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return data.decode("utf-16")
        if data.startswith(b"\xef\xbb\xbf"):
            return data.decode("utf-8-sig")

        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise SubtitleTranslationError(
                    "字幕编码不受支持，请转换为 UTF-8、UTF-16 或 GB18030"
                ) from exc

    @staticmethod
    def _atomic_write(output_path, content, mode=0o644):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as output_file:
                temporary_path = Path(output_file.name)
                os.fchmod(output_file.fileno(), mode)
                output_file.write(content)
                output_file.flush()
                os.fsync(output_file.fileno())
            os.replace(temporary_path, output_path)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()

    def _generate_output_path(self, file_path):
        """生成输出文件路径，移除所有语言标识"""
        # 常见语言代码（包括 hi 等）
        lang_codes = [
            ".en",
            ".eng",
            ".zh",
            ".chs",
            ".cht",
            ".ja",
            ".jp",
            ".ko",
            ".fr",
            ".de",
            ".es",
            ".it",
            ".pt",
            ".ru",
            ".hi",
            ".ar",
            ".th",
            ".vi",
        ]

        # 获取文件扩展名
        for ext in [".srt", ".ass", ".ssa", ".vtt"]:
            if file_path.endswith(ext):
                base_path = file_path[: -len(ext)]

                # 循环移除所有语言代码（处理 .en.hi 这种多语言标识）
                changed = True
                while changed:
                    changed = False
                    for lang in lang_codes:
                        if base_path.endswith(lang):
                            base_path = base_path[: -len(lang)]
                            changed = True
                            break

                # 添加目标语言标识和原扩展名
                return f"{base_path}.{self.target_lang}{ext}"

        # 如果没有匹配的扩展名，使用原逻辑
        base, ext = os.path.splitext(file_path)
        return f"{base}.{self.target_lang}{ext}"


class SubtitleEventHandler(FileSystemEventHandler):
    def __init__(self, translator, subtitle_extensions):
        self.translator = translator
        self.subtitle_extensions = subtitle_extensions
        self.processed_files = {}  # {path: timestamp}
        self.processing_lock = threading.Lock()
        self.pending_files = {}
        self.retry_counts = {}
        self.max_age = 3600  # 1 hour TTL
        self.max_retries = 3
        self.shutting_down = False
        self.file_executor = ThreadPoolExecutor(
            max_workers=max(1, min(4, translator.max_workers)),
            thread_name_prefix="subtitle-file",
        )

    def on_created(self, event):
        if event.is_directory:
            return
        self._schedule_file(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        self._schedule_file(event.dest_path)

    def shutdown(self):
        with self.processing_lock:
            self.shutting_down = True
            timers = list(self.pending_files.values())
            self.pending_files.clear()
        for timer in timers:
            timer.cancel()
        self.file_executor.shutdown(wait=True, cancel_futures=True)

    def _schedule_file(self, file_path, delay=2):
        if not any(file_path.lower().endswith(ext) for ext in self.subtitle_extensions):
            return
        # 保留现有语言跳过逻辑；多目标语言逻辑不在本次修改范围。
        if ".zh." in file_path:
            logger.debug("跳过已翻译文件: %s", file_path)
            return

        with self.processing_lock:
            if self.shutting_down:
                return
            self._cleanup_processed_locked()
            if file_path in self.pending_files or file_path in self.processed_files:
                return

            timer = threading.Timer(delay, self._submit_file, args=[file_path])
            timer.daemon = True
            self.pending_files[file_path] = timer
            timer.start()

    def _submit_file(self, file_path):
        with self.processing_lock:
            if self.shutting_down or file_path not in self.pending_files:
                return
        try:
            self.file_executor.submit(self._process_file, file_path)
        except RuntimeError:
            logger.debug("文件处理队列已关闭: %s", file_path)

    def _process_file(self, file_path):
        with self.processing_lock:
            if self.shutting_down:
                return

            # 跳过已翻译的文件
            if ".zh." in file_path:
                self.pending_files.pop(file_path, None)
                return

            if not os.path.exists(file_path):
                logger.warning(f"文件不存在: {file_path}")
                self.pending_files.pop(file_path, None)
                return

        success = self.translator.translate_subtitle_file(file_path)
        retry_delay = None

        with self.processing_lock:
            self.pending_files.pop(file_path, None)
            if success:
                self.processed_files[file_path] = time.time()
                self.retry_counts.pop(file_path, None)
            elif not self.shutting_down:
                attempt = self.retry_counts.get(file_path, 0) + 1
                self.retry_counts[file_path] = attempt
                if attempt <= self.max_retries:
                    retry_delay = 30 * (2 ** (attempt - 1))
                else:
                    state.increment_stat("total_failed")
                    state.add_log("ERROR", f"文件重试次数已耗尽: {file_path}")

        if retry_delay is not None:
            logger.warning(
                "将在 %s 秒后重试文件（%s/%s）: %s",
                retry_delay,
                self.retry_counts[file_path],
                self.max_retries,
                file_path,
            )
            self._schedule_file(file_path, delay=retry_delay)

    def _cleanup_processed_locked(self):
        now = time.time()
        expired = [k for k, v in self.processed_files.items() if now - v > self.max_age]
        for k in expired:
            del self.processed_files[k]


def main():
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    configure_logging(config["LOG_LEVEL"])

    api_key = config["API_KEY"]
    proxy_url = config["PROXY_URL"] or None
    model = config["MODEL"]

    watch_dirs = [
        config["MOVIES_DIR"],
        config["TV_DIR"],
    ]

    custom_dirs = config["CUSTOM_DIRS"]
    if custom_dirs:
        custom_dir_list = [d.strip() for d in custom_dirs.split(",") if d.strip()]
        watch_dirs.extend(custom_dir_list)
    watch_dirs = list(dict.fromkeys(watch_dirs))

    max_workers = int(config["MAX_WORKERS"])
    web_port = int(config["WEB_PORT"])
    target_lang = config["TARGET_LANG"]

    if not api_key:
        logger.error("未设置API_KEY环境变量")
        state.add_log("ERROR", "未设置API_KEY环境变量")
        return 1

    subtitle_extensions = [".srt", ".ass", ".ssa", ".vtt"]

    translator = SubtitleTranslator(api_key, proxy_url, model, max_workers, target_lang)

    event_handler = SubtitleEventHandler(translator, subtitle_extensions)
    observer = Observer()
    shutdown_event = threading.Event()

    def request_shutdown(signum, _frame):
        logger.info("收到退出信号 %s，正在关闭服务...", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    scheduled_directories = 0
    for watch_dir in watch_dirs:
        if os.path.exists(watch_dir):
            observer.schedule(event_handler, watch_dir, recursive=True)
            scheduled_directories += 1
            logger.info(f"开始监控目录: {watch_dir}")
            state.add_log("INFO", f"开始监控目录: {watch_dir}")
        else:
            logger.warning(f"目录不存在，跳过监控: {watch_dir}")
            state.add_log("WARNING", f"目录不存在: {watch_dir}")

    if scheduled_directories == 0:
        logger.error("没有可用的监控目录，服务无法启动")
        event_handler.shutdown()
        translator.close()
        return 1

    observer.start()
    state.set_health_checker(observer.is_alive)

    # 启动 Web UI
    web_thread = threading.Thread(target=start_web_server, args=[web_port], daemon=True)
    web_thread.start()

    logger.info(f"字幕翻译服务已启动，监控 {len(watch_dirs)} 个目录")
    logger.info(f"Web UI 访问地址: http://localhost:{web_port}")
    state.add_log("INFO", f"服务启动成功，Web UI: http://localhost:{web_port}")

    try:
        while not shutdown_event.wait(1):
            if not observer.is_alive():
                raise RuntimeError("文件监控线程意外退出")
    finally:
        state.add_log("INFO", "服务正在关闭...")
        observer.stop()
        observer.join(timeout=10)
        event_handler.shutdown()
        translator.close()
        state.set_health_checker(None)

    return 0


if __name__ == "__main__":
    sys.exit(main())
