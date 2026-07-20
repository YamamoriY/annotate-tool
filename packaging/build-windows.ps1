# Windows build script.
#
#   .\packaging\build-windows.ps1                # onedir + installer (recommended)
#   .\packaging\build-windows.ps1 -NoInstaller   # onedir only
#   .\packaging\build-windows.ps1 -OneFile       # single exe (no installer)
#
# NOTE: messages are ASCII on purpose. Windows PowerShell 5.1 reads .ps1 files as
# the ANSI codepage unless they carry a UTF-8 BOM, which garbles non-ASCII strings.

param(
    [switch]$OneFile,
    [switch]$NoInstaller
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

# The zip and the installer both package the onedir tree, so neither has anything
# to work with after a onefile build.
if ($OneFile) { return }

# Single source of truth for the version - installer.iss takes it from here too,
# via /D below.
$pyproject = Get-Content pyproject.toml -Raw
if ($pyproject -notmatch '(?m)^\s*version\s*=\s*"([^"]+)"') {
    throw "could not read version from pyproject.toml"
}
$version = $Matches[1]

# Portable build for anyone who cannot or does not want to run an installer.
$zip = "dist\win\annotate-tool-$version-win.zip"
Write-Host "zip: $zip" -ForegroundColor Cyan
Compress-Archive -Path dist\win\annotate-tool -DestinationPath $zip -CompressionLevel Optimal -Force

if ($NoInstaller) { return }

# winget installs Inno Setup per-user, so it is not on PATH and not under Program
# Files. Check both, plus PATH in case it was installed some other way.
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
}

# A missing Inno Setup is not a build failure - the onedir output above is still
# usable. Say so and stop rather than throwing.
if (-not $iscc) {
    Write-Host "installer: skipped - Inno Setup not found" -ForegroundColor Yellow
    Write-Host "  install it with: winget install --id JRSoftware.InnoSetup -e" -ForegroundColor Yellow
    return
}

Write-Host "installer: packaging\installer.iss" -ForegroundColor Cyan
& $iscc "/DAppVersion=$version" packaging\installer.iss | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) { throw "iscc failed ($LASTEXITCODE)" }
