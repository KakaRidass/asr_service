# ============================================
# Docker 部署说明
# ============================================
# 一键启动（开发/演示环境）
# ============================================

# 1. 复制环境变量模板
cp .env.example .env

# 2. 填入 DeepSeek API Key
#    编辑 .env，将 DEEPSEEK_API_KEY 改为你的实际 key
#    （如果只是测试 mock 转写阶段，可以不填，但 LLM 摘要阶段会失败）

# 3. 一键启动（首次启动会拉取镜像，稍等片刻）
docker compose up -d --build

# 4. 验证服务是否启动成功
docker compose ps

#    正常输出：
#    recording_backend   running   (healthy)   0.0.0.0:8000->8000/tcp
#    recording_mysql     running   (healthy)   0.0.0.0:3307->3306/tcp

# 5. 访问 API 文档
open http://127.0.0.1:8000/docs

# 6. 查看日志
docker compose logs -f backend

# ============================================
# 一键停止并清理
# ============================================
docker compose down        # 停止容器（保留数据卷）
docker compose down -v     # 停止并删除数据卷（数据会丢失！）

# ============================================
# 重新构建（代码变更后）
# ============================================
docker compose up -d --build backend

# ============================================
# 使用本地 MySQL（而非 Docker MySQL）
# ============================================
# 如果你已经有本地 MySQL，可以只启动 backend：
#
#   1. 确保本地 MySQL 中有 recording_db 数据库：
#      CREATE DATABASE recording_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
#
#   2. 修改 .env 中的 DATABASE_URL：
#      DATABASE_URL=mysql+aiomysql://root:your_password@127.0.0.1:3306/recording_db
#
#   3. 只构建并运行 backend：
#      docker compose up -d --build backend
#
# ============================================
