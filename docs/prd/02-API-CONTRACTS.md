# 模块接口契约

本文档定义各模块之间的接口契约。所有接口使用Python Protocol或抽象基类定义，确保模块间松耦合。

## 1. 接口设计原则

1. **依赖倒置**: 依赖抽象接口，不依赖具体实现
2. **单一职责**: 每个接口只负责一个职责
3. **接口隔离**: 不强迫实现不需要的方法
4. **里氏替换**: 实现类可以替换接口类型

## 2. 感知模块接口

### 2.1 市场数据采集接口

```python
from abc import ABC, abstractmethod
from typing import Protocol, List
from datetime import datetime
from src.models.market import OHLCVData, OrderBook, Ticker

class IMarketDataCollector(Protocol):
    """市场数据采集接口"""

    async def get_ticker(self, symbol: str) -> Ticker:
        """
        获取ticker数据

        Args:
            symbol: 交易对，如 "BTC/USDT"

        Returns:
            Ticker对象

        Raises:
            DataCollectionError: 数据采集失败
        """
        ...

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: int | None = None,
        limit: int = 100
    ) -> List[OHLCVData]:
        """
        获取K线数据

        Args:
            symbol: 交易对
            timeframe: 时间周期，如 "1m", "5m", "1h", "1d"
            since: 起始时间戳(毫秒)
            limit: 数量限制

        Returns:
            OHLCV数据列表

        Raises:
            DataCollectionError: 数据采集失败
        """
        ...

    async def get_orderbook(
        self,
        symbol: str,
        limit: int = 20
    ) -> OrderBook:
        """
        获取订单簿

        Args:
            symbol: 交易对
            limit: 深度限制

        Returns:
            OrderBook对象

        Raises:
            DataCollectionError: 数据采集失败
        """
        ...

    async def subscribe_ticker(
        self,
        symbol: str,
        callback: callable
    ) -> None:
        """
        订阅ticker实时数据

        Args:
            symbol: 交易对
            callback: 回调函数，签名: async def callback(ticker: Ticker)

        Raises:
            SubscriptionError: 订阅失败
        """
        ...
```

**实现文件**: `src/perception/market_data.py`

**实现类**: `CCXTMarketDataCollector`

### 2.2 技术指标计算接口

```python
from typing import Protocol, Dict, Any
from decimal import Decimal

class IIndicatorCalculator(Protocol):
    """技术指标计算接口"""

    def calculate_sma(
        self,
        prices: List[Decimal],
        period: int
    ) -> List[Decimal]:
        """计算简单移动平均"""
        ...

    def calculate_ema(
        self,
        prices: List[Decimal],
        period: int
    ) -> List[Decimal]:
        """计算指数移动平均"""
        ...

    def calculate_rsi(
        self,
        prices: List[Decimal],
        period: int = 14
    ) -> List[Decimal]:
        """计算RSI"""
        ...

    def calculate_macd(
        self,
        prices: List[Decimal],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Dict[str, List[Decimal]]:
        """
        计算MACD

        Returns:
            {"macd": [...], "signal": [...], "histogram": [...]}
        """
        ...

    def calculate_bollinger_bands(
        self,
        prices: List[Decimal],
        period: int = 20,
        std_dev: int = 2
    ) -> Dict[str, List[Decimal]]:
        """
        计算布林带

        Returns:
            {"upper": [...], "middle": [...], "lower": [...]}
        """
        ...
```

**实现文件**: `src/perception/indicators.py`

**实现类**: `TALibIndicatorCalculator` 或 `PandasIndicatorCalculator`

## 3. 记忆系统接口

### 3.1 短期记忆接口

```python
from typing import Protocol, Any, Optional
from datetime import timedelta

class IShortTermMemory(Protocol):
    """短期记忆接口（基于Redis）"""

    async def set(
        self,
        key: str,
        value: Any,
        ttl: timedelta | None = None
    ) -> bool:
        """
        存储数据

        Args:
            key: 键
            value: 值（自动序列化）
            ttl: 过期时间

        Returns:
            是否成功
        """
        ...

    async def get(self, key: str) -> Any | None:
        """
        获取数据

        Args:
            key: 键

        Returns:
            值（自动反序列化），不存在返回None
        """
        ...

    async def delete(self, key: str) -> bool:
        """删除数据"""
        ...

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        ...

    async def get_market_context(self, symbol: str) -> MarketContext | None:
        """获取市场上下文"""
        ...

    async def update_market_context(
        self,
        symbol: str,
        context: MarketContext
    ) -> bool:
        """更新市场上下文"""
        ...

    async def get_trading_context(self) -> TradingContext | None:
        """获取交易上下文"""
        ...

    async def update_trading_context(
        self,
        context: TradingContext
    ) -> bool:
        """更新交易上下文"""
        ...
```

**实现文件**: `src/memory/short_term.py`

**实现类**: `RedisShortTermMemory`

### 3.2 长期记忆接口

```python
from typing import Protocol, List
from src.models.memory import TradingExperience, MemoryQuery

class ILongTermMemory(Protocol):
    """长期记忆接口（基于向量数据库）"""

    async def store_experience(
        self,
        experience: TradingExperience
    ) -> str:
        """
        存储交易经验

        Args:
            experience: 交易经验对象

        Returns:
            经验ID
        """
        ...

    async def search_similar_experiences(
        self,
        query: MemoryQuery
    ) -> List[TradingExperience]:
        """
        检索相似经验

        Args:
            query: 查询对象

        Returns:
            相似经验列表，按相似度排序
        """
        ...

    async def update_experience(
        self,
        experience_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        更新经验（如添加反思）

        Args:
            experience_id: 经验ID
            updates: 更新字段

        Returns:
            是否成功
        """
        ...

    async def delete_experience(
        self,
        experience_id: str
    ) -> bool:
        """删除经验"""
        ...

    async def get_experience_by_id(
        self,
        experience_id: str
    ) -> TradingExperience | None:
        """根据ID获取经验"""
        ...
```

**实现文件**: `src/memory/long_term.py`

**实现类**: `QdrantLongTermMemory`

### 3.3 记忆检索接口

```python
from typing import Protocol, List

class IMemoryRetrieval(Protocol):
    """记忆检索接口（RAG）"""

    async def retrieve_relevant_context(
        self,
        current_situation: str,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        检索相关上下文

        Args:
            current_situation: 当前情况描述
            top_k: 返回结果数量

        Returns:
            {
                "similar_experiences": List[TradingExperience],
                "current_context": TradingContext,
                "market_context": MarketContext
            }
        """
        ...

    async def build_context_for_llm(
        self,
        symbol: str,
        decision_type: str  # "strategic" or "tactical"
    ) -> str:
        """
        构建给LLM的上下文提示

        Args:
            symbol: 交易对
            decision_type: 决策类型

        Returns:
            格式化的上下文字符串
        """
        ...
```

**实现文件**: `src/memory/retrieval.py`

**实现类**: `RAGMemoryRetrieval`

## 4. 决策引擎接口

### 4.1 LLM客户端接口

```python
from typing import Protocol, List, Dict, Any, Optional

class Message(BaseModel):
    """消息模型"""
    role: str  # "system", "user", "assistant"
    content: str

class ToolCall(BaseModel):
    """工具调用"""
    name: str
    arguments: Dict[str, Any]

class LLMResponse(BaseModel):
    """LLM响应"""
    content: str | None
    tool_calls: List[ToolCall] | None
    finish_reason: str
    tokens_used: int

class ILLMClient(Protocol):
    """LLM客户端接口"""

    async def chat(
        self,
        messages: List[Message],
        tools: List[Dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> LLMResponse:
        """
        调用LLM进行对话

        Args:
            messages: 消息历史
            tools: 可用工具列表（function calling）
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            LLM响应

        Raises:
            LLMError: 调用失败
        """
        ...

    async def embed(self, text: str) -> List[float]:
        """
        生成文本向量

        Args:
            text: 输入文本

        Returns:
            向量表示

        Raises:
            EmbeddingError: 向量化失败
        """
        ...
```

**实现文件**: `src/decision/llm_client.py`

**实现类**: `DeepSeekClient`, `OpenAIClient`

### 4.2 战略决策器接口

```python
from typing import Protocol
from src.models.decision import StrategyConfig, TradingSignal

class IStrategist(Protocol):
    """战略决策器接口"""

    async def analyze_market_regime(
        self,
        symbol: str
    ) -> Dict[str, Any]:
        """
        分析市场状态

        Returns:
            {
                "regime": "bull/bear/sideways",
                "confidence": float,
                "reasoning": str,
                "key_factors": List[str]
            }
        """
        ...

    async def make_strategic_decision(
        self,
        portfolio: Portfolio
    ) -> StrategyConfig:
        """
        制定战略决策

        Args:
            portfolio: 当前投资组合

        Returns:
            策略配置

        Raises:
            DecisionError: 决策失败
        """
        ...

    async def update_risk_parameters(
        self,
        performance: PerformanceMetrics
    ) -> Dict[str, Decimal]:
        """
        根据绩效更新风险参数

        Returns:
            {
                "max_position_size": Decimal,
                "max_daily_loss": Decimal,
                ...
            }
        """
        ...
```

**实现文件**: `src/decision/strategist.py`

**实现类**: `LLMStrategist`

### 4.3 战术交易器接口

```python
from typing import Protocol
from src.models.decision import TradingSignal

class ITrader(Protocol):
    """战术交易器接口"""

    async def generate_trading_signal(
        self,
        symbol: str,
        strategy_config: StrategyConfig
    ) -> TradingSignal:
        """
        生成交易信号

        Args:
            symbol: 交易对
            strategy_config: 当前策略配置

        Returns:
            交易信号

        Raises:
            SignalGenerationError: 信号生成失败
        """
        ...

    async def calculate_position_size(
        self,
        signal: TradingSignal,
        portfolio: Portfolio,
        risk_params: Dict[str, Decimal]
    ) -> Decimal:
        """
        计算仓位大小

        Args:
            signal: 交易信号
            portfolio: 当前组合
            risk_params: 风险参数

        Returns:
            建议仓位大小
        """
        ...
```

**实现文件**: `src/decision/trader.py`

**实现类**: `LLMTrader`

## 5. 执行模块接口

### 5.1 订单执行接口

```python
from typing import Protocol
from src.models.trade import Order, OrderSide, OrderType

class IOrderExecutor(Protocol):
    """订单执行接口"""

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        **kwargs
    ) -> Order:
        """
        创建订单

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 数量
            price: 价格（市价单可为None）
            **kwargs: 其他参数（止损止盈等）

        Returns:
            订单对象

        Raises:
            OrderExecutionError: 订单创建失败
        """
        ...

    async def cancel_order(
        self,
        order_id: str,
        symbol: str
    ) -> bool:
        """
        取消订单

        Args:
            order_id: 订单ID
            symbol: 交易对

        Returns:
            是否成功

        Raises:
            OrderExecutionError: 取消失败
        """
        ...

    async def get_order(
        self,
        order_id: str,
        symbol: str
    ) -> Order:
        """
        查询订单状态

        Args:
            order_id: 订单ID
            symbol: 交易对

        Returns:
            订单对象

        Raises:
            OrderQueryError: 查询失败
        """
        ...

    async def get_open_orders(
        self,
        symbol: str | None = None
    ) -> List[Order]:
        """
        获取所有未完成订单

        Args:
            symbol: 交易对（可选，None表示所有）

        Returns:
            订单列表
        """
        ...
```

**实现文件**: `src/execution/order.py`

**实现类**: `CCXTOrderExecutor`

### 5.2 风险管理接口

```python
from typing import Protocol

class RiskCheckResult(BaseModel):
    """风险检查结果"""
    passed: bool
    reason: str | None = None
    suggested_adjustment: Dict[str, Any] | None = None

class IRiskManager(Protocol):
    """风险管理接口"""

    async def check_order_risk(
        self,
        signal: TradingSignal,
        portfolio: Portfolio,
        risk_params: Dict[str, Decimal]
    ) -> RiskCheckResult:
        """
        检查订单风险

        Args:
            signal: 交易信号
            portfolio: 当前组合
            risk_params: 风险参数

        Returns:
            风险检查结果
        """
        ...

    async def check_position_risk(
        self,
        position: Position,
        current_price: Decimal
    ) -> RiskCheckResult:
        """
        检查持仓风险

        Args:
            position: 持仓
            current_price: 当前价格

        Returns:
            风险检查结果（如需要止损）
        """
        ...

    async def check_portfolio_risk(
        self,
        portfolio: Portfolio
    ) -> RiskCheckResult:
        """
        检查组合风险

        Args:
            portfolio: 投资组合

        Returns:
            风险检查结果（如触发熔断）
        """
        ...

    async def calculate_stop_loss_take_profit(
        self,
        entry_price: Decimal,
        side: OrderSide,
        risk_params: Dict[str, Decimal]
    ) -> Dict[str, Decimal]:
        """
        计算止损止盈价格

        Returns:
            {"stop_loss": Decimal, "take_profit": Decimal}
        """
        ...
```

**实现文件**: `src/execution/risk.py`

**实现类**: `StandardRiskManager`

### 5.3 投资组合管理接口

```python
from typing import Protocol

class IPortfolioManager(Protocol):
    """投资组合管理接口"""

    async def get_current_portfolio(self) -> Portfolio:
        """
        获取当前投资组合

        Returns:
            投资组合对象
        """
        ...

    async def update_portfolio(self) -> Portfolio:
        """
        更新投资组合（从交易所同步）

        Returns:
            更新后的投资组合
        """
        ...

    async def get_position(self, symbol: str) -> Position | None:
        """获取指定持仓"""
        ...

    async def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        ...

    async def calculate_metrics(self) -> PerformanceMetrics:
        """
        计算绩效指标

        Returns:
            绩效指标
        """
        ...
```

**实现文件**: `src/execution/portfolio.py`

**实现类**: `PortfolioManager`

## 6. 学习模块接口

### 6.1 绩效评估接口

```python
from typing import Protocol
from datetime import datetime

class IPerformanceEvaluator(Protocol):
    """绩效评估接口"""

    async def evaluate_trade(
        self,
        trade: Trade,
        entry_decision: DecisionRecord,
        exit_decision: DecisionRecord
    ) -> Dict[str, Any]:
        """
        评估单笔交易

        Returns:
            {
                "pnl": Decimal,
                "pnl_percentage": Decimal,
                "holding_period": timedelta,
                "outcome": "success/failure",
                "analysis": str
            }
        """
        ...

    async def evaluate_period(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> PerformanceMetrics:
        """
        评估时间段绩效

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            绩效指标
        """
        ...

    async def compare_with_benchmark(
        self,
        benchmark_symbol: str = "BTC/USDT"
    ) -> Dict[str, Any]:
        """
        与基准比较

        Returns:
            {
                "alpha": Decimal,
                "beta": Decimal,
                "excess_return": Decimal
            }
        """
        ...
```

**实现文件**: `src/learning/performance.py`

**实现类**: `PerformanceEvaluator`

### 6.2 反思接口

```python
from typing import Protocol

class IReflectionEngine(Protocol):
    """反思引擎接口"""

    async def reflect_on_trade(
        self,
        experience: TradingExperience
    ) -> str:
        """
        对单笔交易进行反思

        Args:
            experience: 交易经验

        Returns:
            反思内容
        """
        ...

    async def reflect_on_period(
        self,
        performance: PerformanceMetrics
    ) -> Dict[str, Any]:
        """
        对阶段性表现进行反思

        Returns:
            {
                "summary": str,
                "strengths": List[str],
                "weaknesses": List[str],
                "improvements": List[str]
            }
        """
        ...

    async def identify_patterns(
        self,
        experiences: List[TradingExperience]
    ) -> List[Dict[str, Any]]:
        """
        识别交易模式

        Returns:
            [
                {
                    "pattern": str,
                    "frequency": int,
                    "success_rate": float,
                    "description": str
                },
                ...
            ]
        """
        ...
```

**实现文件**: `src/learning/reflection.py`

**实现类**: `LLMReflectionEngine`

## 7. 工具函数接口

### 7.1 决策工具接口

```python
from typing import Protocol, Callable, Dict, Any

class ITool(Protocol):
    """工具接口"""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema

    async def execute(self, **kwargs) -> Any:
        """
        执行工具

        Args:
            **kwargs: 工具参数

        Returns:
            执行结果
        """
        ...

    def to_openai_function(self) -> Dict[str, Any]:
        """
        转换为OpenAI function calling格式

        Returns:
            {
                "name": str,
                "description": str,
                "parameters": {...}
            }
        """
        ...
```

**实现文件**: `src/decision/tools.py`

**实现类**: 各种具体工具，如：
- `MarketDataQueryTool`
- `TechnicalAnalysisTool`
- `BacktestTool`
- `RiskCalculatorTool`
- `MemorySearchTool`

## 8. 使用示例

### 8.1 模块组合使用

```python
# 在决策引擎中组合使用各模块接口

class TradingDecisionEngine:
    def __init__(
        self,
        market_collector: IMarketDataCollector,
        memory_retrieval: IMemoryRetrieval,
        strategist: IStrategist,
        trader: ITrader,
        risk_manager: IRiskManager
    ):
        self.market = market_collector
        self.memory = memory_retrieval
        self.strategist = strategist
        self.trader = trader
        self.risk = risk_manager

    async def make_decision(self, symbol: str) -> TradingSignal | None:
        # 1. 获取市场数据
        ticker = await self.market.get_ticker(symbol)

        # 2. 检索相关记忆
        context = await self.memory.retrieve_relevant_context(
            f"Trading {symbol} at price {ticker.last}"
        )

        # 3. 战略分析
        regime = await self.strategist.analyze_market_regime(symbol)

        # 4. 生成信号
        signal = await self.trader.generate_trading_signal(
            symbol,
            context["current_context"].strategy
        )

        # 5. 风险检查
        risk_check = await self.risk.check_order_risk(
            signal,
            context["current_context"].portfolio,
            context["current_context"].risk_params
        )

        if risk_check.passed:
            return signal
        else:
            logger.warning(f"Risk check failed: {risk_check.reason}")
            return None
```

### 8.2 依赖注入示例

```python
# main.py 或 dependency injection容器

from src.perception.market_data import CCXTMarketDataCollector
from src.memory.retrieval import RAGMemoryRetrieval
from src.decision.strategist import LLMStrategist
from src.decision.trader import LLMTrader
from src.execution.risk import StandardRiskManager

# 创建实例
market_collector = CCXTMarketDataCollector(exchange_config)
memory_retrieval = RAGMemoryRetrieval(short_term, long_term, llm_client)
strategist = LLMStrategist(llm_client, memory_retrieval)
trader = LLMTrader(llm_client, memory_retrieval)
risk_manager = StandardRiskManager()

# 注入依赖
decision_engine = TradingDecisionEngine(
    market_collector=market_collector,
    memory_retrieval=memory_retrieval,
    strategist=strategist,
    trader=trader,
    risk_manager=risk_manager
)
```

## 9. 测试Mock示例

```python
# tests/mocks/market_data.py

class MockMarketDataCollector:
    """市场数据采集器Mock"""

    def __init__(self):
        self.ticker_data = {}

    async def get_ticker(self, symbol: str) -> Ticker:
        if symbol in self.ticker_data:
            return self.ticker_data[symbol]
        return Ticker(
            symbol=symbol,
            timestamp=int(datetime.utcnow().timestamp() * 1000),
            datetime=datetime.utcnow(),
            last=Decimal("45000"),
            bid=Decimal("44999"),
            ask=Decimal("45001"),
            # ...
        )

    def set_ticker(self, symbol: str, ticker: Ticker):
        """测试时设置ticker数据"""
        self.ticker_data[symbol] = ticker
```

## 10. 开发检查清单

实现一个新模块时，请确保：

- [ ] 定义了清晰的接口（Protocol或ABC）
- [ ] 接口方法有完整的docstring
- [ ] 所有参数和返回值都有类型注解
- [ ] 定义了可能抛出的异常
- [ ] 提供了接口使用示例
- [ ] 创建了对应的Mock类用于测试
- [ ] 更新了本文档

## 11. 接口版本管理

如需修改接口：

1. **向后兼容**: 尽量添加可选参数而非修改现有参数
2. **废弃警告**: 使用 `@deprecated` 装饰器标记废弃方法
3. **版本号**: 接口有重大变更时更新版本号
4. **迁移指南**: 提供从旧接口到新接口的迁移文档

```python
from typing import deprecated

class IMarketDataCollector(Protocol):
    @deprecated("Use get_ohlcv() instead")
    async def get_candles(self, symbol: str) -> List:
        ...

    async def get_ohlcv(self, symbol: str) -> List[OHLCVData]:
        ...
```
