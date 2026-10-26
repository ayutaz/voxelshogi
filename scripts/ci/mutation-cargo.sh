#!/usr/bin/env bash
# cargo-mutants' CARGO adapter for the locked, default-feature core audit.
# Check coordinates before exercising sliders: a corrupt offset can otherwise
# allocate indefinitely before Cargo reaches the geometry integration tests.
set -eu

: "${VOXELSHOGI_MUTATION_CARGO:?Set the absolute path to the real Cargo executable}"
export CARGO="$VOXELSHOGI_MUTATION_CARGO"

if [ "${1:-}" = test ]; then
  build_only=false
  for arg in "$@"; do
    if [ "$arg" = --no-run ]; then build_only=true; fi
  done
  if [ "$build_only" = false ]; then
    "$CARGO" test --locked --package voxelshogi-core --test geometry_contracts
  fi
fi
exec "$CARGO" "$@"
