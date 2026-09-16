# ==============================================================================
# Artemis 手机智能体 - Windows 全自动下载、装配与启动脚本 (install_artemis.ps1)
# ==============================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 启用现代安全网络协议 TLS 1.2 / 1.3
try {
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12 -bor [System.Net.SecurityProtocolType]::Tls13
} catch {}

Write-Host "==============================================================================" -ForegroundColor DarkCyan
Write-Host "       ☕ Artemis 手机智能体 - Windows 一键全自动极速装配启动器" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "   [说明] 本脚本专为 Windows 用户打造，无需预先安装 Python、Git 或配置环境。" -ForegroundColor Gray
Write-Host "          将全自动下载源码、安装环境、同步依赖并启动手机控制台！" -ForegroundColor Gray
Write-Host ""
Write-Host "------------------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not $ScriptDir) {
    $ScriptDir = [Environment]::GetFolderPath('Desktop')
}

# 判断安装目标路径
$target = Join-Path $ScriptDir "artemis"
if (Test-Path (Join-Path $ScriptDir "pyproject.toml")) {
    $target = $ScriptDir
}

# 如果不存在源码则自动克隆或拉取 GitHub ZIP
if (-not (Test-Path (Join-Path $target "pyproject.toml"))) {
    Write-Host "👉 [1/3] 正在从 GitHub 获取 Artemis 手机智能体最新完整源码..." -ForegroundColor Cyan
    
    $gitInstalled = (Get-Command git -ErrorAction SilentlyContinue) -ne $null
    if ($gitInstalled) {
        Write-Host "   [提示] 检测到系统中已安装 Git，正在克隆源码仓库..." -ForegroundColor Gray
        & git clone https://github.com/yys9253462-gif/artemis.git $target
    } else {
        Write-Host "   [提示] 未检测到 Git，正在从 GitHub 官方极速下载源码压缩包..." -ForegroundColor Yellow
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
    Write-Host "   ✅ 源码下载解压完成！" -ForegroundColor Green
}

# 进入目标目录并唤起部署引擎
$deployScript = Join-Path $target "scripts\deploy_windows.ps1"
$deployBat = Join-Path $target "deploy_windows.bat"

if (Test-Path $deployScript) {
    Set-Location $target
    Write-Host "👉 [2/3] 正在进入自动化装配与部署流程..." -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $deployScript
} elseif (Test-Path $deployBat) {
    Set-Location $target
    & $deployBat
} else {
    Write-Host "❌ 未能在目标目录找到部署脚本，请检查网络或重试。" -ForegroundColor Red
}
