# ============================================
# 文件: backend/Dockerfile
# 功能: FastAPI 后端的 Docker 镜像构建配置。
#      基于 Python 3.10-slim，减少镜像体积。
# ============================================
FROM python:3.10-slim AS base

# 防止 Python 缓冲输出导致日志延迟
ENV PYTHONUNBUFFERED=1
# 国内 pip 镜像（加速安装）
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# ---------- 构建阶段 ----------
FROM base AS builder

WORKDIR /app

# 安装构建依赖（用于编译 aiomysql 等 C 扩展）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmariadb-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------- 运行阶段 ----------
FROM base

WORKDIR /app

# 仅复制已安装好的 site-packages（体积最小化）
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 创建非 root 用户（安全最佳实践）
RUN groupadd -r appgroup && useradd -r -g appgroup appuser \
    && mkdir -p /app/uploads /app/logs \
    && chown -R appuser:appgroup /app/uploads /app/logs

# 复制应用代码
COPY --chown=appuser:appgroup app/ ./app/

# 切换到非 root 用户运行
USER appuser

# 端口
EXPOSE 8000

# 健康检查（使用 uvicorn 内置健康端点）
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health')" || exit 1

# 启动命令
# --proxy-headers: 支持 Nginx 反代时传递真实客户端 IP
# --forwarded-allow-ips='*': 信任 X-Forwarded-For 头
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
