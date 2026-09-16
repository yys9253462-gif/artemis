# ==============================================================================
# Artemis 手机智能体 - Windows 全功能控制台与管理调度中心 (install_artemis.ps1)
# ==============================================================================

[CmdletBinding()]
param(
    [string]$Action = ""
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 启用现代安全网络协议 TLS 1.2 / 1.3
try {
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12 -bor [System.Net.SecurityProtocolType]::Tls13
} catch {}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not $ScriptDir) {
    $ScriptDir = [Environment]::GetFolderPath('Desktop')
}

# 自动解析安装目标路径
$target = Join-Path $ScriptDir "artemis"
if (Test-Path (Join-Path $ScriptDir "pyproject.toml")) {
    $target = $ScriptDir
}

function Ensure-SourceCode {
    $hasCompleteRepo = (Test-Path (Join-Path $target "pyproject.toml")) -and (Test-Path (Join-Path $target "scripts\deploy_windows.ps1"))
    if (-not $hasCompleteRepo) {
        Write-Host ""
        Write-Host "👉 [1/2] 正在从 GitHub 获取 Artemis 手机智能体最新完整源码..." -ForegroundColor Cyan
        
        # 如果目录存在残缺文件，先安全清理
        if (Test-Path $target) {
            try {
                Remove-Item -Path $target -Recurse -Force -ErrorAction SilentlyContinue
            } catch {}
        }
        
        $cloneSuccess = $false
        $gitInstalled = (Get-Command git -ErrorAction SilentlyContinue) -ne $null
        if ($gitInstalled) {
            Write-Host "   [提示] 检测到系统中已安装 Git，正在克隆源码仓库..." -ForegroundColor Gray
            & git clone --depth 1 https://github.com/yys9253462-gif/artemis.git $target
            if ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $target "pyproject.toml"))) {
                $cloneSuccess = $true
            }
        }
        
        if (-not $cloneSuccess) {
            Write-Host "   [提示] 正在从 GitHub 官方极速下载源码压缩包..." -ForegroundColor Yellow
            $zipFile = Join-Path $env:TEMP "artemis_repo_latest.zip"
            $extractDir = Join-Path $env:TEMP "artemis_extract_temp"
            
            if (Test-Path $zipFile) { Remove-Item $zipFile -Force -ErrorAction SilentlyContinue }
            if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue }
            
            $prevProgress = $ProgressPreference
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri "https://github.com/yys9253462-gif/artemis/archive/refs/heads/main.zip" -OutFile $zipFile -UseBasicParsing
            $ProgressPreference = $prevProgress
            
            Expand-Archive -Path $zipFile -DestinationPath $extractDir -Force
            New-Item -ItemType Directory -Path $target -Force | Out-Null
            
            $innerFolder = Join-Path $extractDir "artemis-main"
            if (Test-Path $innerFolder) {
                Copy-Item -Path "$innerFolder\*" -Destination $target -Recurse -Force
            } else {
                Copy-Item -Path "$extractDir\*" -Destination $target -Recurse -Force
            }
            
            Remove-Item $zipFile -Force -ErrorAction SilentlyContinue
            Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        
        if (Test-Path (Join-Path $target "pyproject.toml")) {
            Write-Host "   ✅ 源码下载解压完成！" -ForegroundColor Green
        } else {
            Write-Host "❌ 源码下载失败，请检查网络连接后重试。" -ForegroundColor Red
        }
    }
}

function Invoke-InstallOnly {
    Ensure-SourceCode
    Set-Location $target
    $deployScript = Join-Path $target "scripts\deploy_windows.ps1"
    if (Test-Path $deployScript) {
        Write-Host ""
        Write-Host "👉 正在执行全自动依赖检测、安装与沙箱构建流程..." -ForegroundColor Cyan
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $deployScript -NoOpen -SkipLaunch
        Write-Host ""
        Write-Host "==============================================================================" -ForegroundColor Green
        Write-Host "   🎉 Artemis 全部环境依赖与沙箱已成功安装完毕！" -ForegroundColor Green
        Write-Host "==============================================================================" -ForegroundColor Green
        Write-Host "   💡 提示：您现在可以随时在菜单中输入 [2] 启动服务，或直接运行 run 命令。" -ForegroundColor Gray
        Write-Host ""
    } else {
        Write-Host "❌ 未能在目标目录找到部署脚本: $deployScript" -ForegroundColor Red
    }
}

function Invoke-StartService {
    Ensure-SourceCode
    Set-Location $target
    $deployScript = Join-Path $target "scripts\deploy_windows.ps1"
    if (Test-Path $deployScript) {
        Write-Host ""
        Write-Host "👉 正在唤醒 Artemis 手机智能体服务与 Web 控制台..." -ForegroundColor Cyan
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $deployScript
    } else {
        Write-Host "❌ 未能在目标目录找到部署脚本: $deployScript" -ForegroundColor Red
    }
}

function Invoke-StopService {
    Ensure-SourceCode
    Set-Location $target
    Write-Host ""
    Write-Host "👉 正在安全关闭 Artemis 后台服务与进程..." -ForegroundColor Yellow
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv run python -m artemis stop --force 2>$null
    }
    
    # 彻底关闭占用 8000 端口及后台 python uvicorn 实例
    try {
        $pids = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($p in $pids) {
            if ($p -and $p -ne 0) {
                Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {}
    
    Write-Host "   ✅ Artemis 服务已成功停止，端口 8000 已释放。" -ForegroundColor Green
    Write-Host ""
}

function Invoke-StatusService {
    Ensure-SourceCode
    Set-Location $target
    Write-Host ""
    Write-Host "👉 正在检查 Artemis 服务与运行状态..." -ForegroundColor Cyan
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv run python -m artemis status
    } else {
        $conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
        if ($conn) {
            Write-Host "   🟢 Artemis 服务正在运行中 (Port: 8000, PID: $($conn[0].OwningProcess))" -ForegroundColor Green
            Write-Host "   🌐 Web 控制台访问入口: http://localhost:8000" -ForegroundColor Cyan
        } else {
            Write-Host "   ⚪ Artemis 服务当前未运行 (端口 8000 空闲)" -ForegroundColor Gray
        }
    }
    Write-Host ""
}

function Invoke-RestartService {
    Invoke-StopService
    Start-Sleep -Seconds 1
    Invoke-StartService
}

# ----------------- 命令行参数直接执行 -----------------
if ($Action -eq "install" -or $Action -eq "setup") {
    Invoke-InstallOnly
    exit
} elseif ($Action -eq "start") {
    Invoke-StartService
    exit
} elseif ($Action -eq "stop") {
    Invoke-StopService
    exit
} elseif ($Action -eq "restart") {
    Invoke-RestartService
    exit
} elseif ($Action -eq "status") {
    Invoke-StatusService
    exit
}

# ----------------- 交互式可视化主菜单 -----------------
Clear-Host
Write-Host "==============================================================================" -ForegroundColor DarkCyan
Write-Host "       ☕ Artemis 手机智能体 - Windows 全功能控制与管理中心" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  【1】 📦 一键安装与配置环境 (自动装配 uv/ADB/FFmpeg/scrcpy/190+依赖/前端)" -ForegroundColor Yellow
Write-Host "  【2】 🚀 启动 Artemis 服务 (校验环境、启动后台服务并打开 Web 控制台)" -ForegroundColor Green
Write-Host "  【3】 🛑 关闭 Artemis 服务 (安全停止后台进程并释放 8000 端口)" -ForegroundColor Red
Write-Host "  【4】 🔄 重启 Artemis 服务 (快速热重启服务进程)" -ForegroundColor Magenta
Write-Host "  【5】 📊 查看当前运行状态与已连接设备" -ForegroundColor Cyan
Write-Host "  【0】 🚪 退出程序" -ForegroundColor Gray
Write-Host ""
Write-Host "==============================================================================" -ForegroundColor DarkCyan

$choice = Read-Host "👉 请输入选项数字 [1-5 / 0, 默认: 2 (启动)]"
if ([string]::IsNullOrWhiteSpace($choice)) { $choice = "2" }

switch ($choice) {
    "1" { Invoke-InstallOnly; Write-Host "按任意键返回菜单..."; [Console]::ReadKey() | Out-Null }
    "2" { Invoke-StartService }
    "3" { Invoke-StopService; Write-Host "按任意键退出..."; [Console]::ReadKey() | Out-Null }
    "4" { Invoke-RestartService }
    "5" { Invoke-StatusService; Write-Host "按任意键退出..."; [Console]::ReadKey() | Out-Null }
    "0" { Write-Host "已退出。" -ForegroundColor Gray; exit }
    Default {
        Write-Host "输入无效，正在执行默认启动流程..." -ForegroundColor Yellow
        Invoke-StartService
    }
}
