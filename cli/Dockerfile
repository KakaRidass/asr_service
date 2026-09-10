# ============================================
# 文件: cli/Dockerfile
# 功能: 把 CLI 客户端打包为最小可运行的镜像。
#      用于 docker run -it / docker exec 进入交互式菜单。
#
# 构建:
#   docker build -f cli/Dockerfile -t recording-cli .
#
# 启动（与 backend 同网络）:
#   docker run -it --rm \
#     --network intern_workspace_recording_net \
#     -e RECORDING_API_BASE=http://recording_backend:8000 \
#     recording-cli
# ============================================

FROM python:3.11-slim

# 关闭 Python 输出缓冲，保证交互式菜单的 print 立即可见
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 仅装 CLI 需要的依赖，减小镜像体积
RUN pip install --no-cache-dir "httpx>=0.27.0"

# 复制 CLI 源码
COPY cli/ /app/cli/

# 默认指向 docker-compose 网络内的 backend 服务名
ENV RECORDING_API_BASE=http://recording_backend:8000

# 启动 CLI 菜单
CMD ["python", "-m", "cli.cli"]
