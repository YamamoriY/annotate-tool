# Windows build script.
#
#   .\packaging\build-windows.ps1            # onedir (recommended for distribution)
#   .\packaging\build-windows.ps1 -OneFile   # single exe
#
# NOTE: messages are ASCII on purpose. Windows PowerShell 5.1 reads .ps1 files as
# the ANSI codepage unless they carry a UTF-8 BOM, which garbles non-ASCII strings.

param(
    [switch]$OneFile
)

# PyInstaller writes progress to stderr; with "Stop" that alone aborts the script
# on PowerShell 5.1. Success is determined by $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"

# dist/ and build/ are resolved against the current directory, so pin it to the repo root.
$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location (Split-Path -Parent $here)

# Regenerate app.ico from the master image so master edits are never missed.
Write-Host "icons:" -ForegroundColor Cyan
uv run python packaging\make_icons.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "  icon generation failed - building without an updated icon" -ForegroundColor Yellow
}

$spec = if ($OneFile) { "packaging\annotate-tool-onefile.spec" } else { "packaging\annotate-tool.spec" }

# Outputs are split per-OS so a macOS build in the same tree does not clobber this one.
Write-Host "building: $spec" -ForegroundColor Cyan
uv run pyinstaller $spec --noconfirm --workpath build\win --distpath dist\win
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed ($LASTEXITCODE)" }

$out = if ($OneFile) { "dist\win\annotate-tool-onefile.exe" } else { "dist\win\annotate-tool\annotate-tool.exe" }
Write-Host "done: $out" -ForegroundColor Green
