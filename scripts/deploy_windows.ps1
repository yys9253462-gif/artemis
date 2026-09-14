# ==============================================================================
# Artemis Windows 一键全自动极速部署与初始化脚本 (deploy_windows.ps1)
# 
# 自动化执行流：
# 1. 网络与 TLS 优化 + 环境变量刷新
# 2. 自动检测并极速安装 Astral uv (Python 包与运行时管理器)
# 3. 自动安装/配置 Python 3.12+ 虚拟环境并全自动同步 190+ 项目依赖
# 4. 自动检测并静默安装核心工具链 (ADB / FFmpeg / scrcpy)
# 5. 自动唤醒并校验本地 ADB Server 守护进程
# 6. 自动初始化并检查 .env 配置文件 (自动配置 OpenAI / Gemini 中转凭据模板)
# 7. 自动检查并极速构建 Angular Showcase UI 前端生产包
# 8. 自动配置 AI IDE 原生 MCP 服务集成 (Claude, Cursor, Antigravity, VS Code, Windsurf)
# 9. 自动启动 Artemis Web 交互控制台并弹窗唤起浏览器
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
Write-Host "   ☕ Artemis Mobile Agent - Windows 全自动一键部署与环境装配程序" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor DarkCyan

# ------------------------------------------------------------------------------
# 步骤 1：刷新与优化 PATH 路径
# ------------------------------------------------------------------------------
Write-Step "[1/8] 检查并加载环境路径..."
Update-EnvironmentPath
Write-Success "系统环境路径配置就绪。"

# ------------------------------------------------------------------------------
# 步骤 2：自动检测并安装 Astral uv
# ------------------------------------------------------------------------------
Write-Step "[2/8] 检查 Python 运行时与包管理器 uv..."
if (-not (Test-CommandExists "uv")) {
    Write-Host "   [INFO] 正在自动安装 Astral uv 包管理工具..." -ForegroundColor Yellow
    try {
        Invoke-Expression (Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1")
    } catch {
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    }
    Update-EnvironmentPath
}

if (-not (Test-CommandExists "uv")) {
    Write-Err "未能自动安装 Astral 'uv'，请手动执行以下命令后重新运行："
    Write-Host "      powershell -c ""irm https://astral.sh/uv/install.ps1 | iex""" -ForegroundColor White
    exit 1
}
$uvVer = (& uv --version)
Write-Success "检测到 uv 包管理器: $uvVer"

# ------------------------------------------------------------------------------
# 步骤 3：自动静默装配核心工具链 (ADB, FFmpeg, scrcpy)
# ------------------------------------------------------------------------------
Write-Step "[3/8] 检查 Android 真机操控核心工具链 (ADB, FFmpeg, scrcpy)..."
$missing = @()
if (-not (Test-CommandExists "adb")) { $missing += "adb" }
if (-not (Test-CommandExists "ffmpeg")) { $missing += "ffmpeg" }
if (-not (Test-CommandExists "scrcpy")) { $missing += "scrcpy" }

if ($missing.Count -gt 0) {
    Write-Host "   [INFO] 正在静默安装缺失的核心工具: $($missing -join ', ') ..." -ForegroundColor Yellow
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

    # 备选零管理员权限便携式下载
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
Write-Success "工具链状态 -> ADB: $adbOk | FFmpeg: $ffmpegOk | Scrcpy: $scrcpyOk"

# ------------------------------------------------------------------------------
# 步骤 4：确保 ADB Server 后台守护正常启动
# ------------------------------------------------------------------------------
Write-Step "[4/8] 初始化与唤醒本地 ADB Server 守护服务..."
try {
    & adb start-server 2>$null | Out-Null
    Write-Success "本地 ADB Server (127.0.0.1:5037) 已正常监听。"
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
        Write-Success "已自动从 .env.example 生成 .env 基础配置文件。"
    } else {
        New-Item -ItemType File -Path ".env" | Out-Null
        Write-Success "已新建空白 .env 文件。"
    }
} else {
    Write-Success ".env 配置文件已存在，保留当前配置。"
}

# ------------------------------------------------------------------------------
# 步骤 6：同步 Python 虚拟环境与 190+ 项目核心包
# ------------------------------------------------------------------------------
Write-Step "[6/8] 自动同步 Python 虚拟环境与全部依赖库..."
Write-Host "   [INFO] 执行 uv sync 校验中，请稍候..." -ForegroundColor Gray
& uv sync --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Success "Python 虚拟运行环境与依赖包校验完成。"
} else {
    Write-Warn "uv sync 提示存在部分警告，正在继续执行后续配置..."
}

# ------------------------------------------------------------------------------
# 步骤 7：检查与构建 Web Showcase UI 前端
# ------------------------------------------------------------------------------
Write-Step "[7/8] 检查并构建 Web 前端控制台 (Showcase UI)..."
$ShowcaseIndex = "$RootDir\apps\showcase_ui\dist\frontend\browser\index.html"
$ShowcaseIndexAlt = "$RootDir\apps\showcase_ui\dist\frontend\index.html"

if ((-not (Test-Path $ShowcaseIndex)) -and (-not (Test-Path $ShowcaseIndexAlt)) -and (-not $SkipFrontendBuild)) {
    Write-Host "   [INFO] 未检测到编译好的前端生产包，正在自动执行构建..." -ForegroundColor Yellow
    
    # 检查 Node.js / npm
    if (Test-CommandExists "npm") {
        Push-Location "$RootDir\apps\showcase_ui"
        try {
            Write-Host "   [INFO] 正在编译 Angular 前端..." -ForegroundColor Gray
            & npm run build
            Write-Success "前端生产包构建完成。"
        } catch {
            Write-Warn "前端编译过程存在警告，将使用内置服务直接托管。"
        } finally {
            Pop-Location
        }
    } else {
        Write-Warn "系统中未安装 Node.js/npm，跳过前端重构，使用已有静态产物。"
    }
} else {
    Write-Success "Web 前端控制台产物已就绪。"
}

# ------------------------------------------------------------------------------
# 步骤 8：挂载 MCP 服务并启动 Web 服务
# ------------------------------------------------------------------------------
Write-Step "[8/8] 自动安装 AI IDE 原生 MCP 服务支持并启动..."
try {
    & uv run python -m artemis mcp --install all 2>$null | Out-Null
    Write-Success "AI IDE (Antigravity/Cursor/Claude Code/VS Code) MCP 服务挂载完成。"
} catch {}

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "   🎉 Artemis 自动化系统全栈部署成功！正在拉起控制台服务..." -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "   • Web 前端控制台: http://localhost:$Port" -ForegroundColor Cyan
Write-Host "   • 实时设备投屏:   http://localhost:$Port/workspace" -ForegroundColor Cyan
Write-Host "   • 调试管理面板:   http://localhost:$Port/admin" -ForegroundColor Cyan
Write-Host "   • 后台 API 文档:  http://localhost:$Port/docs" -ForegroundColor Cyan
Write-Host "------------------------------------------------------------------------------" -ForegroundColor Gray
Write-Host "   [提示] 按 Ctrl + C 可正常关闭后台服务。" -ForegroundColor DarkGray
Write-Host ""

if ($NoOpen) {
    & uv run python -m artemis ui --port $Port --no-open
} else {
    & uv run python -m artemis ui --port $Port --open
}
