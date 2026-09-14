@echo off
rem ==============================================================================
rem Artemis Windows 一键全自动极速部署与启动脚本
rem 功能：自动检测并安装 uv、ADB、FFmpeg、scrcpy、Node.js、配置环境、构建前端并自动启动
rem ==============================================================================

chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Artemis Mobile Agent - Windows 一键全自动部署

cd /d "%~dp0"

echo ==============================================================================
echo       ☕ Artemis Mobile Agent - Windows 一键全自动部署与环境初始化
echo ==============================================================================
echo.

rem 检查以管理员或普通用户权限运行 PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deploy_windows.ps1" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ------------------------------------------------------------------------------
    echo ❌ 部署过程中出现异常，请根据上方红色提示排查。
    echo ------------------------------------------------------------------------------
    pause
)
