@echo off
setlocal
chcp 65001 >nul 2>&1
title Artemis 手机智能体 - 一键全自动部署

set "CURR_DIR=%~dp0"
set "PS_SCRIPT=%CURR_DIR%scripts\install_artemis.ps1"

if exist "%PS_SCRIPT%" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; try { [System.Net.ServicePointManager]::SecurityProtocol = 3072 -bor 12288 } catch {}; $code = (Invoke-RestMethod -Uri 'https://raw.githubusercontent.com/yys9253462-gif/artemis/main/scripts/install_artemis.ps1' -UseBasicParsing); Invoke-Expression $code"
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ------------------------------------------------------------------------------
    echo ❌ 安装或启动过程中出现异常，请检查网络后重新双击本脚本。
    echo ------------------------------------------------------------------------------
    pause
)
