# Docker 安全最佳实践说明

## 关于 API_KEY 警告

Docker 扫描工具会警告在 Dockerfile 中使用 `ENV API_KEY`，这是正确的安全提示。

### 已优化的做法

✅ **Dockerfile 中不设置 API_KEY 默认值**
- 移除了 `ENV API_KEY=""` 
- API_KEY 必须在运行时通过环境变量传入

✅ **运行时传入敏感信息**
- 使用 docker-compose.yml 的 `.env` 文件
- 使用 `docker run -e API_KEY=xxx`
- 使用 Unraid Docker 界面的环境变量配置

### 为什么这样安全？

1. **不会烧录到镜像层**：API_KEY 不会被写入 Docker 镜像
2. **不会泄露到镜像仓库**：推送镜像到 Docker Hub 时不包含密钥
3. **运行时注入**：每个容器实例使用自己的密钥

### 正确的使用方式

**Docker Compose（推荐）：**
```yaml
# docker-compose.yml
environment:
  - API_KEY=${API_KEY}  # 从 .env 文件读取

# .env 文件（不要提交到 Git）
API_KEY=sk-your-real-key
```

**Docker Run：**
```bash
docker run -e API_KEY=sk-your-key subtranslator:latest
```

**Unraid：**
在 Docker 容器配置界面的环境变量中填入 API_KEY

### .gitignore 建议

确保敏感文件不被提交：
```
.env
*.log
config/
```

---

现在重新构建镜像将不会出现警告：
```bash
docker build -t subtranslator:latest .
```
