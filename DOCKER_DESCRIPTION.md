# SubTranslator - 自动字幕翻译服务

🎬 实时监控媒体目录，自动将外语字幕翻译为中英双语字幕，完美适配 Plex/Jellyfin/Emby 等媒体服务器。

## 特性

- ✅ 实时监控：自动检测新增字幕文件
- 🌐 双语字幕：中文在上，原文在下
- ⚡ 高性能：多线程并发翻译
- 🎯 智能检测：自动跳过已翻译字幕
- 📊 Web UI：现代化监控界面
- 🔄 失败重试：API 调用自动重试
- 🛡️ 稳定可靠：文件稳定性检查、防抖机制

## 支持的 AI 服务

- DeepSeek（推荐，性价比高）
- OpenAI（GPT-4o、GPT-4o-mini）
- 其他 OpenAI 兼容 API

## 支持的字幕格式

SRT、ASS、SSA、WebVTT

## 快速开始

```bash
docker run -d \
  --name subtranslator \
  -p 8095:8095 \
  -v /path/to/config:/config \
  -v /path/to/media:/mnt/user/media \
  -e API_KEY=your-api-key \
  -e PROXY_URL=https://api.deepseek.com/v1/chat/completions \
  -e MODEL=deepseek-chat \
  your-username/subtranslator:latest
```

访问 Web UI: `http://localhost:8095`

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| API_KEY | API 密钥（必需） | - |
| PROXY_URL | API 端点 | DeepSeek API |
| MODEL | 模型名称 | deepseek-chat |
| MOVIES_DIR | 电影目录 | /mnt/user/media/media/movies |
| TV_DIR | 电视剧目录 | /mnt/user/media/media/tv |
| CUSTOM_DIRS | 自定义目录（逗号分隔） | - |
| MAX_WORKERS | 最大并发数 | 10 |
| LOG_LEVEL | 日志级别 | INFO |

## 文档

- GitHub: https://github.com/your-username/subtranslator
- 问题反馈: https://github.com/your-username/subtranslator/issues

## 许可证

MIT License
