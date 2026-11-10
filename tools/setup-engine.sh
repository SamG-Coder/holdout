#!/usr/bin/env bash
# Fetches the Solstice engine into engine/ at the commit engine.txt names, and applies the
# game's few additions to its renderer (patches/solstice-engine.patch).
#
#   bash tools/setup-engine.sh
#
# Safe to run again: an engine already at that commit, with the patch already applied, is
# left as it is.
set -euo pipefail
cd "$(dirname "$0")/.."

read -r repo commit < <(grep -v '^#' engine.txt | grep .)

if [ -d engine/.git ] && [ "$(git -C engine rev-parse HEAD)" = "$commit" ]; then
  echo "engine/ is at $repo@${commit:0:7}"
else
  if [ -d engine/.git ] && [ -n "$(git -C engine status --porcelain)" ]; then
    echo "engine/ has changes of its own and is not at ${commit:0:7}: move them aside first" >&2
    exit 1
  fi
  mkdir -p engine
  git -C engine init -q
  git -C engine remote remove origin 2>/dev/null || true
  git -C engine remote add origin "https://github.com/$repo.git"
  git -C engine fetch -q --depth 1 origin "$commit"
  git -C engine checkout -q FETCH_HEAD
  echo "fetched $repo@${commit:0:7} into engine/"
fi

if git -C engine apply --reverse --check ../patches/solstice-engine.patch 2>/dev/null; then
  echo "patches/solstice-engine.patch is already applied"
else
  git -C engine apply ../patches/solstice-engine.patch
  echo "applied patches/solstice-engine.patch"
fi
