#!/bin/bash
# Backend启动脚本

set -e

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "========================================="
echo "启动加密货币交易系统后端"
echo "========================================="
echo "Backend目录: $SCRIPT_DIR"
echo "项目根目录: $PROJECT_ROOT"
echo ""

# 检查虚拟环境
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "⚠️  未找到虚拟环境，正在创建..."
    cd "$PROJECT_ROOT"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r backend/requirements.txt
else
    echo "✓ 使用虚拟环境: $PROJECT_ROOT/venv"
    source "$PROJECT_ROOT/venv/bin/activate"
fi

# 检查 .env 文件
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "❌ 错误: 未找到 .env 配置文件"
    echo "请在项目根目录创建 .env 文件"
    exit 1
fi

echo "✓ 配置文件: $PROJECT_ROOT/.env"
echo ""

# 切换到 backend 目录运行
cd "$SCRIPT_DIR"

# 检查参数
if [ "$1" == "api" ]; then
    echo "🚀 启动 API 服务器..."
    echo "📖 API文档: http://localhost:8000/docs"
    echo "📖 ReDoc: http://localhost:8000/redoc"
    echo ""
    uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
else
    echo "🚀 启动交易系统主程序..."
    python main.py
fi
