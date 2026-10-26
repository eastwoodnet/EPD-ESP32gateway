#!/usr/bin/env bash
# 一键同步并部署中继服务端至 192.168.1.254
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-192.168.1.254}"
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/opt/epd-server}"
REMOTE_PORT="${REMOTE_PORT:-8000}"

if ! [[ "$REMOTE_USER" =~ ^[A-Za-z_][A-Za-z0-9._-]*$ ]]; then
    echo "[错误] REMOTE_USER 格式无效"
    exit 1
fi
if ! [[ "$REMOTE_HOST" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "[错误] REMOTE_HOST 格式无效"
    exit 1
fi
if ! [[ "$REMOTE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] || [[ "$REMOTE_DIR" =~ (^|/)\.\.(/|$) ]]; then
    echo "[错误] REMOTE_DIR 必须是不含空白或 shell 元字符的绝对路径"
    exit 1
fi
if ! [[ "$REMOTE_PORT" =~ ^[0-9]+$ ]] || (( REMOTE_PORT < 1 || REMOTE_PORT > 65535 )); then
    echo "[错误] REMOTE_PORT 必须是 1~65535 之间的整数"
    exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$PROJECT_ROOT/server"
REMOTE_TARGET="$REMOTE_USER@$REMOTE_HOST"

if [ ! -d "$SERVER_DIR" ]; then
    echo "[错误] 服务端目录不存在: $SERVER_DIR"
    exit 1
fi

echo "==> [1/4] 同步服务端代码至 $REMOTE_TARGET:$REMOTE_DIR （保留远端运行数据）..."
rsync -avz \
    --exclude='/venv/' \
    --exclude='__pycache__/' \
    --exclude='*.py[cod]' \
    --exclude='/data/' \
    --exclude='/tests/' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='*.log' \
    --exclude='*.pem' \
    --exclude='*.key' \
    --exclude='*.crt' \
    --exclude='*.p12' \
    --exclude='*.pfx' \
    "$SERVER_DIR/" "$REMOTE_TARGET:$REMOTE_DIR/"

echo "==> [2/4] 检查远程 Python 环境并安装依赖 ..."
ssh "$REMOTE_TARGET" "set -e; cd '$REMOTE_DIR'; if [ ! -x venv/bin/python ]; then python3 -m venv venv; fi; venv/bin/python -m pip install -r requirements.txt"

echo "==> [3/4] 重启远程 systemd 服务 (epd-server.service) ..."
ssh "$REMOTE_TARGET" "systemctl restart epd-server && systemctl is-active epd-server"

echo "==> [4/4] 检查远程 HTTP 健康状态 ..."
ssh "$REMOTE_TARGET" "curl -fsS --max-time 10 http://127.0.0.1:$REMOTE_PORT/api/settings >/dev/null"

echo "=========================================================="
echo "✅ 服务端已成功部署至 http://$REMOTE_HOST:$REMOTE_PORT"
echo "=========================================================="
