# ============================================
# 文件: setup.ps1
# 功能: 项目一键引导脚本（Windows PowerShell）
#
# 行为:
#   1. 弹 PowerShell GUI 输入 DeepSeek API Key
#   2. 检测本机是否有 Docker:
#      - 有 Docker → 写 .env，自动执行 docker compose up --build
#      - 无 Docker → 写 .env，切换为 SQLite，提示手动启动命令
#
# 使用: 右键 → 使用 PowerShell 运行
# ============================================

$ErrorActionPreference = "Stop"

# ---------- 脚本自定位 ----------
# 功能说明：右键运行时 $PSScriptRoot 可能为 $null，用 try 兜底
try {
    $ScriptDir = $PSScriptRoot
    if ([string]::IsNullOrEmpty($ScriptDir)) {
        $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    }
    if ([string]::IsNullOrEmpty($ScriptDir)) {
        $ScriptDir = (Get-Location).Path
    }
} catch {
    $ScriptDir = (Get-Location).Path
}

$ErrorLog = Join-Path $ScriptDir "setup-error.log"

# ---------- 全局错误处理 ----------
# 为什么：右键运行时如果脚本崩溃，临时控制台会立即关闭，用户看不到错误。
# 这里把任何未捕获异常写到 setup-error.log，并强制 Read-Host 等待用户按键。
trap {
    $msg = @"
========================================
时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
脚本: setup.ps1
错误: $($_.Exception.Message)
位置: $($_.InvocationInfo.PositionMessage)
类型: $($_.Exception.GetType().FullName)
堆栈: $($_.ScriptStackTrace)
========================================
"@
    Write-Host ""
    Write-Host "[X] 脚本异常退出" -ForegroundColor Red
    Write-Host $msg -ForegroundColor Red
    # 功能说明：用 .NET API 写无 BOM UTF-8，避免日志被 BOM 污染
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::AppendAllText($ErrorLog, $msg, $utf8NoBom)
    Write-Host "错误日志已写入: $ErrorLog" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "按回车关闭窗口"
    exit 1
}

# ---------- 路径常量 ----------
$RootDir       = $ScriptDir
$BackendDir    = Join-Path $RootDir "backend"
$EnvFile       = Join-Path $BackendDir ".env"
$EnvExample    = Join-Path $BackendDir ".env.example"
$CliDir        = Join-Path $RootDir "cli"
$Requirements  = Join-Path $BackendDir "requirements.txt"
$CliReqs       = Join-Path $CliDir "requirements.txt"
$DataDir       = Join-Path $BackendDir "data"

# ---------- 工具函数 ----------
function Write-Step($msg) {
    Write-Host ""
    Write-Host "== $msg ==" -ForegroundColor Cyan
}

function Test-Command($name) {
    $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Read-ApiKeyGUI {
    # 弹 .NET WinForms 输入框，避免在控制台 echo 明文 Key
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "录音转写服务 - 首次配置"
    $form.Size = New-Object System.Drawing.Size(540, 230)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false

    $label = New-Object System.Windows.Forms.Label
    $label.Text = "请输入 DeepSeek API Key（以 sk- 开头）："
    $label.Location = New-Object System.Drawing.Point(15, 15)
    $label.AutoSize = $true
    $form.Controls.Add($label)

    $tip = New-Object System.Windows.Forms.Label
    $tip.Text = "申请地址: https://platform.deepseek.com/"
    $tip.Location = New-Object System.Drawing.Point(15, 38)
    $tip.ForeColor = [System.Drawing.Color]::Gray
    $tip.AutoSize = $true
    $form.Controls.Add($tip)

    $box = New-Object System.Windows.Forms.TextBox
    $box.Location = New-Object System.Drawing.Point(15, 65)
    $box.Width = 495
    $form.Controls.Add($box)

    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = "确定"
    $ok.Location = New-Object System.Drawing.Point(420, 110)
    $ok.Size = New-Object System.Drawing.Size(90, 30)
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $ok
    $form.Controls.Add($ok)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        return $box.Text.Trim()
    }
    return ""
}

function Start-DockerServices {
    # 自动执行 docker compose up --build，流式输出到当前窗口
    # 不用 -d 是为了让用户实时看到构建进度，不用另开窗口
    Write-Host "  正在构建并启动服务（可能需要几分钟）..." -ForegroundColor Cyan
    Write-Host ""

    # UTF-8 无 BOM 编码（在本函数作用域内独立声明，避免依赖其他函数中的同名变量）
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    # 先确保 .env 存在且 KEY 已写入（Save-EnvFile 已在前面调用过）
    $envContent = [System.IO.File]::ReadAllText($EnvFile, $utf8NoBom)
    if ($envContent -notmatch '(?m)^DEEPSEEK_API_KEY=sk-') {
        throw "DEEPSEEK_API_KEY 未正确写入 .env，请检查"
    }

    # 检查 docker compose 文件
    $composeFile = Join-Path $RootDir "docker-compose.yml"
    if (-not (Test-Path $composeFile)) {
        throw "未找到 docker-compose.yml"
    }

    # 启动：用 -d 分离后台运行，setup 窗口立刻返回去弹 CLI 窗口
    # 用户仍然通过 Show-ServiceLogs 看到构建结果（最近 20 行）
    # 出错时 PowerShell 会抛异常，被外层 trap 捕获并写 setup-error.log
    docker compose up -d --build

    Write-Host ""
    Write-Host "  Docker 服务已启动" -ForegroundColor Green
    Write-Host ""
}

function Wait-ForHealthyServices {
    # 轮询 docker compose ps，等待 backend 容器为 Up (healthy)
    # 用 2+ 个空格作为列分隔；只关心 backend 这一行
    Write-Host "  等待服务就绪..." -ForegroundColor Cyan
    $timeout = 120
    $interval = 5
    $elapsed = 0

    while ($elapsed -lt $timeout) {
        Start-Sleep -Seconds $interval
        $elapsed += $interval

        $raw = docker compose ps -a 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
            Write-Host "    ($elapsed s) 检查状态失败，重试..." -ForegroundColor DarkGray
            continue
        }

        $ok = $false
        $skipRest = $false
        foreach ($line in ($raw -split "`r?`n")) {
            if ($skipRest) { break }   # 已经找到 backend，结束遍历
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            # 用 2+ 个空格做分隔
            $cols = $line -split '\s{2,}'
            if ($cols.Count -lt 6) { continue }
            # 字段 0=NAME, 1=IMAGE, 2=COMMAND, 3=SERVICE, 4=CREATED, 5=STATUS
            if ($cols[3] -ne "backend") { continue }
            $skipRest = $true
            # STATUS 是 "Up X (healthy)" 或 "Exited (0) X ago" 等
            # 接受 Up/healthy/running；Exited/unhealthy/restarting 视为未就绪
            if ($cols[5] -match '^Up\b' -and ($cols[5] -match 'healthy' -or $cols[5] -match '\d+')) {
                $ok = $true
            }
        }

        if ($ok) {
            Write-Host "  ✓ 服务已就绪（backend Up）" -ForegroundColor Green
            return $true
        }
        Write-Host "    ($elapsed s) 服务启动中..." -ForegroundColor DarkGray
    }
    Write-Host "  [WARN] 等待超时（${timeout}s），服务可能仍在启动中" -ForegroundColor Yellow
    return $false
}

function Show-ServiceLogs {
    # 显示最近 20 行日志，让用户确认服务正常
    Write-Host ""
    Write-Host "  === 最近日志 ===" -ForegroundColor DarkGray
    docker compose logs --tail=20 2>$null | ForEach-Object {
        Write-Host "    $_" -ForegroundColor DarkGray
    }
}

function Start-LocalServices {
    # 无 Docker 分支：本地 venv + SQLite 全自动跑起来
    # 关键步骤：
    #   1) 准备 venv
    #   2) pip install 后端 + CLI 依赖
    #   3) 初始化 SQLite 数据库
    #   4) 后台启动 uvicorn（写日志到 backend/logs/uvicorn.log）

    $ErrorActionPreference = "Stop"

    # ---- 1. Python 探测 ----
    Write-Host "  正在检查 Python..." -ForegroundColor Cyan
    $python = $null
    foreach ($cand in @("python", "python3", "py")) {
        if (Test-Command $cand) {
            # 拿真实路径
            $python = (Get-Command $cand).Source
            break
        }
    }
    if ([string]::IsNullOrEmpty($python)) {
        throw "未检测到 Python，请先安装 Python 3.10+ 并加入 PATH"
    }
    Write-Host "  ✓ Python: $python" -ForegroundColor Green

    # ---- 2. venv ----
    $venvDir = Join-Path $BackendDir ".venv"
    if (-not (Test-Path $venvDir)) {
        Write-Host "  正在创建 venv: $venvDir" -ForegroundColor Cyan
        & $python -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { throw "venv 创建失败" }
    } else {
        Write-Host "  ✓ venv 已存在: $venvDir" -ForegroundColor DarkGray
    }
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPy)) { throw "venv 中找不到 python.exe: $venvPy" }

    # ---- 3. 升级 pip + 安装后端依赖 ----
    Write-Host "  正在升级 pip + 安装后端依赖..." -ForegroundColor Cyan
    & $venvPy -m pip install --upgrade pip --disable-pip-version-check | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "pip 升级失败" }

    # 清华镜像（用户机器上已经预设）
    $pipIndex = "https://pypi.tuna.tsinghua.edu.cn/simple"
    & $venvPy -m pip install -r $Requirements -i $pipIndex --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw "后端依赖安装失败" }
    Write-Host "  ✓ 后端依赖安装完成" -ForegroundColor Green

    # ---- 4. 安装 CLI 依赖（用同一个 venv，省一个环境） ----
    if (Test-Path $CliReqs) {
        Write-Host "  正在安装 CLI 依赖..." -ForegroundColor Cyan
        & $venvPy -m pip install -r $CliReqs -i $pipIndex --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) { throw "CLI 依赖安装失败" }
        Write-Host "  ✓ CLI 依赖安装完成" -ForegroundColor Green
    }

    # ---- 5. 初始化 SQLite ----
    Write-Host "  正在初始化 SQLite..." -ForegroundColor Cyan
    Push-Location $BackendDir
    try {
        & $venvPy -m scripts.init_sqlite
        if ($LASTEXITCODE -ne 0) { throw "SQLite 初始化失败" }
    } finally {
        Pop-Location
    }

    # ---- 6. 后台启动 uvicorn ----
    Write-Host "  正在后台启动 uvicorn..." -ForegroundColor Cyan
    $logsDir = Join-Path $BackendDir "logs"
    if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }
    $uvicornLog = Join-Path $logsDir "uvicorn.log"

    # 本地模式端口 = 8001，避免与 Docker Desktop 的 com.docker.backend(:8000) 撞端口
    # 说明：8000 已被本机 Docker 后端占着，启动 uvicorn 时会冲突，所以本地走 8001
    $localPort = 8001

    # 先确认端口没被占
    $portInUse = Get-NetTCPConnection -LocalPort $localPort -State Listen -ErrorAction SilentlyContinue
    if ($portInUse) {
        Write-Host "  [WARN] $localPort 端口已被占用，跳过启动（已有进程在跑？）" -ForegroundColor Yellow
        return
    }

    # Start-Process -WindowStyle Hidden：setup 窗口退掉后 uvicorn 仍然跑
    $uvicornArgs = @(
        "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1",
        "--port", "$localPort"
        # 注意：不开 --reload，避免双进程 + 文件改动触发多次重启
    )
    $proc = Start-Process -FilePath $venvPy `
        -ArgumentList $uvicornArgs `
        -WorkingDirectory $BackendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $uvicornLog `
        -RedirectStandardError ($uvicornLog + ".err") `
        -PassThru

    # 把当前启动用的端口写进 setup 进程的全局变量，让 Wait/输出/Cmd 都能读到
    $script:LocalUvicornPort = $localPort
    Write-Host "  ✓ uvicorn PID=$($proc.Id) Port=$localPort，日志: $uvicornLog" -ForegroundColor Green
}

function Wait-ForLocalHealthy {
    # 轮询本地 uvicorn 健康端点，最多等 60 秒
    Write-Host "  等待本地服务就绪..." -ForegroundColor Cyan
    $port = $script:LocalUvicornPort
    if (-not $port) { $port = 8001 }

    $timeout = 60
    $interval = 3
    $elapsed = 0
    while ($elapsed -lt $timeout) {
        Start-Sleep -Seconds $interval
        $elapsed += $interval
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/v1/health" `
                -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($resp.StatusCode -eq 200) {
                Write-Host "  ✓ 本地服务已就绪" -ForegroundColor Green
                return $true
            }
        } catch {
            # 还没起来，继续
        }
        Write-Host "    ($elapsed s) 等待中..." -ForegroundColor DarkGray
    }
    Write-Host "  [WARN] 等待超时（${timeout}s）" -ForegroundColor Yellow
    return $false
}

function Launch-CLIWindow {
    # 在新 PowerShell 窗口启动 CLI
    # 不用 -Wait，让 setup.ps1 主窗口立刻返回；CLI 窗口独立生命周期
    #
    # 端口处理：
    #   - Docker 分支：后端默认 8003，命令行默认 URL 就是 8003，不用传
    #   - 无 Docker 本地分支：后端跑 8001，需要通过 RECORDING_API_BASE 环境变量告诉 CLI
    $cliScript = Join-Path $CliDir "run_cli.ps1"
    if (-not (Test-Path $cliScript)) {
        Write-Host "  ⚠ 未找到 cli/run_cli.ps1，跳过 CLI 启动" -ForegroundColor Yellow
        return
    }

    # 决定传给 CLI 的后端地址
    $apiBase = $env:RECORDING_API_BASE
    if (-not $apiBase -and $script:LocalUvicornPort) {
        $apiBase = "http://127.0.0.1:$($script:LocalUvicornPort)"
    }
    if (-not $apiBase) {
        $apiBase = "http://127.0.0.1:8003"  # Docker 分支默认
    }

    Write-Host ""
    Write-Host "  正在弹出 CLI 窗口（后端 $apiBase）..." -ForegroundColor Cyan

    # 把 RECORDING_API_BASE 通过 -Command 顺序的方式注入：先 setenv，再跑脚本
    $psCommand = "`$env:RECORDING_API_BASE='$apiBase'; & '$cliScript'"
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command", $psCommand
        ) `
        -WorkingDirectory $CliDir `
        -WindowStyle Normal
    Write-Host "  ✓ CLI 窗口已弹出" -ForegroundColor Green
}

function Save-EnvFile($apiKey, $useSqlite) {
    # 第一次跑：复制 .env.example；已有 .env：原地修改
    if (-not (Test-Path $EnvFile)) {
        if (-not (Test-Path $EnvExample)) {
            throw "找不到 .env.example，请确认项目结构完整"
        }
        Copy-Item $EnvExample $EnvFile
        Write-Host "  已生成 backend/.env"
    }

    # 功能说明：用 .NET API 读全文件，避免 PS 5.1 Get-Content -Encoding 选错代码页
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $content = [System.IO.File]::ReadAllText($EnvFile, $utf8NoBom)

    # 替换或追加 DEEPSEEK_API_KEY
    if ($content -match '(?m)^DEEPSEEK_API_KEY=.*$') {
        $content = $content -replace '(?m)^DEEPSEEK_API_KEY=.*$', "DEEPSEEK_API_KEY=$apiKey"
    } else {
        $content = $content.TrimEnd() + "`r`nDEEPSEEK_API_KEY=$apiKey"
    }

    # SQLite 模式下覆盖 DATABASE_URL
    if ($useSqlite) {
        $sqliteUrl = "sqlite+aiosqlite:///./data/recording.db"
        if ($content -match '(?m)^DATABASE_URL=.*$') {
            $content = $content -replace '(?m)^DATABASE_URL=.*$', "DATABASE_URL=$sqliteUrl"
        } else {
            $content = $content.TrimEnd() + "`r`nDATABASE_URL=$sqliteUrl"
        }
        if (-not (Test-Path $DataDir)) {
            New-Item -ItemType Directory -Path $DataDir | Out-Null
        }
    }

    # 功能说明：PS 5.1 的 Set-Content -Encoding UTF8 会带 BOM，干扰 Python pydantic-settings
    #          用 .NET API 直接写无 BOM UTF-8（兼容 PS 5.1 / 7.x）
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($EnvFile, $content, $utf8NoBom)
    Write-Host "  已写入 DEEPSEEK_API_KEY"
}

# ---------- 主流程 ----------
Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  录音转写服务 - 一键启动" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

# 步骤 1: 输 Key
Write-Step "步骤 1/3：配置 DeepSeek API Key"
$apiKey = Read-ApiKeyGUI
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Host "  已取消，未配置 Key。" -ForegroundColor Yellow
    Read-Host "按回车退出"
    exit 0
}
if (-not $apiKey.StartsWith("sk-")) {
    Write-Host "  ⚠️  警告：Key 通常以 sk- 开头，但仍将按用户输入保存" -ForegroundColor Yellow
}

# 步骤 2: 检测 Docker
Write-Step "步骤 2/3：检测环境"
$hasDocker = Test-Command "docker"
# --- 调试开关（需要时取消下行注释强制走无 Docker 分支）---
$hasDocker = $false
if ($hasDocker) {
    Write-Host "  ✓ 检测到 Docker" -ForegroundColor Green
    Save-EnvFile -apiKey $apiKey -useSqlite $false

    Write-Step "步骤 3/3：自动启动服务"
    try {
        Start-DockerServices
        $healthy = Wait-ForHealthyServices
        Show-ServiceLogs
        Launch-CLIWindow

        Write-Host ""
        Write-Host "  ✓ Docker 服务已启动" -ForegroundColor Green
        Write-Host "  请访问 API 文档：" -ForegroundColor Green
        Write-Host "      http://localhost:8003/docs"
        Write-Host ""
        Write-Host "  查看实时日志："
        Write-Host "      docker compose logs -f"
        Write-Host ""
        Write-Host "  停止服务："
        Write-Host "      docker compose down"
    } catch {
        throw "Docker 服务启动失败：$($_.Exception.Message)"
    }
} else {
    Write-Host "  未检测到 Docker，改用 SQLite 本地模式" -ForegroundColor Yellow
    Save-EnvFile -apiKey $apiKey -useSqlite $true

    Write-Step "步骤 3/3：自动启动本地服务"
    try {
        Start-LocalServices
        $healthy = Wait-ForLocalHealthy
        $localPort = $script:LocalUvicornPort
        if (-not $localPort) { $localPort = 8001 }

        if ($healthy) {
            Write-Host ""
            Write-Host "  ✓ 本地服务已启动" -ForegroundColor Green
            Write-Host "  API 文档：" -ForegroundColor Green
            Write-Host "      http://127.0.0.1:$localPort/docs"
            Write-Host "  健康检查：" -ForegroundColor Green
            Write-Host "      http://127.0.0.1:$localPort/v1/health"
            Write-Host ""
            Write-Host "  ⚠️  端口说明：本地模式用 $localPort，避开本机 Docker 后端占用的 8000" -ForegroundColor DarkGray
            Write-Host ""
            Write-Host "  查看实时日志："
            Write-Host "      Get-Content backend\logs\uvicorn.log -Wait"
            Write-Host ""
            Write-Host "  停止服务："
            Write-Host "      Get-Process python -ErrorAction SilentlyContinue | Where-Object { `$_.Path -like '*.venv*' } | Stop-Process"
        } else {
            Write-Host ""
            Write-Host "  服务启动超时，请查看日志：" -ForegroundColor Yellow
            Write-Host "      backend\logs\uvicorn.log"
        }

        # 最后弹 CLI 窗口（不论健康与否都给用户一个交互入口）
        Launch-CLIWindow
    } catch {
        throw "本地服务启动失败：$($_.Exception.Message)"
    }
}

Write-Host ""
Read-Host "按回车退出"
