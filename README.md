# SubTranslator

🎬 自动字幕翻译服务 - 实时监控媒体目录，自动将外语字幕翻译为中英双语字幕

## 功能特性

- ✅ **实时监控**：自动检测新增的字幕文件
- 🌐 **双语字幕**：翻译后保留原文，中文在上，原文在下
- ⚡ **高性能**：支持多线程并发翻译
- 🎯 **智能检测**：自动跳过已翻译的双语字幕
- 🔄 **失败重试**：API 调用失败自动重试
- 📊 **Web UI**：现代化监控界面，实时查看翻译状态
- 🛡️ **稳定可靠**：文件稳定性检查、防抖机制、健康检查

## 支持的字幕格式

- SRT (.srt)
- ASS (.ass)
- SSA (.ssa)
- WebVTT (.vtt)

## 快速开始

### 使用 Docker Compose（推荐）

1. 创建 `.env` 文件：

```env
API_KEY=sk-your-openai-api-key
PROXY_URL=
MODEL=gpt-4o-mini
MOVIES_DIR=/mnt/user/media/media/movies
TV_DIR=/mnt/user/media/media/tv
CUSTOM_DIRS=
MAX_WORKERS=10
LOG_LEVEL=INFO
WEB_PORT=8095
MEDIA_PATH=/mnt/user/media
```

2. 启动服务：

```bash
docker-compose up -d
```

3. 访问 Web UI：

打开浏览器访问 `http://your-server-ip:8095`

### Unraid 部署

1. 在 Unraid 的 Docker 页面点击 "Add Container"

2. 填写以下配置：

**基本设置：**
- Name: `subtranslator`
- Repository: `your-registry/subtranslator:latest`
- Network Type: `bridge`

**端口映射：**
- Container Port: `8095` → Host Port: `8095`

**路径映射：**
- Container Path: `/config` → Host Path: `/mnt/user/appdata/subtranslator`
- Container Path: `/mnt/user/media` → Host Path: `/mnt/user/media`

**环境变量：**
- `API_KEY`: 你的 OpenAI API Key（必需）
- `PROXY_URL`: 自定义 API 端点（可选）
- `MODEL`: `gpt-4o-mini`（推荐）
- `MOVIES_DIR`: `/mnt/user/media/media/movies`
- `TV_DIR`: `/mnt/user/media/media/tv`
- `CUSTOM_DIRS`: 自定义监控目录，逗号分隔（可选）
- `MAX_WORKERS`: `10`
- `LOG_LEVEL`: `INFO`
- `WEB_PORT`: `8095`

3. 点击 "Apply" 启动容器

4. 访问 `http://unraid-ip:8095` 查看监控界面

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 | 必需 |
|------|------|--------|------|
| `API_KEY` | OpenAI API 密钥 | - | ✅ |
| `PROXY_URL` | 自定义 API 端点 | OpenAI 官方 | ❌ |
| `MODEL` | 使用的模型 | `gpt-4o-mini` | ❌ |
| `MOVIES_DIR` | 电影目录 | `/mnt/user/media/media/movies` | ❌ |
| `TV_DIR` | 电视剧目录 | `/mnt/user/media/media/tv` | ❌ |
| `CUSTOM_DIRS` | 自定义监控目录（逗号分隔） | - | ❌ |
| `MAX_WORKERS` | 最大并发线程数 | `10` | ❌ |
| `LOG_LEVEL` | 日志级别 (DEBUG/INFO/WARNING/ERROR) | `INFO` | ❌ |
| `WEB_PORT` | Web UI 端口 | `8095` | ❌ |

### 推荐模型

- **gpt-4o-mini**（推荐）：性价比最高，速度快
- **gpt-4o**：质量更高，成本较高
- **gpt-4-turbo**：平衡选择
- **gpt-3.5-turbo**：最便宜，质量稍低

## Web UI 功能

访问 `http://your-server:8095` 可以：

- 📊 **实时统计**：查看翻译成功/失败数量、正在处理的文件、运行时长
- 📁 **文件列表**：查看最近翻译的文件及状态
- 📋 **系统日志**：实时查看服务运行日志
- ⚙️ **配置管理**：在线修改配置（需重启容器生效）

## 工作原理

1. 服务启动后监控指定目录
2. 检测到新的字幕文件（不含 `.zh.` 的文件）
3. 等待文件写入完成（防止翻译未下载完的文件）
4. 检查是否已是双语字幕（自动跳过）
5. 使用 OpenAI API 翻译字幕内容
6. 保存为双语字幕文件（原文件名 + `.zh.` 后缀）

## 日志管理

Docker 日志已配置自动轮转：
- 单个日志文件最大 10MB
- 保留最近 3 个日志文件
- 应用日志保存在 `/config/subtranslator.log`

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
- 查看日志中的错误信息

### Web UI 无法访问
- 确认端口映射正确
- 检查防火墙设置
- 访问 `http://server-ip:8095/health` 测试健康状态

## 构建镜像

```bash
cd /root/projects/docker/subtranslator
docker build -t subtranslator:latest .
```

## 许可证

MIT License

## 更新日志

### v2.0.0
- ✨ 新增 Web UI 监控界面
- ✨ 新增文件稳定性检查
- ✨ 新增防抖机制
- ✨ 新增失败重试机制
- ✨ 新增双语字幕检测
- ✨ 新增健康检查
- ✨ 优化日志管理
- ✨ 支持自定义监控目录
- 🐛 修复启动脚本路径错误
- 🔧 优化 Docker 配置

## 支持

如有问题或建议，请提交 Issue。
