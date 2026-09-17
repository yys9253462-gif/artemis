# Artemis MCP client discovery and registration.
# Only writes MCP configuration; it does not install dependencies or start services.

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$homeDir = $env:USERPROFILE
$appDataDir = $env:APPDATA
$localAppDataDir = $env:LOCALAPPDATA
$vscodeExtensions = Join-Path $homeDir ".vscode\extensions"
$clients = @(
    @{ Name = "Antigravity"; Target = "antigravity"; Paths = @("$localAppDataDir\Programs\Antigravity"); Commands = @("antigravity") },
    @{ Name = "Claude / Claude Code"; Target = "claude"; Paths = @("$appDataDir\Claude", "$localAppDataDir\Programs\Claude"); Commands = @("claude") },
    @{ Name = "Cursor"; Target = "cursor"; Paths = @("$appDataDir\Cursor", "$localAppDataDir\Programs\cursor"); Commands = @("cursor") },
    @{ Name = "Windsurf"; Target = "windsurf"; Paths = @("$appDataDir\Windsurf", "$localAppDataDir\Programs\Windsurf"); Commands = @("windsurf") },
    @{ Name = "Visual Studio Code / Copilot"; Target = "vscode"; Paths = @("$appDataDir\Code", "$localAppDataDir\Programs\Microsoft VS Code"); Commands = @("code") },
    @{ Name = "Cline"; Target = "cline"; Paths = @("$vscodeExtensions\saoudrizwan.claude-dev-*"); Commands = @() },
    @{ Name = "Roo Code"; Target = "roo"; Paths = @("$vscodeExtensions\rooveterinaryinc.roo-cline-*"); Commands = @() },
    @{ Name = "OpenClaw"; Target = "openclaw"; Paths = @(); Commands = @("openclaw") },
    @{ Name = "Codex"; Target = "codex"; Paths = @("$localAppDataDir\OpenAI\Codex"); Commands = @("codex") },
    @{ Name = "Hermes"; Target = "hermes"; Paths = @("$localAppDataDir\hermes"); Commands = @("hermes") },
    @{ Name = "WorkBuddy"; Target = "workbuddy"; Paths = @("$homeDir\.workbuddy\app"); Commands = @("workbuddy") }
)

$detected = @()
foreach ($client in $clients) {
    $installed = $false
    foreach ($marker in $client.Paths) {
        if ($marker.Contains("*")) {
            if (Get-ChildItem -Path $marker -ErrorAction SilentlyContinue | Select-Object -First 1) { $installed = $true; break }
        } elseif (Test-Path -LiteralPath $marker) {
            $installed = $true; break
        }
    }
    if (-not $installed) {
        foreach ($command in $client.Commands) {
            if (Get-Command $command -ErrorAction SilentlyContinue) { $installed = $true; break }
        }
    }
    if ($installed) { $detected += $client }
}

Write-Host ""
Write-Host "[MCP] Detecting local AI clients and registering ARTEMIS MCP..." -ForegroundColor Cyan
if ($detected.Count -eq 0) {
    Write-Host "   [WARN] No supported local AI clients detected; no MCP configuration was written." -ForegroundColor Yellow
    exit 0
}

Write-Host "   [Detected] $($detected.Name -join ', ')" -ForegroundColor Cyan
$success = @()
$failed = @()
foreach ($client in $detected) {
    & uv run python -m artemis mcp --install $client.Target 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $success += $client.Name } else { $failed += $client.Name }
}

Write-Host ""
Write-Host "   MCP configuration summary" -ForegroundColor Cyan
if ($success.Count -gt 0) { Write-Host "   [OK] Added: $($success -join ', ')" -ForegroundColor Green }
if ($failed.Count -gt 0) { Write-Host "   [FAIL] Failed: $($failed -join ', ')" -ForegroundColor Red }
Write-Host "   Restart each client to load ARTEMIS MCP tools." -ForegroundColor Gray
if ($failed.Count -gt 0) { exit 1 }
