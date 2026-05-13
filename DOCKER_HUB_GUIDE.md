# Docker Hub 推送指南

## 前置准备

1. **注册 Docker Hub 账号**
   - 访问 https://hub.docker.com/
   - 注册账号（免费）

2. **在 Unraid 上登录 Docker Hub**
   ```bash
   docker login
   # 输入用户名和密码
   ```

---

## 方法一：使用自动化脚本（推荐）

### 1. 运行推送脚本

```bash
cd /mnt/user/appdata/subtranslator
./push-to-dockerhub.sh <your-dockerhub-username>
```

**示例：**
```bash
./push-to-dockerhub.sh johndoe
```

脚本会自动完成：
- ✅ 构建镜像
- ✅ 打标签
- ✅ 登录 Docker Hub
- ✅ 推送镜像

---

## 方法二：手动推送

### 1. 构建镜像

```bash
cd /mnt/user/appdata/subtranslator
docker build -t subtranslator:latest .
```

### 2. 打标签

```bash
# 替换 <username> 为你的 Docker Hub 用户名
docker tag subtranslator:latest <username>/subtranslator:latest

# 可选：同时打版本号标签
docker tag subtranslator:latest <username>/subtranslator:v2.0.0
```

**示例：**
```bash
docker tag subtranslator:latest johndoe/subtranslator:latest
docker tag subtranslator:latest johndoe/subtranslator:v2.0.0
```

### 3. 登录 Docker Hub

```bash
docker login
# 输入用户名和密码
```

### 4. 推送镜像

```bash
docker push <username>/subtranslator:latest

# 如果打了版本号标签，也推送版本号
docker push <username>/subtranslator:v2.0.0
```

**示例：**
```bash
docker push johndoe/subtranslator:latest
docker push johndoe/subtranslator:v2.0.0
```

---

## 在 Unraid 上使用 Docker Hub 镜像

### 方法 1：Docker 界面

1. 进入 Unraid Docker 页面
2. 点击 "Add Container"
3. **Repository** 填写：`<username>/subtranslator:latest`
4. 其他配置按之前的参数列表填写

### 方法 2：docker-compose.yml

修改 `docker-compose.yml`：

```yaml
services:
  subtranslator:
    image: <username>/subtranslator:latest  # 改为你的 Docker Hub 镜像
    container_name: subtranslator
    restart: unless-stopped
    # ... 其他配置保持不变
```

然后运行：
```bash
docker-compose pull  # 拉取最新镜像
docker-compose up -d
```

---

## 更新镜像

### 推送新版本

```bash
cd /mnt/user/appdata/subtranslator

# 重新构建
docker build -t subtranslator:latest .

# 打标签
docker tag subtranslator:latest <username>/subtranslator:latest
docker tag subtranslator:latest <username>/subtranslator:v2.1.0  # 新版本号

# 推送
docker push <username>/subtranslator:latest
docker push <username>/subtranslator:v2.1.0
```

### 在 Unraid 上更新

```bash
docker pull <username>/subtranslator:latest
docker stop subtranslator
docker rm subtranslator
docker-compose up -d
```

或在 Unraid Docker 界面点击 "Force Update"

---

## 镜像信息

推送成功后，你的镜像地址：
- **Docker Hub**: `https://hub.docker.com/r/<username>/subtranslator`
- **拉取命令**: `docker pull <username>/subtranslator:latest`

---

## 常见问题

### Q: 推送失败，提示 "denied: requested access to the resource is denied"
**A:** 检查是否已登录 Docker Hub：
```bash
docker login
```

### Q: 如何设置镜像为公开/私有？
**A:** 登录 Docker Hub 网站，进入仓库设置，选择 Public 或 Private

### Q: 如何删除 Docker Hub 上的镜像？
**A:** 登录 Docker Hub 网站，进入仓库，点击 "Settings" → "Delete repository"

### Q: 推送速度慢怎么办？
**A:** 
- 使用国内 Docker Hub 镜像加速
- 或推送到阿里云容器镜像服务
- 或使用 GitHub Container Registry

---

## 推送到其他镜像仓库

### 阿里云容器镜像服务

```bash
# 登录阿里云
docker login --username=<your-aliyun-username> registry.cn-hangzhou.aliyuncs.com

# 打标签
docker tag subtranslator:latest registry.cn-hangzhou.aliyuncs.com/<namespace>/subtranslator:latest

# 推送
docker push registry.cn-hangzhou.aliyuncs.com/<namespace>/subtranslator:latest
```

### GitHub Container Registry

```bash
# 登录 GitHub
echo $GITHUB_TOKEN | docker login ghcr.io -u <username> --password-stdin

# 打标签
docker tag subtranslator:latest ghcr.io/<username>/subtranslator:latest

# 推送
docker push ghcr.io/<username>/subtranslator:latest
```

---

## 版本管理建议

推荐使用语义化版本号：
- `latest` - 最新版本
- `v2.0.0` - 主版本号.次版本号.修订号
- `v2.0` - 主版本号.次版本号
- `v2` - 主版本号

**示例：**
```bash
docker tag subtranslator:latest johndoe/subtranslator:latest
docker tag subtranslator:latest johndoe/subtranslator:v2.0.0
docker tag subtranslator:latest johndoe/subtranslator:v2.0
docker tag subtranslator:latest johndoe/subtranslator:v2

docker push johndoe/subtranslator:latest
docker push johndoe/subtranslator:v2.0.0
docker push johndoe/subtranslator:v2.0
docker push johndoe/subtranslator:v2
```
