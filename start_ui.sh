#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -n "${UV_BIN:-}" ]; then
  uv_bin="$UV_BIN"
elif command -v uv >/dev/null 2>&1; then
  uv_bin="$(command -v uv)"
elif [ -x /opt/homebrew/bin/uv ]; then
  uv_bin="/opt/homebrew/bin/uv"
elif [ -x /usr/local/bin/uv ]; then
  uv_bin="/usr/local/bin/uv"
else
  echo "未找到 uv，请先安装 uv 或设置 UV_BIN=/path/to/uv" >&2
  exit 1
fi

server_name="${SERVER_NAME:-127.0.0.1}"
port="${PORT:-7860}"

exec "$uv_bin" run python main.py ui --server-name "$server_name" --port "$port" "$@"
