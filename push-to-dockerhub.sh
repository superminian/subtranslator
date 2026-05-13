#!/bin/bash

# Docker Hub 推送脚本
# 使用方法: ./push-to-dockerhub.sh <your-dockerhub-username>

set -e

if [ -z "$1" ]; then
    echo "错误: 请提供 Docker Hub 用户名"
    echo "使用方法: ./push-to-dockerhub.sh <your-dockerhub-username>"
    exit 1
fi

DOCKERHUB_USERNAME=$1
IMAGE_NAME="subtranslator"
VERSION="latest"

echo "=========================================="
echo "Docker Hub 推送脚本"
echo "=========================================="
echo "用户名: $DOCKERHUB_USERNAME"
echo "镜像名: $IMAGE_NAME"
echo "版本: $VERSION"
echo "=========================================="

# 1. 构建镜像
echo ""
echo "步骤 1/4: 构建 Docker 镜像..."
docker build -t $IMAGE_NAME:$VERSION .

# 2. 打标签
echo ""
echo "步骤 2/4: 为镜像打标签..."
docker tag $IMAGE_NAME:$VERSION $DOCKERHUB_USERNAME/$IMAGE_NAME:$VERSION

# 可选：同时打版本号标签
# docker tag $IMAGE_NAME:$VERSION $DOCKERHUB_USERNAME/$IMAGE_NAME:v2.0.0

# 3. 登录 Docker Hub（如果未登录）
echo ""
echo "步骤 3/4: 登录 Docker Hub..."
echo "请输入 Docker Hub 密码:"
docker login -u $DOCKERHUB_USERNAME

# 4. 推送镜像
echo ""
echo "步骤 4/4: 推送镜像到 Docker Hub..."
docker push $DOCKERHUB_USERNAME/$IMAGE_NAME:$VERSION

# 可选：推送版本号标签
# docker push $DOCKERHUB_USERNAME/$IMAGE_NAME:v2.0.0

echo ""
echo "=========================================="
echo "✅ 推送完成！"
echo "=========================================="
echo "镜像地址: $DOCKERHUB_USERNAME/$IMAGE_NAME:$VERSION"
echo ""
echo "在 Unraid 中使用:"
echo "Repository: $DOCKERHUB_USERNAME/$IMAGE_NAME:latest"
echo "=========================================="
