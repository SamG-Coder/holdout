#!/usr/bin/env bash
# Puts the scene that scene.txt names where the game can stream it, and prints its address.
#
#   bash tools/host-scene.sh
#
# The game reads its level a little at a time, by HTTP Range, from a page on another origin.
# A release download allows the ranges but not the cross-origin read, and GitHub Pages will
# not deploy half a gigabyte. raw.githubusercontent.com allows both, for files in git of under
# 100 MB. So this takes the level from its release, checks its SHA-256, cuts it into 32 MiB
# parts, and pushes them as one commit to refs/scene/TAG in this repository. That is not a
# branch, so cloning the repository does not fetch it; raw.githubusercontent.com serves it
# all the same, at .../refs/scene/TAG/NAME.000 and so on, with NAME.parts.json saying how it
# was cut.
#
# Run by the Pages workflow, and safe to run again: a scene already hosted is only checked.
# The two newest scenes are kept, so that a game being played is not cut off by a new one.
set -euo pipefail
cd "$(dirname "$0")/.."

read -r name tag digest < <(grep -v '^#' scene.txt | grep .)
repo="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  remote="https://x-access-token:${GH_TOKEN}@github.com/$repo.git"
else
  remote="$(git remote get-url origin)"
fi
ref="refs/scene/$tag"
url="https://raw.githubusercontent.com/$repo/$ref/$name"

hosted() {
  curl -fsSL "$url.parts.json" 2>/dev/null | grep -q "$digest"
}

if git ls-remote --exit-code "$remote" "$ref" >/dev/null 2>&1; then
  hosted || { echo "$ref is there, but it is not the scene scene.txt names" >&2; exit 1; }
  echo "the scene is already hosted at $ref" >&2
else
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT
  echo "taking $name from the release $tag..." >&2
  gh release download "$tag" --repo "$repo" --pattern "$name" --dir "$work"
  echo "$digest  $work/$name" | sha256sum --check >&2

  part=$((32 * 1024 * 1024))
  mkdir "$work/out"
  split -b "$part" -d -a 3 "$work/$name" "$work/out/$name."
  size=$(wc -c < "$work/$name" | tr -d ' ')
  count=$(ls "$work/out/$name".[0-9][0-9][0-9] | wc -l | tr -d ' ')
  printf '{"size": %s, "part": %s, "count": %s, "sha256": "%s"}\n' "$size" "$part" "$count" "$digest" \
    > "$work/out/$name.parts.json"
  # The parts are compressed already: neither deltas nor line endings are to be looked for.
  printf '* -delta -text\n' > "$work/out/.gitattributes"
  printf 'The level of HOLDOUT, %s from the release %s, in parts for the game to stream.\nWritten by tools/host-scene.sh.\n' \
    "$name" "$tag" > "$work/out/README.md"

  echo "pushing $count parts to $ref..." >&2
  git -C "$work/out" init -q -b scene
  git -C "$work/out" config user.name "github-actions[bot]"
  git -C "$work/out" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  git -C "$work/out" config core.compression 0
  git -C "$work/out" add -A
  git -C "$work/out" commit -q -m "$name from the release $tag"
  git -C "$work/out" push -q "$remote" "HEAD:$ref" >&2

  # It takes a moment to be served.
  for _ in $(seq 1 30); do hosted && break; sleep 4; done
  hosted || { echo "pushed $ref, but $url.parts.json is not being served" >&2; exit 1; }

  # Keep this scene and the one before it. (A grep that finds nothing is no failure here.)
  git ls-remote "$remote" 'refs/scene/*' | cut -f2 | { grep -v "^$ref\$" || true; } | sort -V | head -n -1 | while read -r old; do
    echo "letting go of $old" >&2
    git push -q "$remote" --delete "$old" >&2 || true
  done
fi

echo "$url"
