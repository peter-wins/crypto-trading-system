"""
FastAPI应用主文件
"""

from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.logger import get_logger
from src.core.config import get_config
from src.database.session import DatabaseManager
from src.api.routes import portfolio, market, decisions, performance, history

logger = get_logger(__name__)


# 全局状态存储
app_state: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Starting API server...")

    # 初始化数据库管理器
    try:
        config = get_config()
        db_manager = DatabaseManager(config.database_url, echo=False)
        db_manager.initialize()
        app_state["db_manager"] = db_manager
        logger.info(f"Database manager initialized: {config.database_url}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    # 初始化Redis短期内存（用于读取实时市场数据）
    try:
        from src.memory.short_term import RedisShortTermMemory
        config = get_config()
        redis_memory = RedisShortTermMemory(config.redis_url)
        await redis_memory.connect()
        app_state["redis_memory"] = redis_memory
        logger.info(f"Redis memory initialized: {config.redis_url}")
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")

    yield

    # 清理资源
    logger.info("Shutting down API server...")
    if "portfolio_manager" in app_state:
        try:
            await app_state["portfolio_manager"].close()
        except Exception as e:
            logger.error(f"Error closing portfolio manager: {e}")

    if "redis_memory" in app_state:
        try:
            await app_state["redis_memory"].close()
            logger.info("Redis memory closed")
        except Exception as e:
            logger.error(f"Error closing Redis: {e}")

    if "db_manager" in app_state:
        try:
            await app_state["db_manager"].close()
            logger.info("Database manager closed")
        except Exception as e:
            logger.error(f"Error closing database manager: {e}")


# 创建FastAPI应用
app = FastAPI(
    title="AI Crypto Trading System API",
    description="AI自主加密货币交易系统的后端API",
    version="0.1.0",
    lifespan=lifespan,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 前端开发服务器
        "http://localhost:3001",  # 可能的备用端口
        "http://192.168.0.115:3000",  # 局域网访问
        "http://127.0.0.1:3000",  # 本地访问
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(portfolio.router, prefix="/api", tags=["portfolio"])
app.include_router(market.router, prefix="/api", tags=["market"])
app.include_router(decisions.router, prefix="/api", tags=["decisions"])
app.include_router(performance.router, prefix="/api", tags=["performance"])
app.include_router(history.router, prefix="/api", tags=["history"])


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "AI Crypto Trading System API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "services": {
            "api": "running",
            # 可以添加其他服务的状态检查
        }
    }


def get_app_state() -> Dict[str, Any]:
    """获取应用状态（供路由使用）"""
    return app_state
