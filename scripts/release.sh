#!/usr/bin/env bash

set -euo pipefail

tag="${1:-}"

if [[ -z "$tag" || "$tag" != v* ]]; then
  echo "Usage: scripts/release.sh v1.0.0" >&2
  exit 2
fi

for command_name in git gh python twine; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean. Commit or stash changes before releasing." >&2
  exit 1
fi

if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  echo "Tag already exists locally: $tag" >&2
  exit 1
fi

if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
  echo "Tag already exists on origin: $tag" >&2
  exit 1
fi

python -m pytest
rm -rf build dist
python -m build
twine check dist/*

git tag "$tag"
git push origin "$tag"

gh release create "$tag" dist/*.whl dist/*.tar.gz --title "$tag"
