# 数据模型定义

本文档定义系统中所有核心数据模型，使用Pydantic进行数据验证。

## 1. 基础数据类型

### 1.1 时间戳类型
```python
from datetime import datetime
from typing import NewType

# 使用毫秒时间戳
Timestamp = NewType('Timestamp', int)

# 使用datetime对象
DateTimeUTC = NewType('DateTimeUTC', datetime)
```

### 1.2 价格和数量类型
```python
from decimal import Decimal
from typing import NewType

# 使用Decimal避免浮点数精度问题
Price = NewType('Price', Decimal)
Amount = NewType('Amount', Decimal)
Volume = NewType('Volume', Decimal)
```

## 2. 市场数据模型

### 2.1 K线数据 (OHLCV)
```python
from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal

class OHLCVData(BaseModel):
    """K线数据模型"""

    symbol: str = Field(..., description="交易对，如BTC/USDT")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    datetime: datetime = Field(..., description="时间")
    open: Decimal = Field(..., description="开盘价")
    high: Decimal = Field(..., description="最高价")
    low: Decimal = Field(..., description="最低价")
    close: Decimal = Field(..., description="收盘价")
    volume: Decimal = Field(..., description="成交量")

    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }

# 使用示例
ohlcv = OHLCVData(
    symbol="BTC/USDT",
    timestamp=1704067200000,
    datetime=datetime.utcnow(),
    open=Decimal("45000.50"),
    high=Decimal("45500.00"),
    low=Decimal("44800.00"),
    close=Decimal("45200.00"),
    volume=Decimal("123.456")
)
```

### 2.2 订单簿数据
```python
from typing import List, Tuple

class OrderBookLevel(BaseModel):
    """订单簿单层数据"""
    price: Decimal
    amount: Decimal

class OrderBook(BaseModel):
    """完整订单簿"""

    symbol: str
    timestamp: int
    datetime: datetime
    bids: List[OrderBookLevel] = Field(..., description="买单列表，按价格降序")
    asks: List[OrderBookLevel] = Field(..., description="卖单列表，按价格升序")

    def get_spread(self) -> Decimal:
        """获取买卖价差"""
        if not self.bids or not self.asks:
            return Decimal("0")
        return self.asks[0].price - self.bids[0].price

    def get_mid_price(self) -> Decimal:
        """获取中间价"""
        if not self.bids or not self.asks:
            return Decimal("0")
        return (self.asks[0].price + self.bids[0].price) / Decimal("2")
```

### 2.3 Ticker数据
```python
class Ticker(BaseModel):
    """Ticker数据"""

    symbol: str
    timestamp: int
    datetime: datetime
    last: Decimal = Field(..., description="最新成交价")
    bid: Decimal = Field(..., description="最佳买价")
    ask: Decimal = Field(..., description="最佳卖价")
    high: Decimal = Field(..., description="24h最高价")
    low: Decimal = Field(..., description="24h最低价")
    volume: Decimal = Field(..., description="24h成交量")
    quote_volume: Decimal = Field(..., description="24h成交额")
    change_24h: Decimal = Field(..., description="24h涨跌幅(%)")
```

## 3. 交易模型

### 3.1 订单模型
```python
from enum import Enum

class OrderSide(str, Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LOSS_LIMIT = "stop_loss_limit"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"

class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"

class Order(BaseModel):
    """订单模型"""

    id: str = Field(..., description="订单ID")
    client_order_id: str = Field(..., description="客户端订单ID")
    timestamp: int
    datetime: datetime
    symbol: str
    side: OrderSide
    type: OrderType
    status: OrderStatus
    price: Decimal | None = Field(None, description="价格(市价单为None)")
    amount: Decimal = Field(..., description="数量")
    filled: Decimal = Field(Decimal("0"), description="已成交数量")
    remaining: Decimal = Field(..., description="剩余数量")
    cost: Decimal = Field(Decimal("0"), description="成交金额")
    average: Decimal | None = Field(None, description="平均成交价")
    fee: Decimal | None = Field(None, description="手续费")

    # 止损止盈
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    stop_loss_price: Decimal | None = None

    # 额外信息
    exchange: str = Field(..., description="交易所")
    info: dict = Field(default_factory=dict, description="原始数据")
```

### 3.2 成交记录
```python
class Trade(BaseModel):
    """成交记录"""

    id: str
    order_id: str
    timestamp: int
    datetime: datetime
    symbol: str
    side: OrderSide
    price: Decimal
    amount: Decimal
    cost: Decimal
    fee: Decimal | None = None
    fee_currency: str | None = None
```

### 3.3 持仓模型
```python
class Position(BaseModel):
    """持仓信息"""

    symbol: str
    side: OrderSide
    amount: Decimal = Field(..., description="持仓数量")
    entry_price: Decimal = Field(..., description="平均成本价")
    current_price: Decimal = Field(..., description="当前价格")
    unrealized_pnl: Decimal = Field(..., description="未实现盈亏")
    unrealized_pnl_percentage: Decimal = Field(..., description="未实现盈亏比例(%)")
    value: Decimal = Field(..., description="持仓价值")

    # 风险指标
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    def update_current_price(self, price: Decimal):
        """更新当前价格并重新计算盈亏"""
        self.current_price = price
        self.value = self.amount * price

        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (price - self.entry_price) * self.amount
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.amount

        self.unrealized_pnl_percentage = (
            self.unrealized_pnl / (self.entry_price * self.amount) * Decimal("100")
        )
```

## 4. 投资组合模型

### 4.1 账户余额
```python
class Balance(BaseModel):
    """账户余额"""

    currency: str
    free: Decimal = Field(..., description="可用余额")
    used: Decimal = Field(..., description="冻结余额")
    total: Decimal = Field(..., description="总余额")

class AccountBalance(BaseModel):
    """完整账户余额"""

    exchange: str
    timestamp: int
    datetime: datetime
    balances: dict[str, Balance]
    total_value_usd: Decimal = Field(..., description="总价值(USD)")
```

### 4.2 投资组合
```python
class Portfolio(BaseModel):
    """投资组合"""

    timestamp: int
    datetime: datetime
    total_value: Decimal = Field(..., description="总价值(USD)")
    cash: Decimal = Field(..., description="现金(USDT)")
    positions: list[Position] = Field(default_factory=list)

    # 绩效指标
    total_pnl: Decimal = Field(Decimal("0"), description="总盈亏")
    daily_pnl: Decimal = Field(Decimal("0"), description="当日盈亏")
    total_return: Decimal = Field(Decimal("0"), description="总收益率(%)")

    def get_position(self, symbol: str) -> Position | None:
        """获取指定持仓"""
        for pos in self.positions:
            if pos.symbol == symbol:
                return pos
        return None

    def get_allocation(self, symbol: str) -> Decimal:
        """获取仓位占比"""
        pos = self.get_position(symbol)
        if not pos or self.total_value == 0:
            return Decimal("0")
        return (pos.value / self.total_value) * Decimal("100")
```

## 5. 记忆模型

### 5.1 短期记忆（上下文）
```python
class MarketContext(BaseModel):
    """市场上下文（短期记忆）"""

    timestamp: int
    datetime: datetime

    # 市场状态
    market_regime: str = Field(..., description="市场状态: bull/bear/sideways")
    volatility: Decimal = Field(..., description="波动率")
    trend: str = Field(..., description="趋势: up/down/neutral")

    # 近期价格
    recent_prices: list[Decimal] = Field(default_factory=list)

    # 技术指标
    indicators: dict = Field(default_factory=dict)

    # 近期交易
    recent_trades: list[str] = Field(default_factory=list, description="近期交易ID列表")

class TradingContext(BaseModel):
    """交易上下文"""

    timestamp: int
    datetime: datetime

    # 当前策略
    current_strategy: str
    strategy_params: dict = Field(default_factory=dict)

    # 风险参数
    max_position_size: Decimal
    max_daily_loss: Decimal
    current_daily_loss: Decimal = Field(Decimal("0"))

    # 市场上下文
    market_context: MarketContext

    # 投资组合
    portfolio: Portfolio
```

### 5.2 长期记忆（经验）
```python
class TradingExperience(BaseModel):
    """交易经验（长期记忆）"""

    id: str = Field(..., description="经验ID")
    timestamp: int
    datetime: datetime

    # 情景描述
    situation: str = Field(..., description="市场情况描述")
    situation_embedding: list[float] | None = Field(None, description="向量表示")

    # 决策
    decision: str = Field(..., description="做出的决策")
    decision_reasoning: str = Field(..., description="决策理由")

    # 结果
    outcome: str = Field(..., description="结果: success/failure")
    pnl: Decimal = Field(..., description="盈亏")
    pnl_percentage: Decimal = Field(..., description="盈亏比例(%)")

    # 反思
    reflection: str | None = Field(None, description="事后反思")
    lessons_learned: list[str] = Field(default_factory=list)

    # 元数据
    tags: list[str] = Field(default_factory=list)
    importance_score: float = Field(0.0, description="重要性评分 0-1")

class MemoryQuery(BaseModel):
    """记忆查询请求"""

    query_text: str = Field(..., description="查询文本")
    query_embedding: list[float] | None = None
    top_k: int = Field(5, description="返回前K个结果")
    filters: dict = Field(default_factory=dict, description="过滤条件")
    min_importance: float = Field(0.0, description="最小重要性分数")
```

## 6. 决策模型

### 6.1 交易信号
```python
class SignalType(str, Enum):
    """信号类型"""
    ENTER_LONG = "enter_long"
    EXIT_LONG = "exit_long"
    ENTER_SHORT = "enter_short"
    EXIT_SHORT = "exit_short"
    HOLD = "hold"

class TradingSignal(BaseModel):
    """交易信号"""

    timestamp: int
    datetime: datetime
    symbol: str
    signal_type: SignalType
    confidence: float = Field(..., ge=0.0, le=1.0, description="信心分数 0-1")

    # 建议参数
    suggested_price: Decimal | None = None
    suggested_amount: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    # 理由
    reasoning: str = Field(..., description="信号产生理由")
    supporting_factors: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)

    # 来源
    source: str = Field(..., description="信号来源: strategist/trader")
```

### 6.2 决策记录
```python
class DecisionRecord(BaseModel):
    """决策记录"""

    id: str
    timestamp: int
    datetime: datetime

    # 输入
    input_context: dict = Field(..., description="输入上下文")

    # 决策过程
    thought_process: str = Field(..., description="思考过程")
    tools_used: list[str] = Field(default_factory=list, description="使用的工具")

    # 输出
    decision: str = Field(..., description="最终决策")
    action_taken: str | None = Field(None, description="采取的行动")

    # 元信息
    decision_layer: str = Field(..., description="决策层级: strategic/tactical")
    model_used: str = Field(..., description="使用的模型")
    tokens_used: int | None = None
    latency_ms: int | None = None
```

### 6.3 策略参数
```python
class StrategyConfig(BaseModel):
    """策略配置"""

    name: str
    version: str
    description: str

    # 交易参数
    max_position_size: Decimal = Field(..., description="最大仓位(占总资产比例)")
    max_single_trade: Decimal = Field(..., description="单笔最大交易额")
    max_open_positions: int = Field(..., description="最大持仓数量")

    # 风险参数
    max_daily_loss: Decimal = Field(..., description="最大日亏损(占总资产比例)")
    max_drawdown: Decimal = Field(..., description="最大回撤")
    stop_loss_percentage: Decimal = Field(..., description="止损比例")
    take_profit_percentage: Decimal = Field(..., description="止盈比例")

    # 市场参数
    trading_pairs: list[str] = Field(..., description="交易对列表")
    timeframes: list[str] = Field(..., description="时间周期")

    # 更新时间
    updated_at: datetime
    reason_for_update: str | None = None
```

## 7. 性能评估模型

### 7.1 交易绩效
```python
class PerformanceMetrics(BaseModel):
    """绩效指标"""

    start_date: datetime
    end_date: datetime

    # 收益指标
    total_return: Decimal = Field(..., description="总收益率(%)")
    annualized_return: Decimal = Field(..., description="年化收益率(%)")
    daily_returns: list[Decimal] = Field(default_factory=list)

    # 风险指标
    volatility: Decimal = Field(..., description="波动率")
    max_drawdown: Decimal = Field(..., description="最大回撤(%)")
    sharpe_ratio: Decimal = Field(..., description="夏普比率")
    sortino_ratio: Decimal = Field(..., description="索提诺比率")
    calmar_ratio: Decimal = Field(..., description="卡尔玛比率")

    # 交易统计
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal = Field(..., description="胜率(%)")
    avg_win: Decimal = Field(..., description="平均盈利")
    avg_loss: Decimal = Field(..., description="平均亏损")
    profit_factor: Decimal = Field(..., description="盈亏比")

    # 其他
    max_consecutive_wins: int
    max_consecutive_losses: int

class DailySnapshot(BaseModel):
    """每日快照"""

    date: datetime
    total_value: Decimal
    cash: Decimal
    positions_value: Decimal
    daily_pnl: Decimal
    daily_return: Decimal
    drawdown: Decimal
```

## 8. 系统事件模型

### 8.1 事件类型
```python
class EventType(str, Enum):
    """事件类型"""
    MARKET_DATA = "market_data"
    ORDER_CREATED = "order_created"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELED = "order_canceled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    RISK_ALERT = "risk_alert"
    SYSTEM_ERROR = "system_error"
    DECISION_MADE = "decision_made"
    REFLECTION_COMPLETED = "reflection_completed"

class SystemEvent(BaseModel):
    """系统事件"""

    id: str
    timestamp: int
    datetime: datetime
    event_type: EventType
    severity: str = Field(..., description="严重程度: info/warning/error/critical")

    # 事件数据
    data: dict = Field(default_factory=dict)

    # 关联信息
    related_order_id: str | None = None
    related_symbol: str | None = None

    # 消息
    message: str
    details: str | None = None
```

## 9. 配置模型

### 9.1 系统配置
```python
class ExchangeConfig(BaseModel):
    """交易所配置"""

    name: str
    api_key: str
    api_secret: str
    password: str | None = None
    testnet: bool = Field(False, description="是否使用测试网")
    rate_limit: int = Field(1000, description="API请求限制(次/分)")

    class Config:
        # API密钥不应该被序列化到日志
        fields = {
            'api_key': {'exclude': True},
            'api_secret': {'exclude': True},
            'password': {'exclude': True}
        }

class AIModelConfig(BaseModel):
    """AI模型配置"""

    provider: str = Field(..., description="提供商: deepseek/openai")
    model_name: str
    api_key: str
    base_url: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(4000)
    timeout: int = Field(30, description="超时时间(秒)")

    class Config:
        fields = {'api_key': {'exclude': True}}

class SystemConfig(BaseModel):
    """系统配置"""

    # 环境
    environment: str = Field(..., description="环境: dev/test/prod")

    # 交易所
    exchanges: list[ExchangeConfig]

    # AI模型
    ai_models: dict[str, AIModelConfig] = Field(
        ...,
        description="AI模型配置，key为用途: strategist/trader/embedding"
    )

    # 数据库
    database_url: str
    redis_url: str
    qdrant_url: str

    # 系统参数
    loop_interval: int = Field(60, description="主循环间隔(秒)")
    enable_trading: bool = Field(False, description="是否启用实盘交易")

    # 日志
    log_level: str = Field("INFO")
    log_file: str | None = None
```

## 10. 数据验证示例

```python
from pydantic import ValidationError

# 正确的数据
try:
    order = Order(
        id="order_123",
        client_order_id="client_123",
        timestamp=1704067200000,
        datetime=datetime.utcnow(),
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=OrderStatus.OPEN,
        price=Decimal("45000.00"),
        amount=Decimal("0.1"),
        filled=Decimal("0"),
        remaining=Decimal("0.1"),
        exchange="binance"
    )
    print("订单创建成功")
except ValidationError as e:
    print(f"验证失败: {e}")

# 错误的数据（价格不能为负数，需要添加validator）
# 这些验证规则将在实际实现中添加
```

## 11. 使用建议

### 11.1 对于开发者
1. **导入模型**: 从 `src/models/` 导入需要的模型
2. **类型检查**: 使用mypy进行类型检查
3. **数据验证**: 所有外部数据必须通过Pydantic验证
4. **序列化**: 使用 `.dict()` 或 `.json()` 进行序列化

### 11.2 常见操作
```python
# 1. 创建模型实例
ticker = Ticker(
    symbol="BTC/USDT",
    timestamp=int(datetime.utcnow().timestamp() * 1000),
    datetime=datetime.utcnow(),
    last=Decimal("45000"),
    # ... 其他字段
)

# 2. 序列化为dict
ticker_dict = ticker.dict()

# 3. 序列化为JSON
ticker_json = ticker.json()

# 4. 从dict创建
ticker2 = Ticker(**ticker_dict)

# 5. 从JSON创建
ticker3 = Ticker.parse_raw(ticker_json)

# 6. 部分更新
ticker_updated = ticker.copy(update={"last": Decimal("45100")})
```

## 12. 扩展指南

添加新模型时：
1. 定义在对应的 `src/models/` 文件中
2. 使用Pydantic BaseModel
3. 添加完整的类型注解
4. 添加Field描述
5. 添加使用示例
6. 更新本文档
