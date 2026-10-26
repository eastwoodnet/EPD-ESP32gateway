#!/usr/bin/env bash
# 墨水屏服务端便捷启动脚本
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
    echo "[错误] PORT 必须是 1~65535 之间的整数"
    exit 1
fi

# 1. 检查 Python 3 环境
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未检测到 python3，请先安装 Python 3.10+"
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
    echo "[错误] 当前 python3 版本低于 3.10"
    exit 1
fi

# 2. 检查或自动创建虚拟环境
if [ ! -d "venv" ]; then
    echo "[初始化] 正在创建 Python 虚拟环境 (venv)..."
    python3 -m venv venv
    ./venv/bin/python -m pip install --upgrade pip
fi
if [ ! -x "./venv/bin/python" ] || ! ./venv/bin/python -m pip --version &>/dev/null; then
    echo "[错误] venv 已存在但不可用，请修复或移走后重试"
    exit 1
fi

REQUIREMENTS_HASH="$(python3 -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest())')"
REQUIREMENTS_STAMP="venv/.requirements.sha256"
CURRENT_HASH=""
if [ -f "$REQUIREMENTS_STAMP" ]; then
    CURRENT_HASH="$(<"$REQUIREMENTS_STAMP")"
fi
if [ "$CURRENT_HASH" != "$REQUIREMENTS_HASH" ] || ! ./venv/bin/python -c 'import fastapi, httpx, jinja2, multipart, PIL, pydantic, uvicorn' &>/dev/null; then
    echo "[初始化] 正在安装或更新依赖包..."
    ./venv/bin/python -m pip install -r requirements.txt
    printf '%s\n' "$REQUIREMENTS_HASH" > "$REQUIREMENTS_STAMP"
fi

# 3. 检查中文字体支持
HAS_FONT=false
for font in \
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc" \
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc" \
    "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc" \
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc" \
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc" \
    "fonts/font.ttc" "fonts/font.ttf"; do
    if [ -f "$font" ]; then
        HAS_FONT=true
        break
    fi
done

if [ "$HAS_FONT" = false ]; then
    echo "[提示] 系统未检测到常用中文字体，建议安装: sudo apt install fonts-wqy-zenhei (或在 server/fonts/ 下放置中文字体文件 font.ttc)"
fi

mkdir -p data/photos fonts

echo "[启动] 正在启动墨水屏数据中继服务 (http://${HOST}:${PORT})..."
exec ./venv/bin/python -m uvicorn main:app --host "$HOST" --port "$PORT"
