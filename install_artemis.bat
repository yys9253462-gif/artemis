@echo off
rem ==============================================================================
rem ☕ Artemis 手机智能体 - Windows 一键全自动独立安装与极速启动器
rem 说明：用户只需要下载并双击本脚本，即可全自动拉取源码、装配全部运行环境并拉起系统！
rem ==============================================================================

chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Artemis 手机智能体 - Windows 一键全自动独立装配程序

echo ==============================================================================
echo       ☕ Artemis 手机智能体 - Windows 一键全自动极速装配启动器
echo ==============================================================================
echo.
echo   [说明] 本脚本专为 Windows 用户打造，无需预先安装 Python、Git 或配置环境。
echo          双击即可全自动克隆代码、安装环境、同步依赖并启动手机控制台！
echo.
echo ------------------------------------------------------------------------------
echo.

rem 检查当前目录下是否已存在 artemis 核心目录
set "TARGET_DIR=%~dp0artemis"
if exist "%~dp0pyproject.toml" (
    set "TARGET_DIR=%~dp0"
)

rem 启动内置的 PowerShell 全自动极速部署执行流
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;" ^
    "try { [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12 -bor [System.Net.SecurityProtocolType]::Tls13 } catch {};" ^
    "$target = '%TARGET_DIR%';" ^
    "if (-not (Test-Path $target\pyproject.toml)) {" ^
    "    Write-Host '👉 [1/5] 正在下载 Artemis 手机智能体最新完整源码...' -ForegroundColor Cyan;" ^
    "    if (Get-Command git -ErrorAction SilentlyContinue) {" ^
    "        git clone https://github.com/yys9253462-gif/artemis.git $target;" ^
    "    } else {" ^
    "        Write-Host '   [提示] 未检测到 Git，正在从 GitHub 官方极速下载源码压缩包...' -ForegroundColor Yellow;" ^
    "        $zip = \"$env:TEMP\artemis_main.zip\";" ^
    "        Invoke-WebRequest -Uri 'https://github.com/yys9253462-gif/artemis/archive/refs/heads/main.zip' -OutFile $zip -UseBasicParsing;" ^
    "        Expand-Archive -Path $zip -DestinationPath $env:TEMP -Force;" ^
    "        New-Item -ItemType Directory -Path $target -Force | Out-Null;" ^
    "        Copy-Item -Path \"$env:TEMP\artemis-main\*\" -Destination $target -Recurse -Force;" ^
    "        Remove-Item $zip -Force -ErrorAction SilentlyContinue;" ^
    "    }" ^
    "    Write-Host '   ✅ 源码获取完成！' -ForegroundColor Green;" ^
    "};" ^
    "if (Test-Path \"$target\deploy_windows.bat\") {" ^
    "    Set-Location $target;" ^
    "    & .\deploy_windows.bat;" ^
    "} else {" ^
    "    Write-Host '❌ 未能在目标目录找到安装引导脚本，请检查网络连接。' -ForegroundColor Red;" ^
    "}"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ------------------------------------------------------------------------------
    echo ❌ 安装或启动过程中出现异常，请检查网络连接后重新双击运行本脚本。
    echo ------------------------------------------------------------------------------
    pause
)
