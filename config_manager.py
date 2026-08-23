import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_CONFIG = {
    "API_KEY": "",
    "PROXY_URL": "",
    "MODEL": "",
    "MOVIES_DIR": "/mnt/user/media/media/movies",
    "TV_DIR": "/mnt/user/media/media/tv",
    "CUSTOM_DIRS": "",
    "MAX_WORKERS": "10",
    "API_RETRY_COUNT": "3",
    "LOG_LEVEL": "INFO",
    "WEB_PORT": "8095",
    "TARGET_LANG": "zh",
}

CONFIG_KEYS = frozenset(DEFAULT_CONFIG)


class ConfigError(ValueError):
    pass


def get_config_path():
    return Path(os.environ.get("CONFIG_FILE", "/config/settings.json"))


def _read_saved_config():
    path = get_config_path()
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"无法读取配置文件 {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("配置文件必须是 JSON 对象")

    return {key: value for key, value in data.items() if key in CONFIG_KEYS}


def _validate_config(data):
    config = {}
    for key, value in data.items():
        if key not in CONFIG_KEYS:
            raise ConfigError(f"不支持的配置项: {key}")
        if value is None:
            value = ""
        if not isinstance(value, (str, int)):
            raise ConfigError(f"{key} 必须是字符串或整数")
        config[key] = str(value).strip()

    if "MAX_WORKERS" in config:
        try:
            max_workers = int(config["MAX_WORKERS"])
        except ValueError as exc:
            raise ConfigError("MAX_WORKERS 必须是整数") from exc
        if not 1 <= max_workers <= 50:
            raise ConfigError("MAX_WORKERS 必须在 1 到 50 之间")
        config["MAX_WORKERS"] = str(max_workers)

    if "API_RETRY_COUNT" in config:
        try:
            api_retry_count = int(config["API_RETRY_COUNT"])
        except ValueError as exc:
            raise ConfigError("API_RETRY_COUNT 必须是整数") from exc
        if not 0 <= api_retry_count <= 10:
            raise ConfigError("API_RETRY_COUNT 必须在 0 到 10 之间")
        config["API_RETRY_COUNT"] = str(api_retry_count)

    if "WEB_PORT" in config:
        try:
            web_port = int(config["WEB_PORT"])
        except ValueError as exc:
            raise ConfigError("WEB_PORT 必须是整数") from exc
        if not 1 <= web_port <= 65535:
            raise ConfigError("WEB_PORT 必须在 1 到 65535 之间")
        config["WEB_PORT"] = str(web_port)

    if config.get("LOG_LEVEL") and config["LOG_LEVEL"] not in {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
    }:
        raise ConfigError("LOG_LEVEL 必须是 DEBUG、INFO、WARNING 或 ERROR")

    proxy_url = config.get("PROXY_URL", "")
    if proxy_url:
        parsed_url = urlparse(proxy_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ConfigError("PROXY_URL 必须是有效的 HTTP 或 HTTPS URL")

    return config


def load_config():
    config = DEFAULT_CONFIG.copy()
    config.update({key: os.environ[key] for key in CONFIG_KEYS if key in os.environ})
    config.update(_read_saved_config())
    return _validate_config(config)


def save_config(updates):
    if not isinstance(updates, dict):
        raise ConfigError("请求内容必须是 JSON 对象")

    unknown_keys = set(updates) - CONFIG_KEYS
    if unknown_keys:
        raise ConfigError(f"不支持的配置项: {', '.join(sorted(unknown_keys))}")

    saved_config = _read_saved_config()
    normalized_updates = dict(updates)

    # 页面用 *** 表示已有密钥；空值或掩码都不应覆盖真实密钥。
    if normalized_updates.get("API_KEY") in {"", "***", None}:
        normalized_updates.pop("API_KEY", None)

    for key in ("PROXY_URL", "MODEL"):
        value = normalized_updates.get(key)
        if key in normalized_updates and (
            value is None or not str(value).strip()
        ):
            raise ConfigError(f"{key} 不能为空")

    saved_config.update(_validate_config(normalized_updates))
    validated_config = _validate_config(saved_config)

    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as config_file:
            json.dump(validated_config, config_file, ensure_ascii=False, indent=2)
            config_file.flush()
            os.fsync(config_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)

    return load_config()
