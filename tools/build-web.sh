#!/usr/bin/env bash
# Builds the browser game into dist/, a self-contained static site.
#
#   bash tools/build-web.sh [--split] [LEVEL.solstice]
#
# The level defaults to build/levels/alder_ridge.solstice. With --split it is cut into parts
# of 64 MiB with a note of how, which the page reads as it would the one file: GitHub Pages
# will not deploy a single file of several hundred megabytes. To try it:
#   python engine/scripts/serve.py --directory dist --port 8765
# and open http://localhost:8765 in Chrome or Edge.
set -euo pipefail
cd "$(dirname "$0")/.."

split_level=false
if [ "${1:-}" = "--split" ]; then split_level=true; shift; fi
level="${1:-build/levels/alder_ridge.solstice}"
version=$(grep -A1 '^name = "wasm-bindgen"$' Cargo.lock | sed -n 's/^version = "\(.*\)"$/\1/p')
bindgen="build/tools/bin/wasm-bindgen"
if ! "$bindgen" --version 2>/dev/null | grep -q "$version"; then
  echo "installing wasm-bindgen-cli $version..."
  cargo install wasm-bindgen-cli --version "$version" --root build/tools --locked
fi

# SIMD halves the cost of physics in the browser, and every browser with WebGPU has it. A
# target folder of its own, since different compiler flags can't share compiled crates.
RUSTFLAGS="-C target-feature=+simd128" \
  cargo build --release --target wasm32-unknown-unknown -p holdout --lib --target-dir target/web
mkdir -p dist/pkg dist/assets
"$bindgen" --target web --no-typescript --out-dir dist/pkg \
  target/web/wasm32-unknown-unknown/release/holdout.wasm
cp web/index.html web/style.css web/game.js web/audio.js dist/
rm -f dist/assets/level.solstice dist/assets/level.solstice.*
if [ -e "$level" ] && $split_level; then
  part=$((64 * 1024 * 1024))
  split -b "$part" -d -a 3 "$level" dist/assets/level.solstice.
  size=$(wc -c < "$level" | tr -d ' ')
  count=$(ls dist/assets/level.solstice.[0-9][0-9][0-9] | wc -l | tr -d ' ')
  printf '{"size": %s, "part": %s, "count": %s}\n' "$size" "$part" "$count" > dist/assets/level.solstice.parts.json
elif [ -e "$level" ]; then
  # A hard link keeps a big level from taking the disk twice.
  ln -f "$level" dist/assets/level.solstice 2>/dev/null || cp "$level" dist/assets/level.solstice
else
  echo "warning: $level is missing: build the level first"
fi
ls -la dist/pkg/*.wasm dist/assets/ | awk '{print $5, $9}'
echo "built dist/"
