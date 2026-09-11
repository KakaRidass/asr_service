# 录音转写服务

> 一个本地优先的「**录音上传 → 异步转写（mock） → LLM 摘要**」小服务，
> 用 FastAPI + asyncio + SQLAlchemy 2.0 异步 ORM 实现，配一个零依赖的 Python CLI
> 用于交互式体验。

---

## 目录

1. [项目简介](#1-项目简介)
2. [一键启动](#2-一键启动)
3. [核心功能](#3-核心功能)
4. [架构](#4-架构)
5. [数据模型](#5-数据模型)
6. [API 参考](#6-api-参考)
7. [目录结构](#7-目录结构)
8. [技术取舍](#8-技术取舍)
9. [已知问题与未完成项](#9-已知问题与未完成项)
10. [验证记录与 FAQ](#10-验证记录与-faq)

---

## 1. 项目简介

录音转写服务（recording-transcription-service）是一道后端实习笔试的实现，
目标是把下面这条最小可用链路在本地跑通：

```
上传音频 → 异步转写（mock 5~15s，~20% 失败率）
         → 真实 LLM 摘要（DeepSeek，要求严格 JSON 输出）
         → 客户端轮询 / 重试 / 流式预览
```

### 技术栈一览

| 层 | 选择 |
|---|---|
| 后端 | Python 3.10 · FastAPI 0.111 · uvicorn |
| 异步编排 | asyncio.Queue + Semaphore（无 Celery / Redis） |
| 数据访问 | SQLAlchemy 2.0 异步 ORM |
| 数据库 | MySQL 8.0（Docker 模式） · SQLite（无 Docker fallback） |
| LLM | DeepSeek Chat Completions（兼容 OpenAI 协议，裸 httpx 调用） |
| 转写 | Mock（按题目要求"不需真实 ASR"） |
| 部署 | docker-compose（MySQL + backend，CLI 走 profile） |
| CLI | 纯 Python + httpx，无任何第三方 TUI 依赖 |
| 配置 | pydantic-settings + `.env`，启动 fail-fast 校验 |

### 核心特性

- **7 个 REST 接口** + 1 个 SSE 流式接口，全部覆盖题目 P0 核心功能
- **基于 SHA256 的上传幂等**：同一文件重复上传复用同一 `recording`
- **并发闸**：同时最多处理 3 个任务，其余排队
- **任务状态机**：`pending → transcribing → summarizing → done / failed`
- **失败重试**：仅 `failed` 状态可手动重试（`POST /v1/tasks/{id}/retry`）
- **SSE 流式摘要**：`GET /v1/recordings/{id}/summary/stream`
- **Windows 友好**：CLI 自带 UTF-8 / GBK 编码适配，PowerShell 拖拽中文路径可用

---

## 2. 一键启动

> 推荐使用 **`setup.bat` 或 `setup.ps1`**：脚本会自动判断本机是否有 Docker，
> 有就走 Docker 全栈，没有就走本地 venv + SQLite 的 fallback。

### 方式 A：双击 `setup.bat`（Windows 最省事）

```
1. 在项目根目录双击 setup.bat
2. 弹出窗口后按任意键继续
3. 等待部署完成，最终弹出 CLI 交互窗口
```

为什么需要 `.bat` 包一层？因为右键 PowerShell 脚本用的是**临时控制台**，
脚本出错时窗口会一闪而过，用户看不到堆栈。`.bat` 会先开一个**持久控制台**，
再让 `setup.ps1` 在里面跑，出错也能看到。

### 方式 B：手动跑 `setup.ps1`

```powershell
# 项目根目录
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

脚本会弹窗要求输入 **DeepSeek API Key**（到 https://platform.deepseek.com/ 免费申请），
然后按下面两条分支之一走到底。

#### 分支 1：有 Docker（推荐）

```powershell
# 脚本自动执行：
#   1. 把 Key 写入 backend/.env
#   2. docker compose up -d --build（启动 MySQL + backend）
#   3. 等待 backend Up (healthy)
#   4. 弹出 CLI 窗口
```

启动后访问：

| 用途 | 地址 |
|---|---|
| Swagger UI | http://localhost:8003/docs |
| 健康检查 | http://localhost:8003/v1/health |
| CLI | 脚本自动弹窗 |

停止：

```powershell
docker compose down          # 停容器，保留数据卷
docker compose down -v       # 停容器并清空数据卷
```

#### 分支 2：无 Docker（fallback，自动启用）

`setup.ps1` 检测不到 `docker` 命令时自动切换：

```powershell
# 自动步骤：
#   - 创建 backend/.venv
#   - pip install 后端 + CLI 依赖（清华镜像）
#   - DATABASE_URL 切到 SQLite: sqlite+aiosqlite:///./data/recording.db
#   - python -m scripts.init_sqlite（异步建表）
#   - 后台启动 uvicorn（端口 8001，避开本机 Docker Desktop 占用的 8000）
#   - 弹出 CLI 窗口（自动设 RECORDING_API_BASE=http://127.0.0.1:8001）
```

停止：

```powershell
Get-Process python -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like '*.venv*' } | Stop-Process
```

### 方式 C：完全手动（不用 setup）

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 填 DEEPSEEK_API_KEY；DATABASE_URL 按需切 MySQL/SQLite
python -m scripts.init_sqlite       # 仅 SQLite 模式需要
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# CLI（新窗口）
cd cli
pip install -r requirements.txt
export RECORDING_API_BASE=http://127.0.0.1:8000   # Windows: $env:RECORDING_API_BASE=...
python cli.py
```

---

## 3. 核心功能

### P0 核心（全部完成）

| 题目要求 | 接口 | 状态 |
|---|---|---|
| 上传录音 | `POST /v1/recordings`（multipart，≤50MB，wav/mp3/m4a/aac） | ✅ |
| 异步处理 | `pending → transcribing → summarizing → done` | ✅ |
| Mock 转写（5~15s，~20% 失败） | `MockTranscribe` | ✅ |
| 真实 LLM 摘要（严格 JSON） | `LLMClient.chat` → DeepSeek | ✅ |
| 任务查询 | `GET /v1/tasks/{id}` | ✅ |
| 录音列表（分页，倒序） | `GET /v1/recordings?page=&page_size=` | ✅ |
| 录音详情（含 transcript + summary） | `GET /v1/recordings/{id}` | ✅ |
| 失败重试（仅 failed） | `POST /v1/tasks/{id}/retry` | ✅ |
| 删除录音（含文件 + CASCADE） | `DELETE /v1/recordings/{id}` | ✅ |
| 错误响应结构 + HTTP 状态码 | 全局 `register_exception_handlers` | ✅ |
| 关键路径日志 | `app/core/logging.py` + `app.log` | ✅ |
| 数据库迁移脚本 | `backend/app/db/migrations/001_init.sql` | ✅ |

### 加分项（已完成 / 部分完成）

| 加分项 | 状态 | 实现位置 |
|---|---|---|
| #1 失败自动重试 + 指数退避 | ⚠️ **仅手动重试** | `POST /v1/tasks/{id}/retry` |
| #2 服务重启恢复 | ⚠️ **未实现** | 见 [已知问题 #1](#9-已知问题与未完成项) |
| #3 LLM 流式输出 | ✅ | `GET /v1/recordings/{id}/summary/stream`（SSE） |
| #4 上传幂等 | ✅ | SHA256 唯一索引 + 应用层先查后写 |
| #5 并发控制 | ✅ | `MAX_CONCURRENT_TASKS=3` Semaphore |
| #6 单元 / 集成测试 | ❌ **未完成** | 见 [已知问题 #9](#9-已知问题与未完成项) |
| #7 公网部署 | ❌ **未完成** | - |

---

## 4. 架构

### 4.1 全链路图

```
                  ┌─────────────────────────────────────────────┐
                  │           CLI 客户端 (cli/cli.py)            │
                  │   菜单交互 · httpx · Windows 编码适配        │
                  └──────────────────┬──────────────────────────┘
                                     │ HTTP (multipart / JSON / SSE)
                                     ▼
       ┌─────────────────────────────────────────────────────────────┐
       │              FastAPI 后端 (backend/app/main.py)            │
       │ ┌───────────────┬───────────────────┬─────────────────────┐ │
       │ │ /v1/health    │ /v1/recordings    │ /v1/tasks           │ │
       │ │ 健康检查       │ 上传 / 列表 / 详情 / 流式 / 删除       │ │
       │ └──────┬────────┴─────────┬─────────┴──────────┬─────────┘ │
       │        │                  │                    │           │
       │        ▼                  ▼                    ▼           │
       │   RecordingService   TaskService         PipelineWorker    │
       │   (校验 / 落盘 /      (状态机 CRUD /       (asyncio.Queue + │
       │    SHA256 幂等)       retry / 终态判定)   Semaphore N=3)    │
       │        │                  │                    │           │
       │        └─────── SQLAlchemy 2.0 异步 ORM ──────┘           │
       │                          │                                 │
       └──────────────────────────┼─────────────────────────────────┘
                                  │
                ┌─────────────────┴─────────────────┐
                ▼                                   ▼
   ┌──────────────────────────┐        ┌──────────────────────────────┐
   │  MySQL 8.0  /  SQLite     │        │   DeepSeek LLM (真实 API)    │
   │  recordings · tasks       │        │   POST /v1/chat/completions  │
   │  (docker / 本地双模)      │        │   + chat_stream(SSE)         │
   └──────────────────────────┘        └──────────────────────────────┘
                                                  ▲
                                                  │
                                       ┌──────────┴───────────┐
                                       │   Mock ASR           │
                                       │   5~15s + 20% 失败率  │
                                       │   (transcription)    │
                                       └──────────────────────┘
```

### 4.2 异步流水线状态机

```
   pending ──► transcribing ──► summarizing ──► done
       │            │                │
       │            │                │
       └────────────┴────────────────┴─────► failed   (任意阶段异常)
                                                 │
                                                 ▼
                                       POST /v1/tasks/{id}/retry
                                       (仅 failed → 重新入队)
```

### 4.3 后端模块地图

```
backend/app/
├── main.py              # FastAPI 应用工厂 + lifespan
├── api/v1/              # 路由层（按版本 + 资源拆分）
│   ├── health.py        #   GET  /v1/health
│   ├── recordings.py    #   POST/GET/DELETE /v1/recordings[/...]
│   └── tasks.py         #   GET/POST /v1/tasks/{id}[/retry]
├── services/            # 业务编排层
│   ├── recording_service.py     #   上传 / 幂等 / 列表 / 删除
│   ├── task_service.py          #   任务状态机 / 重试
│   └── transcription_service.py  #   转写 + 摘要流水线
├── workers/
│   └── pipeline_worker.py       # asyncio.Queue + Semaphore 调度
├── clients/
│   └── llm_client.py            # DeepSeek 客户端（chat + chat_stream）
├── models/              # SQLAlchemy 2.0 ORM
│   ├── base.py
│   ├── recording.py
│   └── task.py
├── schemas/             # Pydantic 请求/响应模型
├── core/
│   ├── config.py        # pydantic-settings + validate()
│   ├── exceptions.py    # 自定义异常 + 全局处理器
│   └── logging.py       # stdout + 文件双通道
├── db/
│   ├── session.py       # 异步引擎 + Session 工厂
│   └── migrations/001_init.sql
├── scripts/init_sqlite.py       # SQLite 模式建表脚本
└── utils/               # 文件哈希、音频校验等
```

---

## 5. 数据模型

迁移脚本：`backend/app/db/migrations/001_init.sql`（MySQL）。
SQLite 模式由 `backend/scripts/init_sqlite.py` 异步建表，结构对齐。

### 5.1 `recordings`（录音文件元数据）

| 字段 | 类型 | 约束 / 说明 |
|---|---|---|
| `id` | `CHAR(36)` | 主键，UUID v4 |
| `filename` | `VARCHAR(255)` | 原始文件名（用户上传时的 `upload.filename`） |
| `file_path` | `VARCHAR(512)` | 磁盘存储路径（Docker: `/app/uploads`；本地: `./uploads`） |
| `file_size` | `BIGINT` | 字节数 |
| `file_hash` | `CHAR(64)` | **SHA256，唯一索引**，作为上传幂等键 |
| `mime_type` | `VARCHAR(64)` | 上传时的 MIME 类型 |
| `created_at` | `DATETIME` | 默认 `CURRENT_TIMESTAMP` |
| `updated_at` | `DATETIME` | 自动 `ON UPDATE CURRENT_TIMESTAMP` |

**索引**：
- `PRIMARY KEY (id)`
- `UNIQUE KEY uk_recordings_hash (file_hash)` —— 幂等去重核心
- `KEY idx_recordings_created_at (created_at)` —— 列表按时间倒序分页

**设计取舍**：
- 用 `CHAR(36)` 存 UUID 而非 `BIGINT AUTO_INCREMENT`：避免枚举 + 跨服务引用风险
- 文件本体不入库，仅存 `file_path` 元数据 —— 体量大、不适合塞进关系型数据库
- `file_hash` 唯一约束 + 应用层先查后写：并发同 hash 写入会被唯一索引兜底

### 5.2 `tasks`（处理任务）

| 字段 | 类型 | 约束 / 说明 |
|---|---|---|
| `id` | `CHAR(36)` | 主键，UUID v4 |
| `recording_id` | `CHAR(36)` | 外键 → `recordings.id`，`ON DELETE CASCADE` |
| `status` | `ENUM(...)` | `pending` / `transcribing` / `summarizing` / `done` / `failed` |
| `current_stage` | `VARCHAR(64)` | 当前阶段可读描述（如「摘要生成中」） |
| `error_message` | `TEXT` | 失败原因（仅 `failed` 时填充） |
| `transcript` | `LONGTEXT` | 转写文本 |
| `summary_json` | `JSON` | 摘要结果 `{summary, key_points, todos}` |
| `retry_count` | `INT` | 已重试次数（手动 `/retry` 接口递增） |
| `created_at` | `DATETIME` | 默认 `CURRENT_TIMESTAMP` |
| `updated_at` | `DATETIME` | 自动 `ON UPDATE CURRENT_TIMESTAMP` |

**索引**：
- `PRIMARY KEY (id)`
- `KEY idx_tasks_recording (recording_id)`
- `KEY idx_tasks_status (status)` —— 未来按状态查询（如找所有失败任务）

**设计取舍**：
- 一条 `recording` 可关联多条 `task`：用户手动 `/retry` 时**不删旧 task**，
  新建一条 `pending` 任务，旧的 `failed` 记录保留，便于审计
- `summary_json` 直接用 MySQL 原生 `JSON` 列（SQLite 走 JSON1 兼容路径），
  不再拆 `summary / key_points / todos` 三张子表 —— 摘要结构稳定，避免过度范式化
- `ENUM` 状态机在 schema 层兜底，非法状态在 SQL 层就被拒绝
- `recording.tasks` 关系显式 `order_by=created_at DESC`，确保 `tasks[0]` 永远是最新任务

---

## 6. API 参考

完整可执行的请求样例见 **`backend/api.http`**（VSCode REST Client / IntelliJ HTTP Client 通用）。
下面给出每个接口的契约简表。

### 6.1 健康检查

```
GET /v1/health
→ 200 { "status": "ok", "database": "connected" }
```

### 6.2 上传录音（幂等）

```
POST /v1/recordings        (multipart/form-data, 字段: file)
→ 202 { "recording_id": "...", "task_id": "...", "status": "pending",
        "idempotent_reused": false }     # 二次上传相同文件 → true
```

- 校验：扩展名 ∈ {.wav, .mp3, .m4a, .aac}，大小 ≤ 50MB
- 幂等键：上传前算 SHA256，唯一索引兜底

### 6.3 录音列表（分页，倒序）

```
GET /v1/recordings?page=1&page_size=20
→ 200 { "items": [...], "total": N, "page": 1, "page_size": 20,
        "latest_task_by_recording": { recording_id: task, ... } }
```

### 6.4 录音详情

```
GET /v1/recordings/{id}
→ 200 { ..., "transcript": "...", "tasks": [{ status, summary_json, ... }] }
```

### 6.5 任务状态

```
GET /v1/tasks/{id}
→ 200 { "id": "...", "status": "summarizing", "current_stage": "摘要生成中", ... }
```

### 6.6 失败任务重试

```
POST /v1/tasks/{id}/retry
→ 200 { ..., "status": "pending", "retry_count": N+1 }
→ 409 Conflict（非 failed 状态）
```

### 6.7 删除录音

```
DELETE /v1/recordings/{id}
→ 204 No Content（磁盘文件已删，关联 task CASCADE 清空）
→ 404 Not Found
```

### 6.8 流式摘要预览（SSE）

```
GET /v1/recordings/{id}/summary/stream
→ 200  text/event-stream
   data: {"type":"start"}
   data: {"type":"delta","text":"..."}
   ...
   data: {"type":"done","summary_json":{...}}
```

> 注意：当前每次流式请求都会重新调用 LLM，**不**复用流水线已写好的 `summary_json`
> （见 [已知问题 #3](#9-已知问题与未完成项)）。

### 6.9 错误响应统一结构

```json
{ "error": { "code": "TASK_NOT_FOUND", "message": "task xxx not found",
             "request_id": "uuid" } }
```

| HTTP 状态码 | 典型场景 |
|---|---|
| 400 | 扩展名 / 大小校验失败，参数缺失 |
| 404 | 录音 / 任务不存在 |
| 409 | 状态冲突（非 failed 任务被重试等） |
| 500 | LLM 解析失败、数据库异常等未预期错误 |

---

## 7. 目录结构

```
intern_workspace/
├── README.md                 # 你正在读的这份（项目主文档）
├── docker-compose.yml        # MySQL + backend + cli(profile)
├── setup.bat                 # Windows 启动器（开持久控制台）
├── setup.ps1                 # 真正的一键启动脚本
├── .env.example              # 配置模板（必须提交）
├── .gitignore
│
├── backend/                  # FastAPI 后端
│   ├── Dockerfile
│   ├── api.http              # VSCode REST Client 请求样例
│   ├── requirements.txt
│   ├── README_DOCKER.md      # Docker 部署细节
│   ├── .env.example
│   └── app/
│       ├── main.py
│       ├── api/v1/{health,recordings,tasks}.py
│       ├── services/{recording,task,transcription}_service.py
│       ├── workers/pipeline_worker.py
│       ├── clients/llm_client.py
│       ├── models/{base,recording,task}.py
│       ├── schemas/{common,recording,task}.py
│       ├── core/{config,exceptions,logging}.py
│       ├── db/session.py
│       ├── db/migrations/001_init.sql
│       ├── scripts/init_sqlite.py
│       └── utils/
│
├── cli/                      # 命令行客户端
│   ├── README.md             # CLI 专属文档（菜单、编码适配、Docker 内运行等）
│   ├── cli.py
│   ├── Dockerfile
│   └── requirements.txt
│
└── tests/                    # 测试占位（见已知问题 #9）
    └── fixtures/
```

---

## 8. 技术取舍

| 维度 | 选择 | 理由 | 放弃的备选 |
|---|---|---|---|
| 后端框架 | **FastAPI** | 类型注解 + Pydantic + 异步原生支持；自动 OpenAPI 文档；`StreamingResponse` 实现 SSE 简单直接 | Flask（缺类型 + 异步弱）、Django（重） |
| 异步编排 | **asyncio.Queue + Semaphore** | 项目体量小，没必要引入 Celery / Redis；纯标准库即可拿到「并发闸 + 队列」两件套 | Celery（重，需 broker）、Redis Queue |
| 数据库 | **MySQL 8.0（Docker）/ SQLite（无 Docker）** | MySQL 是生产 / Docker 默认；SQLite 是无 Docker fallback，二选一由 `setup.ps1` 自动切换 | 强绑 MySQL（牺牲无 Docker 用户体验） |
| ORM | **SQLAlchemy 2.0 异步** | 同时支持 MySQL (`aiomysql`) 与 SQLite (`aiosqlite`)，迁移成本为零 | Tortoise ORM（生态较小）、原生 SQL |
| LLM 客户端 | **裸 httpx 调用 DeepSeek** | 避免引入 `openai` SDK 带来的额外依赖；DeepSeek 协议与 OpenAI Chat Completions 完全兼容 | openai SDK（多一层封装、API 字段冗余） |
| 转写 | **Mock（5~15s 随机 + 20% 失败）** | 题目要求「不需接入真实 ASR」，mock 足以模拟真实行为暴露异步流水线问题 | 真实 ASR（成本高、超出题目范围） |
| LLM | **DeepSeek** | 国内可直连、价格低、中文能力好；与 OpenAI 协议兼容 | 智谱 / 通义千问 / Ollama（题目的可行选项） |
| CLI | **纯 Python + httpx** | 不依赖任何第三方 TUI 库，`input/print` 即可；Windows 编码问题在 `cli.py` 内部打补丁 | `click` / `rich` / `prompt_toolkit`（过度设计） |
| 部署 | **docker-compose** | 一键起 MySQL + backend + uploads 数据卷；`depends_on: condition: service_healthy` 兜底启动顺序 | Kubernetes（杀鸡用牛刀） |
| 配置管理 | **pydantic-settings + .env** | 类型安全的 Settings；启动时 `validate()` 做 fail-fast，避免运行时才发现 Key 缺失 | 直接 `os.getenv`（无类型校验） |

---

## 9. 已知问题与未完成项

| # | 项目 | 现状 | 影响 |
|---|---|---|---|
| 1 | **服务重启后任务不恢复** | 任务状态持久化在 MySQL/SQLite，但 `PipelineWorker` 启动时**不会**扫描 `status IN ('pending','transcribing','summarizing')` 的任务并重新入队 | 正在处理中的任务会卡在中间状态，需手动调 `POST /v1/tasks/{id}/retry` |
| 2 | **失败不会自动重试** | 当前 `retry_count` 仅在手动 `/retry` 接口递增；转写 / 摘要阶段失败后**直接置 `failed`**，没有指数退避重试 | 偶发抖动需要用户手动重试；题目加分项 #1 未实现 |
| 3 | **Stream 摘要不落库** | `GET /v1/recordings/{id}/summary/stream` 每次都会重新调用 LLM 流式生成，不复用流水线已写好的 `summary_json` | 流式预览会**额外消耗 token**，不能用于成本敏感场景 |
| 4 | **MySQL 初始迁移只支持「干净卷」** | `001_init.sql` 通过 `docker-entrypoint-initdb.d/` 执行，**只在数据卷首次创建时运行**；已存在的库不会自动应用迁移 | 改表结构需要手动 `docker compose down -v` 或手工执行 SQL |
| 5 | **缺鉴权 / 用户体系** | 题目明确「不考察用户注册 / 登录」，故所有接口裸奔 | 仅适合本地 / 内部演示，**不可直接公网部署** |
| 6 | **`pool_pre_ping` 关闭** | SQLAlchemy 2.0.30 与 `aiomysql 0.3.x` 的 `do_ping` 签名不兼容（见 `app/db/session.py` 的 TODO），暂未开启连接探活 | 长时间空闲后第一次查询可能偶发 `MySQL server has gone away` |
| 7 | **CLI 流式断连不重连** | SSE 流式预览时如果客户端断网，`_summary_event_source` 仍会在服务端继续迭代到结束 | 浪费 token，无重连机制 |
| 8 | **Docker Desktop 端口冲突** | 本机装了 Docker Desktop 的，`uvicorn --port 8000` 会撞 `com.docker.backend`，故本地 fallback 强制走 `8001` | 仅影响本地无 Docker 模式用户；Docker 模式不受影响 |
| 9 | **缺正式单元测试** | `backend/tests/` 仅有占位 `__init__.py`；题目加分项 #6 未充分覆盖 | 重构时缺少自动化保护 |

---

## 10. 验证记录与 FAQ

### 10.1 端到端冒烟快照

```
启动服务：setup.ps1（Docker 分支）成功，backend Up (healthy)
GET    http://localhost:8003/v1/health                 → {"status":"ok","database":"connected"}
POST   http://localhost:8003/v1/recordings（同文件 ×2） → 两次均 202，第二次 idempotent_reused=true
GET    http://localhost:8003/v1/recordings?page=1&page_size=10 → 200，分页正确
GET    http://localhost:8003/v1/tasks/{id}  → pending → transcribing → summarizing → done 全程可观察
POST   http://localhost:8003/v1/tasks/{id}/retry（非 failed） → 409 Conflict
GET    http://localhost:8003/v1/recordings/{id}/summary/stream → SSE 帧格式正确，data: [DONE] 收尾
DELETE http://localhost:8003/v1/recordings/{id} → 204，磁盘文件已删，tasks CASCADE 清空
```

### 10.2 CLI 用法速览

CLI 是**纯交互式 Python 脚本**（无 TUI 库），仅依赖 `httpx`。
完整菜单、状态着色、Windows 编码适配等内容见 **[`cli/README.md`](cli/README.md)**。

```bash
# Docker 模式后端（默认端口 8003）
python cli/cli.py

# 无 Docker fallback（端口 8001）
$env:RECORDING_API_BASE="http://127.0.0.1:8001"; python cli/cli.py
```

### 10.3 FAQ

**Q：CLI 启动后报 `Connection refused`？**
- 检查后端是否真的启动了：`docker compose ps` 或 `curl http://127.0.0.1:8001/v1/health`
- 检查 `RECORDING_API_BASE` 与后端实际监听地址一致

**Q：上传时报「扩展名不合法」或「文件过大」？**
- 允许的扩展名：`.wav` / `.mp3` / `.m4a` / `.aac`
- 上限大小：50 MB（`MAX_UPLOAD_SIZE_MB`）

**Q：显示任务一直 `transcribing` / `summarizing` 不动？**
- 这是正常状态，转写 mock 阶段会 sleep 5~15 秒，摘要阶段会真实调用 LLM
- 看实时日志：`docker compose logs -f backend` 或 `Get-Content backend\logs\app.log -Wait`

**Q：Windows 终端中文路径打不开？**
- 用 Windows Terminal / VSCode 内置终端（默认 UTF-8），或 PowerShell 7+
- 老版 CMD / PowerShell 5.1 自动适配；如仍异常，键入 `chcp 65001` 切到 UTF-8

**Q：怎么切换数据库 / 跑全 MySQL 模式？**
- 编辑 `backend/.env`，把 `DATABASE_URL` 改成 `mysql+aiomysql://user:pass@host:3306/dbname`
- MySQL 表结构由 `001_init.sql` 在新卷首次启动时自动建

---

## 附：CLI 客户端

本项目配套一个**零依赖**的 Python 命令行客户端（位于 `cli/`），用于交互式演示。
CLI 是相对独立的小工具，详细使用说明请阅读 **[`cli/README.md`](cli/README.md)**，内容包括：

- 7 个菜单项对应 7 个后端接口
- Windows 终端 UTF-8 / GBK 编码适配
- 在 Docker 中运行 CLI 的三种方式
- 常见问题与排错

> **本 README 不会重复 CLI 的细节**——这是项目主文档，以「项目整体」视角组织；
> CLI 细节请到 `cli/README.md` 查看。

