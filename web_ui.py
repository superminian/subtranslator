#!/usr/bin/env python3
import os
import json
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 全局状态管理
class AppState:
    def __init__(self):
        self.stats = {
            'total_translated': 0,
            'total_failed': 0,
            'in_progress': 0,
            'start_time': datetime.now().isoformat()
        }
        self.recent_files = []
        self.config = {}
        self.logs = []
        self.translation_logs = []
        self.translation_content_logs = []  # 新增：翻译内容日志
        self.max_logs = 1000
        self.max_translation_logs = 200
        self.max_translation_content_logs = 500  # 翻译内容日志最多 500 条
        self.max_log_age_hours = 24
        self.lock = threading.Lock()

    def add_log(self, level, message):
        with self.lock:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'level': level,
                'message': message
            }
            self.logs.append(log_entry)

            # 清理过期日志
            cutoff_time = datetime.now().timestamp() - (self.max_log_age_hours * 3600)
            self.logs = [
                log for log in self.logs
                if datetime.fromisoformat(log['timestamp']).timestamp() > cutoff_time
            ]

            # 限制日志数量
            if len(self.logs) > self.max_logs:
                self.logs = self.logs[-self.max_logs:]

    def add_translation_log(self, file_path, status, message='', progress=0):
        """添加翻译进度日志"""
        with self.lock:
            # 查找是否已存在该文件的日志
            existing_log = None
            for log in self.translation_logs:
                if log['file_path'] == file_path:
                    existing_log = log
                    break

            if existing_log:
                # 更新现有日志
                existing_log['status'] = status
                existing_log['message'] = message
                existing_log['progress'] = progress
                existing_log['updated_at'] = datetime.now().isoformat()
            else:
                # 创建新日志
                log_entry = {
                    'file_path': file_path,
                    'status': status,
                    'message': message,
                    'progress': progress,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                self.translation_logs.insert(0, log_entry)

            # 限制数量
            if len(self.translation_logs) > self.max_translation_logs:
                self.translation_logs = self.translation_logs[:self.max_translation_logs]

    def add_translation_content_log(self, file_path, original_text, translated_text):
        """添加翻译内容日志"""
        with self.lock:
            log_entry = {
                'file_path': file_path,
                'original': original_text,
                'translated': translated_text,
                'timestamp': datetime.now().isoformat()
            }
            self.translation_content_logs.insert(0, log_entry)

            # 限制数量
            if len(self.translation_content_logs) > self.max_translation_content_logs:
                self.translation_content_logs = self.translation_content_logs[:self.max_translation_content_logs]

    def add_file(self, file_path, status, message=''):
        with self.lock:
            file_entry = {
                'path': file_path,
                'status': status,
                'message': message,
                'timestamp': datetime.now().isoformat()
            }
            self.recent_files.insert(0, file_entry)
            if len(self.recent_files) > 100:
                self.recent_files = self.recent_files[:100]

    def update_stats(self, key, value):
        with self.lock:
            if key in self.stats:
                self.stats[key] = value

    def increment_stat(self, key):
        with self.lock:
            if key in self.stats:
                self.stats[key] += 1

state = AppState()

# API 路由
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/api/stats')
def get_stats():
    with state.lock:
        return jsonify(state.stats)

@app.route('/api/files')
def get_files():
    with state.lock:
        return jsonify(state.recent_files)

@app.route('/api/logs')
def get_logs():
    limit = request.args.get('limit', 100, type=int)
    with state.lock:
        return jsonify(state.logs[-limit:])

@app.route('/api/translation-logs')
def get_translation_logs():
    with state.lock:
        return jsonify(state.translation_logs)

@app.route('/api/translation-content-logs')
def get_translation_content_logs():
    with state.lock:
        return jsonify(state.translation_content_logs)

@app.route('/api/config', methods=['GET'])
def get_config():
    config = {
        'API_KEY': '***' if os.environ.get('API_KEY') else '',
        'PROXY_URL': os.environ.get('PROXY_URL', ''),
        'MODEL': os.environ.get('MODEL', 'gpt-4o-mini'),
        'MOVIES_DIR': os.environ.get('MOVIES_DIR', '/mnt/user/media/media/movies'),
        'TV_DIR': os.environ.get('TV_DIR', '/mnt/user/media/media/tv'),
        'CUSTOM_DIRS': os.environ.get('CUSTOM_DIRS', ''),
        'MAX_WORKERS': os.environ.get('MAX_WORKERS', '10'),
        'LOG_LEVEL': os.environ.get('LOG_LEVEL', 'INFO')
    }
    return jsonify(config)

@app.route('/api/config', methods=['POST'])
def update_config():
    try:
        data = request.json
        config_file = '/config/settings.json'

        # 保存配置到文件
        with open(config_file, 'w') as f:
            json.dump(data, f, indent=2)

        state.add_log('INFO', '配置已更新，需要重启容器生效')
        return jsonify({'success': True, 'message': '配置已保存，请重启容器使配置生效'})
    except Exception as e:
        state.add_log('ERROR', f'配置更新失败: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500

def start_web_server(port=8095):
    from waitress import serve
    import logging

    # 配置 waitress 日志
    waitress_logger = logging.getLogger('waitress')
    waitress_logger.setLevel(logging.WARNING)

    logger = logging.getLogger('SubtitleTranslator')
    logger.info(f'启动生产级 Web 服务器，端口: {port}')

    serve(app, host='0.0.0.0', port=port, threads=4)
