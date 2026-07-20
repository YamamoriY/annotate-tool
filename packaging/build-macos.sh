#!/usr/bin/env bash
# macOS build script.
#
#   ./packaging/build-macos.sh            # onedir + .app bundle (recommended)
#   ./packaging/build-macos.sh --onefile  # single executable
#
# Mirrors packaging/build-windows.ps1. Outputs go to dist/mac/ so builds for
# different operating systems can coexist in one working tree.

set -euo pipefail

onefile=0
for arg in "$@"; do
    case "$arg" in
        --onefile) onefile=1 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

# dist/ and build/ are resolved against the current directory, so pin it to the repo root.
cd "$(dirname "$(dirname "$(realpath "$0")")")"

# Regenerate app.icns from the master image so master edits are never missed.
echo "icons:"
if ! uv run python packaging/make_icons.py; then
    echo "  icon generation failed - building without an updated icon"
fi

if [ "$onefile" -eq 1 ]; then
    spec="packaging/annotate-tool-onefile.spec"
    out="dist/mac/annotate-tool-onefile"
else
    spec="packaging/annotate-tool.spec"
    out="dist/mac/annotate-tool.app"
fi

echo "building: $spec"
uv run pyinstaller "$spec" --noconfirm --workpath build/mac --distpath dist/mac

echo "done: $out"

# Only the .app is worth zipping - a bare onefile executable can be uploaded as is.
if [ "$onefile" -eq 1 ]; then
    exit 0
fi

# Same single source of truth for the version as build-windows.ps1.
version=$(sed -n 's/^[[:space:]]*version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' pyproject.toml | head -n 1)
if [ -z "$version" ]; then
    echo "could not read version from pyproject.toml" >&2
    exit 1
fi

# A .app is a directory holding symlinks and permission bits, so it has to be
# zipped before distribution. ditto preserves them; zip(1) and Finder do not.
zip="dist/mac/annotate-tool-$version-mac.zip"
echo "zip: $zip"
rm -f "$zip"
ditto -c -k --keepParent "$out" "$zip"
