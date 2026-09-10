# Cursor AI 开发规则

## 1. 修改现有代码的谨慎原则
- **禁止静默删除或大规模重构现有代码**。
- 任何对已有文件或模块的修改，必须：
  - 在修改前向我明确说明**修改的具体位置**（文件路径、函数/类名）。
  - 说明**修改实现的功能**。
  - 提供**修改前/修改后的关键代码对比**（至少展示差异部分）。
- 如果修改可能引发其他模块的连锁影响，需先分析影响范围并告知。

示例：
> 📁 `backend/app/services/agent_service.py` 的 `run_agent()` 函数  
> 修改目的：增加流式响应支持  
> 修改前：返回完整字符串  
> 修改后：返回异步生成器，逐 token 产出

## 2. 功能验证与自我调试
- 每个功能模块开发完成后，**必须自行模拟测试**。
- 测试要求：
  - 根据模块职责，构造至少两个典型输入（一个正常，一个边界/异常）。
  - 验证输出是否符合预期（如 API 状态码、响应结构、副作用是否符合设计）。
  - 若发现错误，自行修复并重新验证，**直到功能可用**。
- 完成后在代码注释底部或回复中附上简要的「验证记录」，如：
验证记录：已测试注册成功（201）、重复邮箱（400）、密码不足8位（422），均返回预期结果
text

## 3. 统一代码风格
代码必须遵循以下六个维度：

| 原则 | 具体要求 |
|------|----------|
| **简洁** | 函数尽量短小（不超过30行），避免冗余变量；优先使用标准库和已知框架提供的高层 API |
| **易读性强** | 命名清晰，逻辑直白；避免晦涩的技巧；复杂逻辑加注释 |
| **模块化** | 每个文件承担单一职责；功能按 `api/`、`services/`、`models/` 分离；模块间通过接口调用 |
| **高可复用性** | 通用工具函数抽离到 `utils/`；服务方法可被不同路由复用；避免重复代码 |
| **功能解耦** | 各模块不直接依赖内部实现，通过注入或参数传递依赖；不跨模块直接操作数据库 |
| **防御式编程** | 对所有外部输入做校验；处理可能的异常（如网络错误、数据库断连）；提供有意义的错误信息 |

## 4. 注释规范
- **每个函数**（包括类方法）必须添加文档字符串或行注释，说明：
- 函数用途（一句话）。
- 参数含义。
- 返回值。
- 可能抛出的异常（若有）。
- **关键操作步骤**（如复杂的算法、数据库查询、状态变更）上方添加注释，说明“为什么这样做”。
- 注释语言：中文，简单易懂，避免长难句。
- 示例：
```python
def get_user_by_email(db: Session, email: str) -> User | None:
  """
  根据邮箱查询用户。
  参数：
      db: 数据库会话
      email: 用户邮箱
  返回:
      User 对象，未找到则返回 None
  """
  # 大小写不敏感查询，避免因大小写导致的登录失败
  return db.query(User).filter(User.email.ilike(email)).first()

## 5. 代码生成逻辑
代码生成遵循以下逻辑：

代码文件
搭建项目框架

根据项目需求（如 Web API、CLI 工具、数据处理脚本等）建立对应的包/模块文件夹结构。

遵循项目约定的命名规范（如 src/、app/、services/、models/ 等）。

同时创建必要的 __init__.py（Python 项目）或其他语言对应的包标识文件。

逐文件生成代码框架

对每个代码文件，按顺序完成以下操作：
a. 写入导入语句（import / from ... import ...），按标准库、第三方库、本地模块分组。
b. 写入类/函数定义骨架（包括 docstring 和类型注解）。
c. 在函数/方法体内，使用格式为 # 功能说明：<描述> 的占位符代替具体实现，例如：

严格遵守代码生成顺序: 先生成文件骨架 -> 在每个文件里插入对应的函数框架，并在每个函数里插入函数逻辑描述 -> 对每个函数，根据函数逻辑描述用脚本插入具体函数逻辑
注意开发颗粒度细化到函数: 一次只写一个函数，而不是一个完整的API文件，避免上下文污染。

python
def process_data(data: dict) -> dict:
    # 功能说明：清洗输入数据，移除无效字段
    pass
确保所有占位符清晰描述该段代码的职责。

填充函数逻辑

针对每个占位符，根据其“功能说明”逐条编写完整的业务代码。

遵循编码规范（如 PEP 8、ESLint 配置），并考虑异常处理、日志记录、性能优化。

填充完成后，删除占位符注释，保留必要的行内注释（如有）。

配置文件
识别配置需求

根据项目类型（例如 Web 服务、CLI 工具、后台任务）确定所需的配置项，包括但不限于：

服务端口、主机地址

数据库连接串

缓存（Redis）地址

第三方 API 密钥

日志级别、日志路径

功能开关（Feature Flags）

选择配置格式

根据项目生态和团队偏好选择合适的配置文件格式：

Python 项目：优先使用 .env（配合 python-dotenv）存储敏感变量，结合 settings.py 或 config.yaml 管理非敏感配置。

Node.js 项目：常用 .env + config.js / config.json。

Java 项目：使用 application.yml / application.properties。

通用：config.yaml / config.toml 适用于多语言项目。

构建时配置下载要求

在配置时就应当给项目的所有依赖尽可能地配置有效的国内镜像下载地址，避免直接从外网下载导致下载速度缓慢

创建配置模板

生成一个示例配置文件（如 .env.example、config.example.yaml），包含所有必要的配置键，并为每个键提供：

描述性注释（说明用途、数据类型、可选值）

默认值（如果是安全的示例值）

是否为必填项

示例（.env.example）：

env
# 服务端口 (必填)
PORT=3000
# 数据库连接字符串 (必填)
DATABASE_URL=postgresql://user:pass@localhost:5432/db
# Redis 地址 (可选，默认为本地)
REDIS_URL=redis://localhost:6379/0
# 日志级别 (debug|info|warning|error)
LOG_LEVEL=info
支持环境变量覆盖

所有配置值应首先从环境变量读取，若无则回退到配置文件中的默认值。

提供统一的配置加载模块（如 config.py 或 load_config() 函数），负责：

读取 .env 文件（使用 python-dotenv 或类似库）。

解析 YAML/JSON/TOML 文件（如果使用）。

合并环境变量和文件配置，优先采用环境变量。

校验必填项是否缺失，缺失时抛出明确的错误提示。

示例（config.py）：

python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    PORT = int(os.getenv("PORT", 3000))
    DATABASE_URL = os.getenv("DATABASE_URL")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

    @classmethod
    def validate(cls):
        if not cls.DATABASE_URL:
            raise ValueError("DATABASE_URL must be set")
多环境配置（可选）

若项目需要区分开发、测试、生产环境，应支持按环境加载不同配置文件（如 config.dev.yaml、config.prod.yaml），通过 NODE_ENV 或 APP_ENV 环境变量选择。

敏感信息（如密码、密钥）禁止提交到版本控制，应通过 .env 或外部密钥管理服务（如 HashiCorp Vault）注入。

配置即代码

将配置加载与验证逻辑放在项目启动阶段，一旦配置无效应快速失败（fail-fast），避免后续运行时错误。

6. 测试文件规则
如果在项目中需要临时编写测试文件，请将其统一放在一个'/test'文件夹下
测试完成并通过之后，请将其删掉

6. 项目专属补充规则
技术栈固定：后端 Python 3.10+ / FastAPI / LangChain / LangGraph / SQLAlchemy / PostgreSQL / Redis；前端 React 18 + TypeScript + Ant Design + Zustand；移动端 Flutter（第一周不涉及）。

目录结构约定：严格遵循 backend/app/ 下的 api/、services/、models/、schemas/、core/、utils/ 分层；前端 src/ 下 pages/、components/、stores/、api/ 分层。

API 设计：统一前缀 /api/v1/，请求/响应用 Pydantic 模型，错误返回标准格式 {"detail": "..."}。

安全要求：密码必须 bcrypt 哈希；JWT 密钥从环境变量读取，不可硬编码。

流式响应：使用 SSE，格式为 data: {"token": "..."}\n\n，结束标记 data: [DONE]\n\n。

依赖管理：后端依赖写入 requirements.txt；前端 package.json；Docker 服务通过 docker-compose.yml 管理。

AI 模型调用：统一通过 LiteLLM，模型名称在 app/core/config.py 中配置。

# ============================================
# 【最高优先级】文件编码与写入安全熔断规则
# ============================================

7.Agent写入文件规则

[RULE_1] 修改文件前必须识别编码
- 在使用 StrReplace 或 Write 工具修改任何 `.py` 文件前，你必须先通过 Shell 或 Python 检查该文件的真实编码（例如使用 `chardet` 或 `file -i` 命令）。
- 如果文件包含中文且编码不是 UTF-8（如 GBK/GB18030），你必须先转换为 UTF-8（例如用 `iconv` 或 `recode`）再进行修改，或者直接拒绝操作并通知我。

[RULE_2] 写入失败或出现乱码的立即熔断机制
- 当 StrReplace 或 Write 操作返回 JSON 解析错误、编码错误或任何与文件内容相关的异常时，你**必须立即停止所有后续写入尝试**。
- **绝对禁止**用以下方式“挽救”乱码文件：
  - 翻译注释或 docstring 为英文
  - 重写整个文件内容
  - 删除部分内容
  - 使用 Shell 命令强行覆盖
- 正确的唯一行动是：执行 `git checkout -- <文件名>` 回滚（如果 Git 可用），或使用 `docker cp` 从容器恢复，然后向我报告问题，等待我的明确指令。

[RULE_3] 验证修改结果
- 每次修改后，必须用 `file -i <文件名>` 或 Python 读取文件检查编码，确保文件仍然是合法 UTF-8，且中文内容显示正常。
- 如果发现文件内容中出现 `\ufffd`、`姘撶倝` 等乱码字符，立即触发 [RULE_2]。

[RULE_4] 违反规则的惩罚性自检
- 在每次输出代码修改建议前，你必须自我检查是否违反了以上规则。如果违反了，必须主动撤销自己的操作，并向我道歉和说明原因。

[RULE_5] 与现有规则的一致性
- 本规则优先级高于任何“允许优化注释”或“主动改进代码”的指令。即使我说“继续”，也**不得**以此为由绕过本条规则。

8. 代码注释语言强制规则（最高优先级）

- **绝对禁止翻译**：严禁将代码中任何现有的中文注释翻译成英文。无论你（AI）认为英文多么通用或专业，都必须保持注释原文的语言不变。

- **修改时保留原样**：当你修改或重构代码时，对于被修改代码块中的已有注释，必须**原封不动**地保留其内容和语言，不得改写、润色或翻译。

- **新增注释语言**：
   - 如果文件内**已有**中文注释，新增的注释必须使用**中文**，以保持全文件语言风格统一。
   - 仅当整个项目文件全部为英文注释时，才允许使用英文注释。

- **违规自查**：在每次输出代码修改建议前，请自查一遍，确保没有对中文注释做任何不必要的改动。违反此规则的操作将被直接驳回。

## 9. 导入语句验证规则（代码生成前必读）

### 9.1 核心原则
**生成任何涉及跨模块导入的代码前，必须先通过 Read 或 Grep 工具确认目标模块中确实存在被引用的对象（函数、类、变量）。禁止凭记忆或命名惯例假设接口存在。**

### 9.2 违规案例
新文件 `social_ws.py` 写入了以下导入：
```python
from app.core.security import decode_token  # ❌ decode_token 不存在！
```
但 `security.py` 中实际的函数名是 `decode_access_token`。导致运行时报错：
```
ImportError: cannot import name 'decode_token' from 'app.core.security'
```

### 9.3 正确流程
生成涉及导入的代码时，按以下步骤执行：

**第一步**：在写入任何 `from X import Y` 或 `import X` 之前，先用 Read 或 Grep 工具读取目标模块，确认其中存在的函数名、类名、变量名。

**第二步**：将确认后的正确名称写入导入语句。

**第三步**（可选但推荐）：写完导入后，用 `python -c "from X import Y"` 快速验证导入是否成功。

### 9.4 适用场景
以下场景必须执行验证：
- 新建的 API 文件引用已有的 service / core / utils 模块
- 新建的 service 文件引用已有的 models / schemas
- 任何通过 `from ... import ...` 引入外部模块的代码

### 9.5 常见命名惯例（参考，实际以代码为准）
| 模块 | 常见函数/类 | 验证必要性 |
|------|------------|-----------|
| `app.core.security` | `decode_access_token`、`get_current_user_ws`、`create_access_token` | 必须验证 |
| `app.core.database` | `get_db` | 必须验证 |
| `app.core.config` | `settings` | 必须验证 |
| `app.services.*` | 各 service 文件中的函数 | 必须验证 |

## 10. 容器编排与启动时序规则

### 10.1 核心原则
**修改 docker-compose.yml 或 nginx 配置后，必须做一次"启动时序"脑内模拟：哪个容器先起、哪个服务先就绪、依赖链是否有 healthcheck 兜底。代码本身正确 ≠ 系统能起来。**

### 10.2 违规案例
nginx 配置 upstream 写 `server backend:8000`，docker-compose 只写 `depends_on: backend`（默认 service_started）：
- backend 容器先启动了，但 uvicorn 还在跑 alembic、加载模型，没开始监听 8000
- nginx 在容器启动时尝试解析 `backend`，DNS 查不到，直接 `[emerg]` 退出
- docker-compose 认为 nginx 启动失败，整套系统起不来

报错：
```
[emerg] host not found in upstream "backend:8000" in /etc/nginx/nginx.conf:68
```

### 10.3 正确做法：两层防护

**第一层：nginx 配置加 resolver（运行时动态解析）**

在 `nginx.conf` 的 `http {}` 块内添加：
```nginx
resolver 127.0.0.11 valid=10s ipv6=off;
```
- `127.0.0.11` 是 Docker 内嵌 DNS，解析容器服务名
- `valid=10s` 让 nginx 每 10 秒重新解析，不在启动时死锁

**第二层：docker-compose 用 service_healthy 而非 service_started**

nginx 依赖 backend：
```yaml
nginx:
  depends_on:
    backend:
      condition: service_healthy   # 不是 service_started
```

backend 要有 healthcheck：
```yaml
backend:
  healthcheck:
    test: ["CMD", "wget", "-q", "-O-", "http://127.0.0.1:8000/api/v1/health"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 20s
```

两层都做才能覆盖：backend 还没就绪时 resolver 兜底，nginx 不会在 backend 起来之前就启动。

### 10.4 适用场景
以下场景必须检查启动时序和健康检查：
- 新增 / 修改 nginx 反代配置（任何 `proxy_pass` 到容器内服务名）
- 新增 / 修改 docker-compose 的 `depends_on`
- 新增 / 修改服务 healthcheck
- 任何涉及多容器启动顺序的改动

### 10.5 常见的"假安全"写法（需警惕）
| 写法 | 为什么不够 | 正确写法 |
|------|-----------|---------|
| `depends_on: [backend]` | 只等容器启动，不等服务就绪 | `depends_on: backend: condition: service_healthy` |
| `depends_on: backend: condition: service_started` | 同上，started ≠ healthy | `condition: service_healthy` |
| nginx upstream 无 resolver | 启动时 DNS 查不到直接崩 | 加 `resolver 127.0.0.11 valid=10s` |
| healthcheck 指向 /healthz 而非 /api/v1/health | /healthz 不经过后端路由，可能误判 | 用实际的 API 健康检查端点 |

## 11. 敏感信息与配置管理规范

## 核心原则
所有**密钥、API Token、数据库连接串、第三方服务地址、邮箱/账号**等敏感信息，**严禁**以字符串字面量的形式直接出现在代码文件中。

## 强制性要求

### 1. 禁止硬编码的内容包括但不限于
- API Key / Secret / Token
- 数据库连接字符串（如 `mysql://user:pass@host:port/db`）
- Redis / MongoDB 等中间件连接地址
- 第三方服务的 URL 或 Endpoint
- 邮箱、密码、手机号等个人/系统凭证
- 任何包含认证信息的 Bearer Token 或 Authorization Header

### 2. 正确做法：统一使用配置文件
所有敏感信息必须放置在统一的配置文件中，通过环境变量或配置文件读取。

#### Python 后端示例
```python
# 正确
import os

API_KEY = os.getenv("BAIDU_API_KEY")
DB_URL = os.getenv("DATABASE_URL")

## 12. 运行验证规则（最高优先级）

### 核心原则
**任何后端 API、WebSocket、SSE 流程、服务间调用，在声称“完成”之前，必须通过实际运行验证，禁止只做语法检查或单元测试就交付。**

### 强制验证步骤
1. **启动依赖环境**：
   - 使用 `docker compose up -d` 启动所有需要的中间件（PostgreSQL、Redis 等）。
   - 如果服务本身需要在容器中运行，则执行 `docker compose up -d --build` 启动全部服务。

2. **等待服务就绪**：
   - 通过 `docker compose ps` 或健康检查端点确认服务已启动。
   - 若后端启动较慢，等待 `healthcheck` 通过。

3. **调用接口验证**：
   - 对每个新增或修改的 API 端点，使用 `curl` 或 Python `httpx`/`requests` 发起真实 HTTP 请求。
   - 验证以下内容：
     - 状态码是否符合预期（200/201/400/401/422 等）。
     - 响应 JSON 结构是否符合 Pydantic Schema。
     - 数据库或 Redis 中是否产生了预期的副作用（如插入记录、写入缓存）。
   - 对于流式接口（SSE），用 `curl -N` 或 Python 脚本检查 `data:` 格式和 `[DONE]` 结束标记。
   - 对于 WebSocket，使用 `websockets` 库或 `wscat` 连接测试消息交互。

4. **异常路径测试**：
   - 至少测试一个异常场景（如无效 Token、缺失参数、数据库断开），确认返回友好错误而非 500 堆栈。

5. **验证记录输出**：
   - 在回复中附上验证记录，格式为：
      验证记录：

    启动服务：docker compose up -d 成功

    GET /api/v1/health 返回       {"status":"ok","database":"connected"}

    POST /api/v1/auth/send-sms 携带正确 phone 返回 200

    POST /api/v1/auth/login 携带错误验证码返回 400

    以上均符合预期

6. **如果验证失败**：
- 必须立即修复，重新运行验证，直到通过。
- 如果无法启动服务或调用接口，**不得声称完成**，应主动说明错误日志并请求进一步指令。

## 12.输出中不允许出现的特定文字
- "DONE"