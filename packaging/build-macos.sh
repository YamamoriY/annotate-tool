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
