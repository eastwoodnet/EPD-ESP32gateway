#!/usr/bin/env bash
# 墨水屏服务端便捷启动脚本
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

# 1. 检查 Python 3 环境
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未检测到 python3，请先安装 Python 3.10+"
    exit 1
fi

# 2. 检查或自动创建虚拟环境
if [ ! -d "venv" ]; then
    echo "[初始化] 正在创建 Python 虚拟环境 (venv)..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    echo "[初始化] 正在安装依赖包..."
    ./venv/bin/pip install -r requirements.txt
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
exec ./venv/bin/uvicorn main:app --host "$HOST" --port "$PORT"
