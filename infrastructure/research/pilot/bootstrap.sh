set -euo pipefail
uname -r > /root/voxelshogi-pilot-kernel.txt
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export CARGO_BUILD_JOBS=2
apt-get update -qq
apt-get install -y --no-install-recommends build-essential pkg-config curl ca-certificates git libvulkan1 vulkan-tools
if ! command -v cc >/dev/null 2>&1; then
 apt-get update -qq
 apt-get install -y --no-install-recommends build-essential pkg-config curl ca-certificates
fi
curl --proto '=https' --tlsv1.2 -fsSL https://astral.sh/uv/0.11.23/install.sh -o /tmp/voxelshogi-uv-install.sh
sh /tmp/voxelshogi-uv-install.sh
curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs -o /tmp/voxelshogi-rustup-install.sh
sh /tmp/voxelshogi-rustup-install.sh -y --profile minimal --default-toolchain 1.97.1
curl --proto '=https' --tlsv1.2 -fsSL https://astral.sh/uv/0.13.6/install.sh -o /tmp/voxelshogi-python-bootstrap-uv.sh
UV_INSTALL_DIR="$HOME/.local/share/voxelshogi-bootstrap-uv" sh /tmp/voxelshogi-python-bootstrap-uv.sh
"$HOME/.local/share/voxelshogi-bootstrap-uv/uv" python install 3.14.9
mkdir "$HOME/voxelshogi"
cd "$HOME/voxelshogi"
git init -q
git remote add origin https://github.com/ayutaz/voxelshogi.git
git fetch --depth 1 origin SOURCE_COMMIT_PLACEHOLDER
git checkout --detach FETCH_HEAD
uv sync --project infrastructure/cuda --locked
mkdir -p runs/p6/research-pilot
uv run --project infrastructure/cuda --locked python -m training.cuda_preflight runs/p6/research-pilot/cuda-preflight.json
printf '{"complete":true,"source_commit":"SOURCE_COMMIT_PLACEHOLDER"}\n' > runs/p6/research-pilot/bootstrap-complete.json
