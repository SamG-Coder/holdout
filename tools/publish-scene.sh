#!/usr/bin/env bash
# Publishes a compiled level: uploads it to a new GitHub release and records that release in
# scene.txt. Committing and pushing scene.txt is what deploys it: the Pages workflow takes
# the scene the file names from its release, checks it, hosts it where the game can stream
# it (tools/host-scene.sh), and points the game at it.
#
#   bash tools/publish-scene.sh [LEVEL.solstice] [TAG]
#
# The level defaults to build/levels/alder_ridge.solstice and the tag to scene-YYYY-MM-DD.
# Levels take minutes to build and hundreds of megabytes to store, and need Blender, so they
# are built on a PC rather than by CI. Needs the GitHub CLI, signed in.
set -euo pipefail
cd "$(dirname "$0")/.."

level="${1:-build/levels/alder_ridge.solstice}"
tag="${2:-scene-$(date +%Y-%m-%d)}"
name="$(basename "$level")"
[ -f "$level" ] || { echo "$level is missing: build the level first" >&2; exit 1; }

digest="$(sha256sum "$level" | cut -d' ' -f1)"
size="$(du -m "$level" | cut -f1)"
if grep -q "$digest" scene.txt 2>/dev/null; then
  echo "scene.txt already names this file: nothing to publish"
  exit 0
fi
# A second scene on the same day takes the next free tag.
base="$tag"; n=2
while gh release view "$tag" >/dev/null 2>&1; do tag="$base-$n"; n=$((n + 1)); done

echo "uploading $name ($size MB) to release $tag..."
gh release create "$tag" "$level" \
  --title "Scene: ${name%.solstice}, ${tag#scene-}" \
  --notes "The compiled level the game streams: \`$name\`, $size MB, SHA-256 \`$digest\`.

Built from \`art/levels/\` with \`levelc\`. The Pages workflow serves the scene that \`scene.txt\` names."

cat > scene.txt <<EOF
# The scene the game streams: its file name, the release of this repository that holds it,
# and its SHA-256. Written by tools/publish-scene.sh; pushing a change to this file hosts
# the new scene and deploys the game to read it.
$name $tag $digest
EOF
echo "scene.txt now names $tag. To deploy it:"
echo "  git add scene.txt && git commit -m \"Publish scene $tag\" && git push"
