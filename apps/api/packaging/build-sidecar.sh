#!/usr/bin/env bash
set -euo pipefail

# Builds only on Apple Silicon macOS. The output is a generated, ignored Tauri
# sidecar artifact; neither Python nor uv is required by the packaged runtime.
if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Phase 0C sidecar build requires Apple Silicon macOS (arm64)." >&2
  exit 1
fi

repo_root="$(cd "$(dirname "$0")/../../../" && pwd)"
api_root="$repo_root/apps/api"
output_dir="$repo_root/apps/desktop/src-tauri/binaries"
ion_uv_cache_dir="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/ion-os-uv-cache}"
ion_pyinstaller_cache_dir="${PYINSTALLER_CONFIG_DIR:-${TMPDIR:-/tmp}/ion-os-pyinstaller-cache}"

mkdir -p "$output_dir"
cd "$api_root"
UV_CACHE_DIR="$ion_uv_cache_dir" PYINSTALLER_CONFIG_DIR="$ion_pyinstaller_cache_dir" \
  uv --directory "$api_root" run --group packaging pyinstaller \
  --clean \
  --noconfirm \
  --distpath "$api_root/build/sidecar-dist" \
  --workpath "$api_root/build/sidecar-work" \
  "packaging/ion-api.spec"
cp "$api_root/build/sidecar-dist/ion-api" \
  "$output_dir/ion-api-aarch64-apple-darwin"
chmod 755 "$output_dir/ion-api-aarch64-apple-darwin"
