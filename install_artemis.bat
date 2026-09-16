@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0scripts\install_artemis.ps1" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_artemis.ps1" %*
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; try { [System.Net.ServicePointManager]::SecurityProtocol = 3072 -bor 12288 } catch {}; $f = Join-Path $env:TEMP 'artemis_installer_run.ps1'; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/yys9253462-gif/artemis/main/scripts/install_artemis.ps1' -OutFile $f -UseBasicParsing; & $f %*"
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Process exited with code %ERRORLEVEL%]
    pause
)
