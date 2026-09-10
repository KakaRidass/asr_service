# ============================================
# 录音转写系统 · CLI 客户端
# ============================================

一个用纯 Python 写的命令行交互界面，对接 FastAPI 后端。

## 安装

```bash
cd cli
pip install -r requirements.txt
```

## 启动

```bash
# 默认连接 http://127.0.0.1:8003（docker-compose 把后端容器的 8000 映射到宿主机 8003）
python cli.py

# 自定义后端地址（PowerShell）
$env:RECORDING_API_BASE="http://127.0.0.1:8001"; python cli.py

# 自定义后端地址（CMD）
set RECORDING_API_BASE=http://127.0.0.1:8001 && python cli.py
```

## 功能菜单

| 编号 | 功能         | 说明                                 |
|------|--------------|--------------------------------------|
| 1    | 健康检查     | GET /v1/health                       |
| 2    | 上传录音     | POST /v1/recordings（multipart）     |
| 3    | 录音列表     | GET /v1/recordings?page=&page_size=  |
| 4    | 录音详情     | GET /v1/recordings/{id}              |
| 5    | 任务状态     | GET /v1/tasks/{id}                   |
| 6    | 重试任务     | POST /v1/tasks/{id}/retry            |
| 0    | 退出         | -                                    |

## 状态着色

CLI 会按任务状态自动着色：
- `pending` 灰
- `transcribing` 黄
- `summarizing` 青
- `done` 绿
- `failed` 红

## 在 Docker 里启动交互界面

CLI 是**交互式前台进程**，需要分配 TTY，所以用 `docker compose run` 而非 `up -d`。

### 方式 A：compose profile 启动（推荐）

```powershell
# 1. 启动后端（必须先起）
docker compose up -d db backend

# 2. 拉起 CLI（一次性前台进程，退出即清理）
docker compose --profile cli run --rm cli
```

会看到菜单提示符。`--rm` 保证退出时容器自动删除。

### 方式 B：手动 docker run

```powershell
# 构建镜像
docker build -f cli/Dockerfile -t recording-cli .

# 在 docker-compose 网络里跑
docker run -it --rm `
  --network intern_workspace_recording_net `
  -e RECORDING_API_BASE=http://recording_backend:8000 `
  recording-cli
```

> 网络名 `intern_workspace_recording_net` 由 docker-compose 自动生成，
> 与 `docker compose config` 显示的 `networks.recording_net.name` 一致。

### 方式 C：exec 进已有 backend 容器

```powershell
docker exec -it recording_backend bash
# 容器内手动安装 httpx 并 python -m cli.cli
```

不推荐：需要 backend 镜像里已有 CLI 代码 + httpx。方式 A 是最小可行方案。

## 备注

- 需要后端服务先启动并可访问。
- 文件路径可直接把文件拖到终端里。
- `Ctrl+C` 中断当前操作回到菜单；`Ctrl+D` / `0` 退出。
