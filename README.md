# SubTranslator

自动字幕翻译服务 - 实时监控媒体目录，自动将外语字幕翻译为双语字幕，适配 Plex/Jellyfin/Emby 等媒体服务器。

## 功能特性

- 实时监控：自动检测新增的字幕文件
- 双语字幕：翻译后保留原文，译文在上，原文在下
- 多语言支持：可配置目标语言（中文、日语、韩语、法语等 12 种语言）
- 高性能：支持多线程并发翻译
- 智能检测：基于比例阈值自动跳过已翻译的双语字幕
- 失败重试：API 调用失败自动重试
- Web UI：现代化监控界面，实时查看翻译状态
- API 认证：可选的 Admin Token 保护配置接口
- 内存管理：已处理文件记录自动过期清理（1 小时 TTL）

## 支持的字幕格式

- SRT (.srt)
- ASS (.ass)
- SSA (.ssa)
- WebVTT (.vtt)

## 快速开始

### Docker Compose（推荐）

1. 创建 `.env` 文件：

```env
API_KEY=sk-your-api-key
PROXY_URL=https://api.deepseek.com/v1/chat/completions
MODEL=deepseek-chat
MOVIES_DIR=/mnt/user/media/media/movies
TV_DIR=/mnt/user/media/media/tv
CUSTOM_DIRS=
MAX_WORKERS=10
LOG_LEVEL=INFO
WEB_PORT=8095
TARGET_LANG=zh
ADMIN_TOKEN=your-secret-token
```

2. 拉取镜像并启动服务：

```console
docker compose pull
docker compose up -d
```

3. 访问 Web UI：`http://your-server-ip:8095`

### Docker Run

```bash
docker run -d \
  --name subtranslator \
  -p 8095:8095 \
  -v /path/to/config:/config \
  -v /path/to/media:/mnt/user/media \
  -e API_KEY=your-api-key \
  -e PROXY_URL=https://api.deepseek.com/v1/chat/completions \
  -e MODEL=deepseek-chat \
  -e TARGET_LANG=zh \
  -e ADMIN_TOKEN=your-secret-token \
  cyberfrostfall/subtranslator:latest
```

## 环境变量

| 变量 | 说明 | 默认值 | 必需 |
|------|------|--------|------|
| `API_KEY` | API 密钥 | - | 是 |
| `PROXY_URL` | API 端点 | `https://api.deepseek.com/v1/chat/completions` | 否 |
| `MODEL` | 模型名称 | `deepseek-chat` | 否 |
| `TARGET_LANG` | 目标翻译语言 | `zh` | 否 |
| `MOVIES_DIR` | 电影目录 | `/mnt/user/media/media/movies` | 否 |
| `TV_DIR` | 电视剧目录 | `/mnt/user/media/media/tv` | 否 |
| `CUSTOM_DIRS` | 自定义监控目录（逗号分隔） | - | 否 |
| `MAX_WORKERS` | 最大并发线程数 | `10` | 否 |
| `LOG_LEVEL` | 日志级别 (DEBUG/INFO/WARNING/ERROR) | `INFO` | 否 |
| `WEB_PORT` | Web UI 端口 | `8095` | 否 |
| `ADMIN_TOKEN` | 配置接口认证 Token（留空则不启用认证） | - | 否 |

设置 `ADMIN_TOKEN` 后，保存配置时浏览器会提示输入 Token，并仅在当前浏览器会话中保存；Token 不会嵌入页面或写入 URL。

### 支持的目标语言

| 代码 | 语言 | 代码 | 语言 |
|------|------|------|------|
| `zh` | 中文 | `fr` | 法语 |
| `en` | 英语 | `de` | 德语 |
| `ja` | 日语 | `es` | 西班牙语 |
| `ko` | 韩语 | `it` | 意大利语 |
| `pt` | 葡萄牙语 | `ru` | 俄语 |
| `ar` | 阿拉伯语 | `th` | 泰语 |

### 推荐模型

- **DeepSeek**（推荐）：性价比高，中文翻译质量好
- **GPT-4o-mini**：速度快，质量稳定
- **GPT-4o**：质量最高，成本较高
- 其他 OpenAI 兼容 API 均可使用

## Web UI

访问 `http://your-server:8095` 可以：

- 实时统计：查看翻译成功/失败数量、正在处理的文件、运行时长
- 文件列表：查看最近翻译的文件及状态
- 翻译内容：实时查看翻译进度和内容
- 系统日志：实时查看服务运行日志
- 配置管理：在线修改配置（设置 `ADMIN_TOKEN` 后需认证）

## 工作原理

1. 服务启动后监控指定目录
2. 检测到新的字幕文件（不含 `.{TARGET_LANG}.` 的文件）
3. 等待文件写入完成（防止翻译未下载完的文件）
4. 检查是否已是双语字幕（中外文各占 20% 以上则跳过）
5. 使用 AI API 翻译字幕内容
6. 保存为双语字幕文件（原文件名 + `.{TARGET_LANG}.` 后缀）

## CI/CD

项目使用 GitHub Actions 自动验证和发布镜像：

- Pull Request：构建 `linux/amd64` + `linux/arm64` 双平台镜像，但不推送。
- 推送到 `main`：发布 `latest` 和 `sha-<完整提交 SHA>`。
- 推送版本标签（如 `v1.2.3`）：发布 `1.2.3`、`1.2` 和 `sha-<完整提交 SHA>`。
- 发布镜像包含 OCI 元数据、构建来源证明（provenance）和 SBOM。

镜像地址：`cyberfrostfall/subtranslator`

生产环境建议使用版本标签（例如 `cyberfrostfall/subtranslator:1.1.0`）固定版本；`latest` 会跟随 `main` 持续更新。

## 故障排查

### 容器无法启动
- 检查 `API_KEY` 是否正确设置
- 检查目录映射是否正确
- 查看容器日志：`docker logs subtranslator`

### 字幕未被翻译
- 确认文件在监控目录中
- 检查文件扩展名是否支持
- 查看 Web UI 日志页面
- 确认文件名不包含 `.zh.`（已翻译文件会被跳过）

### API 调用失败
- 检查 API Key 是否有效
- 检查网络连接
- 如使用代理，确认 `PROXY_URL` 正确

## 许可证

MIT License
