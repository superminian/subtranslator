import logging
import os
import secrets
import threading
from datetime import UTC, datetime
from functools import wraps

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from config_manager import ConfigError, load_config, save_config

app = Flask(__name__)
cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if cors_origins:
    CORS(app, origins=cors_origins)

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if ADMIN_TOKEN:
            token = request.headers.get("X-Admin-Token", "")
            if not secrets.compare_digest(token, ADMIN_TOKEN):
                return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ADMIN_TOKEN:
            return jsonify(
                {"error": "ADMIN_TOKEN is required to modify configuration"}
            ), 503
        token = request.headers.get("X-Admin-Token", "")
        if not secrets.compare_digest(token, ADMIN_TOKEN):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


# 全局状态管理
class AppState:
    def __init__(self):
        self.stats = {
            "total_translated": 0,
            "total_failed": 0,
            "in_progress": 0,
            "start_time": datetime.now(UTC).isoformat(),
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
        self.health_checker = None

    def add_log(self, level, message):
        with self.lock:
            log_entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": level,
                "message": message,
            }
            self.logs.append(log_entry)

            # 清理过期日志
            cutoff_time = datetime.now(UTC).timestamp() - (
                self.max_log_age_hours * 3600
            )
            self.logs = [
                log
                for log in self.logs
                if datetime.fromisoformat(log["timestamp"]).timestamp() > cutoff_time
            ]

            # 限制日志数量
            if len(self.logs) > self.max_logs:
                self.logs = self.logs[-self.max_logs :]

    def add_translation_log(self, file_path, status, message="", progress=0):
        """添加翻译进度日志"""
        with self.lock:
            # 查找是否已存在该文件的日志
            existing_log = None
            for log in self.translation_logs:
                if log["file_path"] == file_path:
                    existing_log = log
                    break

            if existing_log:
                # 更新现有日志
                existing_log["status"] = status
                existing_log["message"] = message
                existing_log["progress"] = progress
                existing_log["updated_at"] = datetime.now(UTC).isoformat()
            else:
                # 创建新日志
                log_entry = {
                    "file_path": file_path,
                    "status": status,
                    "message": message,
                    "progress": progress,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
                self.translation_logs.insert(0, log_entry)

            # 限制数量
            if len(self.translation_logs) > self.max_translation_logs:
                self.translation_logs = self.translation_logs[
                    : self.max_translation_logs
                ]

    def add_translation_content_log(self, file_path, original_text, translated_text):
        """添加翻译内容日志"""
        with self.lock:
            log_entry = {
                "file_path": file_path,
                "original": original_text,
                "translated": translated_text,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self.translation_content_logs.insert(0, log_entry)

            # 限制数量
            if len(self.translation_content_logs) > self.max_translation_content_logs:
                self.translation_content_logs = self.translation_content_logs[
                    : self.max_translation_content_logs
                ]

    def add_file(self, file_path, status, message=""):
        with self.lock:
            file_entry = {
                "path": file_path,
                "status": status,
                "message": message,
                "timestamp": datetime.now(UTC).isoformat(),
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

    def decrement_stat(self, key):
        with self.lock:
            if key in self.stats:
                self.stats[key] = max(0, self.stats[key] - 1)

    def set_health_checker(self, checker):
        with self.lock:
            self.health_checker = checker

    def is_healthy(self):
        with self.lock:
            checker = self.health_checker
        return bool(checker and checker())


state = AppState()


# API 路由
@app.route("/")
def index():
    return render_template("index.html", admin_token_required=bool(ADMIN_TOKEN))


@app.route("/health")
def health():
    if state.is_healthy():
        return jsonify({"status": "healthy"}), 200
    return jsonify({"status": "starting_or_unhealthy"}), 503


@app.route("/api/stats")
def get_stats():
    with state.lock:
        return jsonify(state.stats)


@app.route("/api/files")
@require_auth
def get_files():
    with state.lock:
        return jsonify(state.recent_files)


@app.route("/api/logs")
@require_auth
def get_logs():
    limit = min(max(request.args.get("limit", 100, type=int), 1), 500)
    with state.lock:
        return jsonify(state.logs[-limit:])


@app.route("/api/translation-logs")
@require_auth
def get_translation_logs():
    with state.lock:
        return jsonify(state.translation_logs)


@app.route("/api/translation-content-logs")
@require_auth
def get_translation_content_logs():
    with state.lock:
        return jsonify(state.translation_content_logs)


@app.route("/api/config", methods=["GET"])
@require_auth
def get_config():
    try:
        config = load_config()
        config["API_KEY"] = "***" if config["API_KEY"] else ""
        return jsonify(config)
    except ConfigError as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/config", methods=["POST"])
@require_admin
def update_config():
    try:
        data = request.get_json(silent=True)
        save_config(data)

        state.add_log("INFO", "配置已更新，需要重启容器生效")
        return jsonify({"success": True, "message": "配置已保存，请重启容器使配置生效"})
    except ConfigError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except OSError as exc:
        state.add_log("ERROR", f"配置更新失败: {exc}")
        return jsonify({"success": False, "message": "配置文件写入失败"}), 500


def start_web_server(port=8095):
    from waitress import serve

    # 配置 waitress 日志
    waitress_logger = logging.getLogger("waitress")
    waitress_logger.setLevel(logging.WARNING)

    logger = logging.getLogger("SubtitleTranslator")
    logger.info(f"启动生产级 Web 服务器，端口: {port}")

    # 容器端口必须监听所有接口；对外暴露范围由端口映射和认证控制。
    serve(app, host="0.0.0.0", port=port, threads=4)  # nosec B104
