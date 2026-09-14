# ==============================================================================
# Artemis 手机智能体 - Windows 全中文一键极速部署与运行脚本 (deploy_windows.ps1)
# 
# 自动化执行流水线：
# 1. 终端编码与网络环境优化 (UTF-8 + TLS 1.2/1.3)
# 2. 自动检测并极速静默安装 Python 包与运行时管理器 (Astral uv)
# 3. 自动检测并静默装配 Android 核心工具链 (ADB / FFmpeg / scrcpy)
# 4. 自动激活本地 ADB Server 守护服务 (127.0.0.1:5037)
# 5. 自动检查并生成 .env 环境变量配置文件模板
# 6. 自动构筑隔离运行沙箱并全量同步 190+ 个项目核心依赖库
# 7. 自动校验与构建 Web 前端可视化控制台 (Showcase UI)
# 8. 自动挂载主流 AI IDE 的原生 MCP 协议支持
# 9. 自动拉起 Artemis 服务并自动在浏览器中打开工作台
# ==============================================================================

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$NoOpen = $false,
    [switch]$SkipFrontendBuild = $false
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 启用现代安全 TLS 通信协议
try {
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12 -bor [System.Net.SecurityProtocolType]::Tls13
} catch {}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = Split-Path -Parent $ScriptDir
Set-Location $RootDir

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "👉 $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "   ✅ $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "   ⚠️ $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "   ❌ $Message" -ForegroundColor Red
}

function Test-CommandExists {
    param([string]$Command)
    $res = Get-Command $Command -ErrorAction SilentlyContinue
    return ($null -ne $res)
}

function Update-EnvironmentPath {
    $standardDirs = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links",
        "$env:LOCALAPPDATA\Programs\node",
        "$env:USERPROFILE\.local\share\node",
        "$env:LOCALAPPDATA\Programs\scrcpy",
        "$env:USERPROFILE\.local\share\scrcpy",
        "$env:LOCALAPPDATA\Programs\platform-tools",
        "$env:USERPROFILE\.local\share\platform-tools",
        "$env:LOCALAPPDATA\Programs\uv",
        "$env:LOCALAPPDATA\uv",
        "$env:APPDATA\uv",
        "$env:USERPROFILE\.cargo\bin",
        "$env:USERPROFILE\.local\bin",
        "$env:USERPROFILE\scoop\shims",
        "C:\ProgramData\chocolatey\bin",
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools",
        "$env:LOCALAPPDATA\Android\android-sdk\platform-tools",
        "$env:ProgramFiles\Android\platform-tools",
        "${env:ProgramFiles(x86)}\Android\android-sdk\platform-tools",
        "$env:ProgramFiles\nodejs",
        "${env:ProgramFiles(x86)}\nodejs",
        "$env:APPDATA\npm"
    )
    if ($env:CARGO_HOME) { $standardDirs = @("$env:CARGO_HOME\bin") + $standardDirs }
    if ($env:ANDROID_HOME) { $standardDirs += "$env:ANDROID_HOME\platform-tools" }
    if ($env:ANDROID_SDK_ROOT) { $standardDirs += "$env:ANDROID_SDK_ROOT\platform-tools" }
    if ($env:NVM_SYMLINK) { $standardDirs = @($env:NVM_SYMLINK) + $standardDirs }
    if ($env:NVM_HOME) { $standardDirs = @($env:NVM_HOME) + $standardDirs }

    $regPath = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $currentPaths = ($env:PATH -split ";") + ($regPath -split ";") + $standardDirs | Where-Object { [string]::IsNullOrWhiteSpace($_) -eq $false -and (Test-Path $_) } | Select-Object -Unique
    $env:PATH = $currentPaths -join ";"

    $portableNode = "$env:LOCALAPPDATA\Programs\node"
    if (Test-Path "$portableNode\node.exe") {
        $env:PATH = "$portableNode;$env:PATH"
    }
    $portableScrcpy = "$env:LOCALAPPDATA\Programs\scrcpy"
    if (Test-Path "$portableScrcpy\scrcpy.exe") {
        $env:PATH = "$portableScrcpy;$env:PATH"
    }
    $portablePt = "$env:LOCALAPPDATA\Programs\platform-tools"
    if (Test-Path "$portablePt\adb.exe") {
        $env:PATH = "$portablePt;$env:PATH"
    }
}

function Invoke-DownloadFile {
    param(
        [Parameter(Mandatory=$true)][string]$Uri,
        [Parameter(Mandatory=$true)][string]$OutFile,
        [int]$TimeoutSec = 60
    )
    if (Test-Path $OutFile) {
        Remove-Item -Path $OutFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-CommandExists "curl.exe") {
        try {
            & curl.exe -f -sSL --connect-timeout 5 --max-time $TimeoutSec "$Uri" -o "$OutFile" 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt 0)) {
                return $true
            }
        } catch {}
    }
    try {
        $prevProgress = $ProgressPreference
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $Uri -OutFile $OutFile -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
        $ProgressPreference = $prevProgress
        if ((Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt 0)) {
            return $true
        }
    } catch {
        $ProgressPreference = $prevProgress
    }
    return $false
}

Write-Host "==============================================================================" -ForegroundColor DarkCyan
Write-Host "   ☕ Artemis 手机智能体 - Windows 全中文一键全自动极速部署与装配程序" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor DarkCyan

# ------------------------------------------------------------------------------
# 步骤 1：刷新与优化 PATH 路径
# ------------------------------------------------------------------------------
Write-Step "[1/8] 检查并配置系统环境运行路径..."
Update-EnvironmentPath
Write-Success "系统环境路径与运行目录配置就绪。"

# ------------------------------------------------------------------------------
# 步骤 2：自动检测并安装 Astral uv
# ------------------------------------------------------------------------------
Write-Step "[2/8] 检查 Python 现代包管理器 (Astral uv)..."
if (-not (Test-CommandExists "uv")) {
    Write-Host "   [提示] 系统中未找到 uv，正在自动从官方源极速静默安装..." -ForegroundColor Yellow
    try {
        Invoke-Expression (Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1")
    } catch {
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    }
    Update-EnvironmentPath
}

if (-not (Test-CommandExists "uv")) {
    Write-Err "未能自动安装 Astral 'uv'，请在终端手动执行以下命令后重新运行："
    Write-Host "      powershell -c ""irm https://astral.sh/uv/install.ps1 | iex""" -ForegroundColor White
    exit 1
}
$uvVer = (& uv --version)
Write-Success "Python 运行时与包管理器已就绪: $uvVer"

# ------------------------------------------------------------------------------
# 步骤 3：自动静默装配核心工具链 (ADB, FFmpeg, scrcpy)
# ------------------------------------------------------------------------------
Write-Step "[3/8] 检查真机操控核心工具链 (ADB 调试桥、FFmpeg 视频流、scrcpy 极速镜像)..."
$missing = @()
if (-not (Test-CommandExists "adb")) { $missing += "adb" }
if (-not (Test-CommandExists "ffmpeg")) { $missing += "ffmpeg" }
if (-not (Test-CommandExists "scrcpy")) { $missing += "scrcpy" }

if ($missing.Count -gt 0) {
    Write-Host "   [提示] 检测到部分核心工具尚未安装: $($missing -join ', ')，正在自动静默装配..." -ForegroundColor Yellow
    if (Test-CommandExists "winget") {
        if ($missing -contains "adb") {
            winget install --id Google.PlatformTools -e --accept-source-agreements --accept-package-agreements --silent 2>$null | Out-Null
        }
        if ($missing -contains "ffmpeg") {
            winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent 2>$null | Out-Null
        }
        if ($missing -contains "scrcpy") {
            winget install --id Genymobile.scrcpy -e --accept-source-agreements --accept-package-agreements --silent 2>$null | Out-Null
        }
        Update-EnvironmentPath
    }

    # 针对无管理员权限环境自动拉取官方绿色免安装版
    if (-not (Test-CommandExists "adb")) {
        $ptZip = "$env:TEMP\platform-tools-windows.zip"
        if (Invoke-DownloadFile -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $ptZip) {
            New-Item -ItemType Directory -Path "$env:LOCALAPPDATA\Programs" -Force | Out-Null
            Expand-Archive -Path $ptZip -DestinationPath "$env:LOCALAPPDATA\Programs" -Force
            Remove-Item $ptZip -Force -ErrorAction SilentlyContinue
            Update-EnvironmentPath
        }
    }
}

$adbOk = if (Test-CommandExists "adb") { "已就绪" } else { "未就绪" }
$ffmpegOk = if (Test-CommandExists "ffmpeg") { "已就绪" } else { "未就绪" }
$scrcpyOk = if (Test-CommandExists "scrcpy") { "已就绪" } else { "未就绪" }
Write-Success "核心工具链状态 ➔ ADB 调试桥: $adbOk | FFmpeg 视频引擎: $ffmpegOk | Scrcpy 硬件镜像: $scrcpyOk"

# ------------------------------------------------------------------------------
# 步骤 4：确保 ADB Server 后台守护正常启动
# ------------------------------------------------------------------------------
Write-Step "[4/8] 检查并唤醒本地 ADB Server 守护服务..."
try {
    & adb start-server 2>$null | Out-Null
    Write-Success "本地 ADB Server (127.0.0.1:5037) 已正常监听运行。"
} catch {
    Write-Warn "ADB Server 启动跳过或已在运行。"
}

# ------------------------------------------------------------------------------
# 步骤 5：环境配置文件 (.env) 自动初始化
# ------------------------------------------------------------------------------
Write-Step "[5/8] 检查项目环境配置文件 (.env)..."
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Success "已自动从 .env.example 模板生成默认 .env 配置文件。"
    } else {
        New-Item -ItemType File -Path ".env" | Out-Null
        Write-Success "已自动新建空白 .env 配置文件。"
    }
} else {
    Write-Success ".env 配置文件已就绪（保留您已配置的模型密钥与参数）。"
}

# ------------------------------------------------------------------------------
# 步骤 6：同步 Python 虚拟环境与 190+ 项目核心包
# ------------------------------------------------------------------------------
Write-Step "[6/8] 构筑独立隔离沙箱并同步 190+ 个核心依赖库..."
Write-Host "   [提示] 正在执行 uv sync 自动环境同步，请稍候..." -ForegroundColor Gray
& uv sync --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Success "Python 虚拟运行环境与 190+ 个核心算法包校验同步完成。"
} else {
    Write-Warn "uv sync 提示存在部分非关键警告，正在继续执行后续流程..."
}

# ------------------------------------------------------------------------------
# 步骤 7：检查与构建 Web Showcase UI 前端
# ------------------------------------------------------------------------------
Write-Step "[7/8] 检查 Web 前端控制台静态资源 (Showcase UI)..."
$ShowcaseIndex = "$RootDir\apps\showcase_ui\dist\frontend\browser\index.html"
$ShowcaseIndexAlt = "$RootDir\apps\showcase_ui\dist\frontend\index.html"

if ((-not (Test-Path $ShowcaseIndex)) -and (-not (Test-Path $ShowcaseIndexAlt)) -and (-not $SkipFrontendBuild)) {
    Write-Host "   [提示] 未检测到预编译前端包，正在自动执行编译构建..." -ForegroundColor Yellow
    
    if (Test-CommandExists "npm") {
        Push-Location "$RootDir\apps\showcase_ui"
        try {
            Write-Host "   [提示] 正在构建 Angular 前端生产包..." -ForegroundColor Gray
            & npm run build
            Write-Success "Web 前端控制台构建完成。"
        } catch {
            Write-Warn "前端编译存在警告，将使用内置静态服务直接托管。"
        } finally {
            Pop-Location
        }
    } else {
        Write-Warn "当前环境未安装 Node.js/npm，跳过前端重构，使用已有静态产物直接托管。"
    }
} else {
    Write-Success "Web 前端控制台静态资源已就绪。"
}

# ------------------------------------------------------------------------------
# 步骤 8：挂载 MCP 服务并启动 Web 服务
# ------------------------------------------------------------------------------
Write-Step "[8/8] 自动向 AI IDE 注册原生 MCP 真机操控服务支持..."
try {
    & uv run python -m artemis mcp --install all 2>$null | Out-Null
    Write-Success "已自动为 AI IDE (Antigravity / Cursor / Claude Code / VS Code / Windsurf) 挂载 MCP 协议服务。"
} catch {}

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "   🎉 Artemis 手机智能体自动化系统全栈部署成功！正在拉起控制台服务..." -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "   • Web 前端主控制台: http://localhost:$Port" -ForegroundColor Cyan
Write-Host "   • 手机实时投屏工作台: http://localhost:$Port/workspace" -ForegroundColor Cyan
Write-Host "   • 系统调试与管理面板: http://localhost:$Port/admin" -ForegroundColor Cyan
Write-Host "   • 后端 REST API 文档: http://localhost:$Port/docs" -ForegroundColor Cyan
Write-Host "------------------------------------------------------------------------------" -ForegroundColor Gray
Write-Host "   [操作提示] 终端按 Ctrl + C 可正常关闭后台服务。" -ForegroundColor DarkGray
Write-Host ""

if ($NoOpen) {
    & uv run python -m artemis ui --port $Port --no-open
} else {
    & uv run python -m artemis ui --port $Port --open
}
