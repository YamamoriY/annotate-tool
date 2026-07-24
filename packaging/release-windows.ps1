# Build and publish the Windows release for the version in pyproject.toml.
#
#   .\packaging\release-windows.ps1

$ErrorActionPreference = "Stop"

$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location (Split-Path -Parent $here)

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "gh was not found; install GitHub CLI and run 'gh auth login'"
}

& .\packaging\build-windows.ps1
if ($LASTEXITCODE -ne 0) { throw "Windows build failed ($LASTEXITCODE)" }

$pyproject = Get-Content pyproject.toml -Raw
if ($pyproject -notmatch '(?m)^\s*version\s*=\s*"([^"]+)"') {
    throw "could not read version from pyproject.toml"
}

$version = $Matches[1]
$tag = "v$version"
$assets = @(
    "dist\win\annotate-tool-$version-win.zip",
    "dist\win\annotate-tool-setup-$version.exe"
)

foreach ($asset in $assets) {
    if (-not (Test-Path -LiteralPath $asset -PathType Leaf)) {
        throw "release asset was not built: $asset"
    }
}

# The other OS may already have created this version's release. In that case,
# add/replace only the Windows assets instead of trying to create it again.
$previousErrorActionPreference = $ErrorActionPreference
try {
    # Windows PowerShell 5.1 turns a native command's stderr into an error record.
    # A missing release is an expected result here, so inspect the exit code instead.
    $ErrorActionPreference = "Continue"
    & gh release view $tag *> $null
    $releaseExists = $LASTEXITCODE -eq 0
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}

if ($releaseExists) {
    Write-Host "release: uploading Windows assets to $tag" -ForegroundColor Cyan
    & gh release upload $tag @assets --clobber
} else {
    Write-Host "release: creating $tag with Windows assets" -ForegroundColor Cyan
    & gh release create $tag @assets --title $tag --generate-notes
}

if ($LASTEXITCODE -ne 0) { throw "GitHub release failed ($LASTEXITCODE)" }
Write-Host "released: $tag" -ForegroundColor Green
