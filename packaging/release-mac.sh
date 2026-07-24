#!/usr/bin/env bash
# Build and publish the macOS release for the version in pyproject.toml.
#
#   bash packaging/release-mac.sh

set -euo pipefail

cd "$(dirname "$(dirname "$(realpath "$0")")")"

if ! command -v gh >/dev/null 2>&1; then
    echo "gh was not found; install GitHub CLI and run 'gh auth login'" >&2
    exit 1
fi

./packaging/build-macos.sh

version=$(sed -n 's/^[[:space:]]*version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' pyproject.toml | head -n 1)
if [ -z "$version" ]; then
    echo "could not read version from pyproject.toml" >&2
    exit 1
fi

tag="v$version"
asset="dist/mac/annotate-tool-$version-mac.zip"
if [ ! -f "$asset" ]; then
    echo "release asset was not built: $asset" >&2
    exit 1
fi

# The other OS may already have created this version's release. In that case,
# add/replace only the macOS asset instead of trying to create it again.
if gh release view "$tag" >/dev/null 2>&1; then
    echo "release: uploading macOS asset to $tag"
    gh release upload "$tag" "$asset" --clobber
else
    echo "release: creating $tag with macOS asset"
    gh release create "$tag" "$asset" --title "$tag" --generate-notes
fi

echo "released: $tag"
