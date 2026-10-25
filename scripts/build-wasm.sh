#!/usr/bin/env bash
# Builds the WASM engine into apps/web/src/wasm/pkg (git-ignored).
# Requires: rustup target wasm32-unknown-unknown, wasm-bindgen-cli matching
# the wasm-bindgen version pinned in crates/voxelshogi-wasm/Cargo.toml.
set -euo pipefail
cd "$(dirname "$0")/.."
PROFILE="${1:-release}"
cargo build --locked --profile "$PROFILE" --target wasm32-unknown-unknown -p voxelshogi-wasm
DIR="$PROFILE"; [ "$PROFILE" = "dev" ] && DIR=debug
wasm-bindgen --target web --out-dir apps/web/src/wasm/pkg \
  "target/wasm32-unknown-unknown/$DIR/voxelshogi_wasm.wasm"
ls -la apps/web/src/wasm/pkg
