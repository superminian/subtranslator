#!/usr/bin/env python3
import os
import time
import sys
import re
import json
import logging
import requests
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入 Web UI
from web_ui import app, state, start_web_server

# 配置日志
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/config/subtranslator.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SubtitleTranslator")

class SubtitleTranslator:
    LANG_NAMES = {
        'zh': '中文', 'en': 'English', 'ja': '日本語', 'ko': '한국어',
        'fr': 'Français', 'de': 'Deutsch', 'es': 'Español', 'it': 'Italiano',
        'pt': 'Português', 'ru': 'Русский', 'ar': 'العربية', 'th': 'ไทย',
    }

    def __init__(self, api_key, proxy_url=None, model="gpt-4o-mini", max_workers=10, target_lang="zh"):
        self.api_key = api_key
        self.proxy_url = proxy_url if proxy_url else "https://api.openai.com/v1/chat/completions"
        self.model = model
        self.max_workers = max_workers
        self.target_lang = target_lang
        self.target_lang_name = self.LANG_NAMES.get(target_lang, target_lang)
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        logger.info(f"初始化翻译器: 模型={model}, 代理URL={'已设置' if proxy_url else '未设置'}, 最大并发数={max_workers}")
        state.add_log('INFO', f'翻译器初始化完成: {model}')

    def _is_already_translated(self, content):
        """检测字幕是否已经是双语格式"""
        lines = content.strip().split('\n')
        chinese_count = 0
        non_chinese_count = 0

        for line in lines:
            if '-->' in line or line.strip().isdigit() or not line.strip():
                continue
            if re.search(r'[\u4e00-\u9fff]', line):
                chinese_count += 1
            elif re.search(r'[a-zA-Z]', line):
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

    def translate_subtitle_content(self, content):
        """翻译字幕内容，保留时间轴格式，使用并发处理，并保留原文（中文在上，原文在下）"""
        lines = content.strip().split('\n')
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

            if '-->' in line and re.search(r'\d{2}:\d{2}:\d{2},\d{3}', line):
                result_lines.append(line)

                text_lines = []
                i += 1
                start_pos = len(result_lines)

                while i < len(lines) and lines[i].strip() and not lines[i].strip().isdigit() and '-->' not in lines[i]:
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
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_index = {
                    executor.submit(self.translate_text, text): idx
                    for idx, text in enumerate(text_segments)
                }

                for future in as_completed(future_to_index):
                    idx = future_to_index[future]
                    try:
                        translated_text = future.result()
                        result_lines[segment_positions[idx]] = f"{translated_text}\n{original_texts[idx]}"

                        # 记录翻译内容日志
                        state.add_translation_content_log(
                            file_path=getattr(self, '_current_file', 'unknown'),
                            original_text=original_texts[idx][:100],  # 只记录前100字符
                            translated_text=translated_text[:100]
                        )
                    except Exception as e:
                        logger.error(f"翻译任务失败: {str(e)}")
                        result_lines[segment_positions[idx]] = original_texts[idx]

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
                        {"role": "system", "content": f"你是一个专业的字幕翻译专家。请将以下字幕翻译成{self.target_lang_name}，保持原意的同时使翻译自然流畅。不要添加任何解释或额外内容。"},
                        {"role": "user", "content": f"翻译以下字幕内容为{self.target_lang_name}:\n{text}"}
                    ],
                    "temperature": 0.3
                }

                response = requests.post(
                    self.proxy_url,
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )

                if response.status_code == 200:
                    result = response.json()
                    translated_text = result["choices"][0]["message"]["content"].strip()
                    return translated_text
                else:
                    logger.warning(f"API 返回错误 {response.status_code}, 尝试 {attempt + 1}/{retry}")
                    if attempt < retry - 1:
                        time.sleep(2 ** attempt)  # 指数退避
                    else:
                        raise Exception(f"API 错误: {response.status_code}")
            except Exception as e:
                if attempt < retry - 1:
                    logger.warning(f"翻译失败，重试 {attempt + 1}/{retry}: {str(e)}")
                    time.sleep(2 ** attempt)
                else:
                    raise e

        return text

    def _needs_translation(self, text):
        """检查文本是否需要翻译"""
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        return len(chinese_chars) < len(text) * 0.3

    def translate_subtitle_file(self, file_path):
        """翻译字幕文件"""
        try:
            # 设置当前文件路径，供翻译内容日志使用
            self._current_file = file_path

            logger.info(f"开始处理字幕文件: {file_path}")
            state.add_log('INFO', f'开始翻译: {file_path}')
            state.add_translation_log(file_path, 'starting', '等待文件稳定...', 0)
            state.increment_stat('in_progress')
            state.add_file(file_path, 'progress', '正在翻译...')

            # 等待文件稳定
            if not self._wait_for_file_stable(file_path):
                logger.warning(f"文件可能未完全写入: {file_path}")
                state.add_translation_log(file_path, 'translating', '文件可能未完全写入，继续处理...', 10)

            state.add_translation_log(file_path, 'translating', '读取文件内容...', 20)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 检查是否已翻译
            if self._is_already_translated(content):
                logger.info(f"文件已是双语字幕，跳过: {file_path}")
                state.add_log('INFO', f'跳过已翻译文件: {file_path}')
                state.add_translation_log(file_path, 'skipped', '已是双语字幕，跳过翻译', 100)
                state.update_stats('in_progress', state.stats['in_progress'] - 1)
                state.add_file(file_path, 'success', '已是双语字幕')
                return

            state.add_translation_log(file_path, 'translating', '正在调用 API 翻译...', 30)
            translated_content = self.translate_subtitle_content(content)

            state.add_translation_log(file_path, 'translating', '翻译完成，保存文件...', 80)
            # 智能生成输出文件名：移除语言标识（如 .en），添加 .zh
            output_path = self._generate_output_path(file_path)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(translated_content)

            logger.info(f"翻译完成: {output_path}")
            state.add_log('INFO', f'翻译完成: {output_path}')
            state.add_translation_log(file_path, 'success', f'已保存到 {output_path}', 100)
            state.increment_stat('total_translated')
            state.update_stats('in_progress', state.stats['in_progress'] - 1)
            state.add_file(file_path, 'success', f'已保存到 {output_path}')

        except Exception as e:
            logger.error(f"翻译失败 {file_path}: {str(e)}")
            state.add_log('ERROR', f'翻译失败 {file_path}: {str(e)}')
            state.add_translation_log(file_path, 'failed', f'错误: {str(e)}', 0)
            state.increment_stat('total_failed')
            state.update_stats('in_progress', state.stats['in_progress'] - 1)
            state.add_file(file_path, 'error', str(e))

    def _generate_output_path(self, file_path):
        """生成输出文件路径，移除所有语言标识"""
        # 常见语言代码（包括 hi 等）
        lang_codes = ['.en', '.eng', '.zh', '.chs', '.cht', '.ja', '.jp', '.ko', '.fr', '.de', '.es', '.it', '.pt', '.ru', '.hi', '.ar', '.th', '.vi']

        # 获取文件扩展名
        for ext in ['.srt', '.ass', '.ssa', '.vtt']:
            if file_path.endswith(ext):
                base_path = file_path[:-len(ext)]

                # 循环移除所有语言代码（处理 .en.hi 这种多语言标识）
                changed = True
                while changed:
                    changed = False
                    for lang in lang_codes:
                        if base_path.endswith(lang):
                            base_path = base_path[:-len(lang)]
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
        self.max_age = 3600  # 1 hour TTL

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        if any(file_path.endswith(ext) for ext in self.subtitle_extensions):
            # 跳过已翻译的文件（包含 .zh.）
            if '.zh.' in file_path:
                logger.debug(f"跳过已翻译文件: {file_path}")
                return

            # 防抖：延迟处理
            with self.processing_lock:
                if file_path in self.pending_files:
                    logger.debug(f"文件已在待处理队列: {file_path}")
                    return
                self._cleanup_processed()
                if file_path in self.processed_files:
                    logger.debug(f"文件已处理过: {file_path}")
                    return
                self.pending_files[file_path] = time.time()

            # 延迟2秒后处理
            threading.Timer(2.0, self._process_file, args=[file_path]).start()

    def _process_file(self, file_path):
        with self.processing_lock:
            if file_path in self.processed_files:
                logger.debug(f"文件已处理，跳过: {file_path}")
                if file_path in self.pending_files:
                    del self.pending_files[file_path]
                return

            # 跳过已翻译的文件
            if '.zh.' in file_path:
                if file_path in self.pending_files:
                    del self.pending_files[file_path]
                return

            if not os.path.exists(file_path):
                logger.warning(f"文件不存在: {file_path}")
                if file_path in self.pending_files:
                    del self.pending_files[file_path]
                return

            # 标记为已处理（在翻译前）
            self.processed_files[file_path] = time.time()

        # 执行翻译（释放锁后）
        try:
            self.translator.translate_subtitle_file(file_path)
        finally:
            with self.processing_lock:
                if file_path in self.pending_files:
                    del self.pending_files[file_path]

    def _cleanup_processed(self):
        now = time.time()
        expired = [k for k, v in self.processed_files.items() if now - v > self.max_age]
        for k in expired:
            del self.processed_files[k]

def main():
    api_key = os.environ.get('API_KEY')
    proxy_url = os.environ.get('PROXY_URL')
    model = os.environ.get('MODEL', 'gpt-4o-mini')

    watch_dirs = [
        os.environ.get('MOVIES_DIR', '/mnt/user/media/media/movies'),
        os.environ.get('TV_DIR', '/mnt/user/media/media/tv')
    ]

    custom_dirs = os.environ.get('CUSTOM_DIRS', '')
    if custom_dirs:
        custom_dir_list = [d.strip() for d in custom_dirs.split(',') if d.strip()]
        watch_dirs.extend(custom_dir_list)

    max_workers = int(os.environ.get('MAX_WORKERS', '10'))
    web_port = int(os.environ.get('WEB_PORT', '8095'))
    target_lang = os.environ.get('TARGET_LANG', 'zh')

    if not api_key:
        logger.error("未设置API_KEY环境变量")
        state.add_log('ERROR', '未设置API_KEY环境变量')
        sys.exit(1)

    subtitle_extensions = ['.srt', '.ass', '.ssa', '.vtt']

    translator = SubtitleTranslator(api_key, proxy_url, model, max_workers, target_lang)

    event_handler = SubtitleEventHandler(translator, subtitle_extensions)
    observer = Observer()

    for watch_dir in watch_dirs:
        if os.path.exists(watch_dir):
            observer.schedule(event_handler, watch_dir, recursive=True)
            logger.info(f"开始监控目录: {watch_dir}")
            state.add_log('INFO', f'开始监控目录: {watch_dir}')
        else:
            logger.warning(f"目录不存在，跳过监控: {watch_dir}")
            state.add_log('WARNING', f'目录不存在: {watch_dir}')

    observer.start()

    # 启动 Web UI
    web_thread = threading.Thread(target=start_web_server, args=[web_port], daemon=True)
    web_thread.start()

    logger.info(f"字幕翻译服务已启动，监控 {len(watch_dirs)} 个目录")
    logger.info(f"Web UI 访问地址: http://localhost:{web_port}")
    state.add_log('INFO', f'服务启动成功，Web UI: http://localhost:{web_port}')

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("正在关闭服务...")
        state.add_log('INFO', '服务正在关闭...')
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
