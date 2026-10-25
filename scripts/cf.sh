#!/usr/bin/env bash
# Run wrangler with a project-local login, isolated from the global one.
# Credentials live in .cloudflare-cli/ (gitignored).
#   scripts/cf.sh login --browser=false
#   scripts/cf.sh whoami
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export XDG_CONFIG_HOME="$root/.cloudflare-cli"
mkdir -p "$XDG_CONFIG_HOME"
cd "$root/apps/web"
exec pnpm exec wrangler "$@"
