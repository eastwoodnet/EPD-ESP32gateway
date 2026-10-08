#!/usr/bin/env bash
# 一键同步并部署中继服务端至 192.168.1.254
set -e

REMOTE_HOST="${REMOTE_HOST:-192.168.1.254}"
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/opt/epd-server}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$PROJECT_ROOT/server"

echo "==> [1/3] 同步服务端文件至 $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR ..."
rsync -avz --exclude 'venv' --exclude '__pycache__' --exclude '*.pyc' \
    "$SERVER_DIR/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"

echo "==> [2/3] 重启远程 systemd 服务 (epd-server.service) ..."
ssh "$REMOTE_USER@$REMOTE_HOST" "systemctl restart epd-server"

echo "==> [3/3] 检查服务运行状态 ..."
ssh "$REMOTE_USER@$REMOTE_HOST" "systemctl status epd-server --no-pager -l"

echo "=========================================================="
echo "✅ 服务端已成功部署至 http://$REMOTE_HOST:8000"
echo "=========================================================="
