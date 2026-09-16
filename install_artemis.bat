@echo off
setlocal
chcp 65001 >nul 2>&1
title Artemis 手机智能体 - 控制台管理中心

set "CURR_DIR=%~dp0"
set "PS_SCRIPT=%CURR_DIR%scripts\install_artemis.ps1"

rem 支持参数传入：如 install_artemis.bat start / install_artemis.bat stop / install_artemis.bat status
set "ARG=%~1"

if exist "%PS_SCRIPT%" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -Action "%ARG%"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; try { [System.Net.ServicePointManager]::SecurityProtocol = 3072 -bor 12288 } catch {}; $code = (Invoke-RestMethod -Uri 'https://raw.githubusercontent.com/yys9253462-gif/artemis/main/scripts/install_artemis.ps1' -UseBasicParsing); $fn = [scriptblock]::Create($code); & $fn -Action '%ARG%'"
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ------------------------------------------------------------------------------
    echo ❌ 操作执行过程中出现异常或已中断。
    echo ------------------------------------------------------------------------------
    pause
)
