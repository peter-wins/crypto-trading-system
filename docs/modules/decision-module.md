# 决策模块开发指南

本文档提供决策模块的详细开发指南，包括完整的代码示例和实现细节。

## 1. 模块概述

决策模块是系统的大脑，负责：
- 调用LLM进行推理
- 战略层决策（市场分析、策略制定）
- 战术层决策（交易信号生成）
- 工具调用框架

## 2. LLM客户端实现

### 2.1 基础接口

参考文档: `docs/prd/02-API-CONTRACTS.md` 第4.1章

### 2.2 完整实现示例

```python
# src/decision/llm_client.py

import asyncio
import hashlib
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import httpx
from openai import AsyncOpenAI

from src.core.logger import get_logger
from src.core.exceptions import LLMError, RateLimitError

logger = get_logger(__name__)


class Message(BaseModel):
    """消息模型"""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None  # function name for tool messages


class ToolCall(BaseModel):
    """工具调用"""
    id: str
    name: str
    arguments: Dict[str, Any]


class LLMResponse(BaseModel):
    """LLM响应"""
    content: Optional[str]
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str
    tokens_used: int
    model: str


class DeepSeekClient:
    """DeepSeek客户端"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        timeout: int = 60
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout
        )
        self.model = model
        self.total_tokens = 0

    async def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> LLMResponse:
        """
        调用DeepSeek Chat API

        Args:
            messages: 消息历史
            tools: 可用工具列表（OpenAI function calling格式）
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            LLM响应

        Raises:
            LLMError: 调用失败
            RateLimitError: 限流
        """
        try:
            # 转换消息格式
            formatted_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]

            # 构建请求参数
            params = {
                "model": self.model,
                "messages": formatted_messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            if tools:
                params["tools"] = tools
                params["tool_choice"] = "auto"

            # 调用API
            logger.info(f"Calling DeepSeek API with {len(messages)} messages")
            response = await self.client.chat.completions.create(**params)

            # 解析响应
            choice = response.choices[0]
            tokens_used = response.usage.total_tokens
            self.total_tokens += tokens_used

            logger.info(
                f"DeepSeek response received. "
                f"Tokens: {tokens_used}, "
                f"Finish reason: {choice.finish_reason}"
            )

            # 处理工具调用
            tool_calls = None
            if choice.message.tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=eval(tc.function.arguments)  # JSON string to dict
                    )
                    for tc in choice.message.tool_calls
                ]

            return LLMResponse(
                content=choice.message.content,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason,
                tokens_used=tokens_used,
                model=self.model
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(f"Rate limit exceeded: {e}")
            raise LLMError(f"HTTP error: {e}")

        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            raise LLMError(f"Failed to call LLM: {e}")

    async def embed(self, text: str) -> List[float]:
        """
        生成文本向量（使用OpenAI embedding）

        Args:
            text: 输入文本

        Returns:
            向量表示

        Raises:
            EmbeddingError: 向量化失败
        """
        try:
            # DeepSeek可能没有embedding API，使用OpenAI
            # 或者使用本地模型
            response = await self.client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Embedding failed: {e}", exc_info=True)
            raise LLMError(f"Failed to generate embedding: {e}")

    def get_total_tokens(self) -> int:
        """获取总token使用量"""
        return self.total_tokens


class OpenAIClient:
    """OpenAI客户端（用于embedding或backup）"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        embedding_model: str = "text-embedding-ada-002",
        timeout: int = 60
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout
        )
        self.model = model
        self.embedding_model = embedding_model

    async def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> LLMResponse:
        """类似DeepSeekClient.chat实现"""
        # 实现与DeepSeekClient类似
        pass

    async def embed(self, text: str) -> List[float]:
        """
        生成文本向量

        Args:
            text: 输入文本

        Returns:
            向量表示（1536维）
        """
        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Embedding failed: {e}", exc_info=True)
            raise LLMError(f"Failed to generate embedding: {e}")
```

## 3. Prompt设计

### 3.1 Prompt模板

```python
# src/decision/prompts.py

from typing import Dict, Any
from datetime import datetime


class PromptTemplates:
    """Prompt模板集合"""

    @staticmethod
    def strategist_system_prompt() -> str:
        """战略决策者系统提示"""
        return """你是一位资深的加密货币投资组合经理和市场分析师。

你的职责：
1. 分析宏观市场环境和趋势
2. 识别当前市场regime（牛市/熊市/震荡）
3. 制定投资组合策略和资产配置
4. 设定风险管理参数
5. 定期反思和优化决策流程

你的决策风格：
- 基于数据和逻辑，而非情绪
- 重视风险管理，控制回撤
- 长期视角，不追求短期暴利
- 持续学习，从失败中改进

你可以使用以下工具：
- market_data_query: 查询市场数据
- technical_analysis: 进行技术分析
- memory_search: 搜索历史经验
- risk_calculator: 计算风险指标

决策时请：
1. 先使用工具收集信息
2. 进行深入分析和推理
3. 明确说明决策理由
4. 考虑潜在风险
5. 给出具体的策略参数
"""

    @staticmethod
    def trader_system_prompt() -> str:
        """战术交易者系统提示"""
        return """你是一位专业的加密货币交易员。

你的职责：
1. 根据战略指引识别具体交易机会
2. 生成精确的交易信号（进场/出场）
3. 计算合理的仓位大小
4. 设置止损止盈价格

你的交易原则：
- 严格遵守战略层的风险参数
- 等待高概率的交易机会
- 明确的进出场计划
- 每笔交易都有风险回报比

你可以使用以下工具：
- market_data_query: 查询实时市场数据
- technical_analysis: 技术指标分析
- memory_search: 查找相似历史情况
- risk_calculator: 计算仓位和风险

生成交易信号时请：
1. 分析当前市场状态
2. 检查技术指标
3. 参考历史经验
4. 计算风险回报比
5. 明确说明交易理由
"""

    @staticmethod
    def reflection_prompt() -> str:
        """反思提示"""
        return """请对以下交易进行深入反思：

交易信息：
{trade_info}

决策过程：
{decision_process}

结果：
{outcome}

请回答：
1. 这个决策的优点是什么？
2. 有哪些可以改进的地方？
3. 从中学到了什么经验教训？
4. 下次遇到类似情况应该怎么做？

请客观、深入地分析，不要回避失败，也不要过度自信。
"""

    @staticmethod
    def build_strategist_prompt(context: Dict[str, Any]) -> str:
        """构建战略决策提示"""
        return f"""当前时间：{datetime.utcnow().isoformat()}

=== 投资组合状态 ===
总价值: ${context['portfolio']['total_value']:,.2f}
现金: ${context['portfolio']['cash']:,.2f}
持仓: {len(context['portfolio']['positions'])}个
总盈亏: {context['portfolio']['total_return']:.2f}%

=== 最近绩效 ===
7日收益: {context['performance']['7d_return']:.2f}%
30日收益: {context['performance']['30d_return']:.2f}%
夏普比率: {context['performance']['sharpe_ratio']:.2f}
最大回撤: {context['performance']['max_drawdown']:.2f}%

=== 相关历史经验 ===
{context.get('similar_experiences', '暂无相关经验')}

=== 任务 ===
请分析当前市场环境，并制定下一阶段的投资策略。

具体要求：
1. 判断市场regime（牛市/熊市/震荡）
2. 建议资产配置（现金比例、持仓比例）
3. 设定风险参数（最大仓位、止损比例等）
4. 说明决策理由

请使用工具收集必要信息后再做决策。
"""

    @staticmethod
    def build_trader_prompt(
        symbol: str,
        context: Dict[str, Any]
    ) -> str:
        """构建战术交易提示"""
        return f"""当前时间：{datetime.utcnow().isoformat()}

=== 交易对 ===
{symbol}

=== 当前策略 ===
{context['strategy']}

=== 风险参数 ===
最大仓位: {context['risk_params']['max_position_size']:.1f}%
止损比例: {context['risk_params']['stop_loss_percentage']:.1f}%
止盈比例: {context['risk_params']['take_profit_percentage']:.1f}%

=== 当前持仓 ===
{context.get('current_position', '无持仓')}

=== 相似历史案例 ===
{context.get('similar_cases', '暂无相关案例')}

=== 任务 ===
请分析{symbol}的交易机会，并生成交易信号。

要求：
1. 使用工具查询最新市场数据和技术指标
2. 分析当前是否有交易机会
3. 如果有机会，生成详细的交易信号（方向、价格、仓位）
4. 设置止损止盈
5. 说明交易理由和风险

如果当前没有明确机会，请说明原因并建议持币观望。
"""
```

### 3.2 工具定义

```python
# src/decision/tools.py

from typing import Dict, Any, List, Protocol
from abc import ABC, abstractmethod
from decimal import Decimal
import json

from src.perception.market_data import IMarketDataCollector
from src.perception.indicators import IIndicatorCalculator
from src.memory.retrieval import IMemoryRetrieval
from src.core.logger import get_logger

logger = get_logger(__name__)


class ITool(Protocol):
    """工具接口"""
    name: str
    description: str

    async def execute(self, **kwargs) -> Any:
        """执行工具"""
        ...

    def to_function_schema(self) -> Dict[str, Any]:
        """转换为OpenAI function格式"""
        ...


class MarketDataQueryTool:
    """市场数据查询工具"""

    name = "market_data_query"
    description = "查询加密货币的实时市场数据，包括价格、成交量、24h涨跌幅等"

    def __init__(self, market_collector: IMarketDataCollector):
        self.market = market_collector

    async def execute(
        self,
        symbol: str,
        data_type: str = "ticker"
    ) -> Dict[str, Any]:
        """
        执行查询

        Args:
            symbol: 交易对，如"BTC/USDT"
            data_type: 数据类型，"ticker"或"ohlcv"

        Returns:
            市场数据
        """
        try:
            if data_type == "ticker":
                ticker = await self.market.get_ticker(symbol)
                return {
                    "symbol": ticker.symbol,
                    "price": float(ticker.last),
                    "bid": float(ticker.bid),
                    "ask": float(ticker.ask),
                    "24h_high": float(ticker.high),
                    "24h_low": float(ticker.low),
                    "24h_volume": float(ticker.volume),
                    "24h_change": float(ticker.change_24h)
                }

            elif data_type == "ohlcv":
                ohlcv_list = await self.market.get_ohlcv(
                    symbol,
                    timeframe="1h",
                    limit=24
                )
                return {
                    "symbol": symbol,
                    "timeframe": "1h",
                    "data": [
                        {
                            "timestamp": candle.timestamp,
                            "open": float(candle.open),
                            "high": float(candle.high),
                            "low": float(candle.low),
                            "close": float(candle.close),
                            "volume": float(candle.volume)
                        }
                        for candle in ohlcv_list
                    ]
                }

        except Exception as e:
            logger.error(f"Market data query failed: {e}")
            return {"error": str(e)}

    def to_function_schema(self) -> Dict[str, Any]:
        """OpenAI function格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "交易对，如BTC/USDT"
                        },
                        "data_type": {
                            "type": "string",
                            "enum": ["ticker", "ohlcv"],
                            "description": "数据类型：ticker(实时报价)或ohlcv(K线数据)",
                            "default": "ticker"
                        }
                    },
                    "required": ["symbol"]
                }
            }
        }


class TechnicalAnalysisTool:
    """技术分析工具"""

    name = "technical_analysis"
    description = "计算技术指标，如RSI、MACD、MA等，帮助分析市场趋势"

    def __init__(
        self,
        market_collector: IMarketDataCollector,
        indicator_calculator: IIndicatorCalculator
    ):
        self.market = market_collector
        self.indicators = indicator_calculator

    async def execute(
        self,
        symbol: str,
        indicators: List[str]
    ) -> Dict[str, Any]:
        """
        执行技术分析

        Args:
            symbol: 交易对
            indicators: 指标列表，如["rsi", "macd", "sma"]

        Returns:
            计算结果
        """
        try:
            # 获取历史数据
            ohlcv = await self.market.get_ohlcv(
                symbol,
                timeframe="1h",
                limit=100
            )
            closes = [float(c.close) for c in ohlcv]

            result = {"symbol": symbol, "indicators": {}}

            for indicator in indicators:
                if indicator == "rsi":
                    rsi_values = self.indicators.calculate_rsi(closes)
                    result["indicators"]["rsi"] = {
                        "current": float(rsi_values[-1]),
                        "signal": self._interpret_rsi(rsi_values[-1])
                    }

                elif indicator == "macd":
                    macd_data = self.indicators.calculate_macd(closes)
                    result["indicators"]["macd"] = {
                        "macd": float(macd_data["macd"][-1]),
                        "signal": float(macd_data["signal"][-1]),
                        "histogram": float(macd_data["histogram"][-1]),
                        "interpretation": self._interpret_macd(macd_data)
                    }

                elif indicator == "sma":
                    sma_20 = self.indicators.calculate_sma(closes, 20)
                    sma_50 = self.indicators.calculate_sma(closes, 50)
                    result["indicators"]["sma"] = {
                        "sma_20": float(sma_20[-1]),
                        "sma_50": float(sma_50[-1]),
                        "current_price": closes[-1],
                        "trend": self._interpret_sma(
                            closes[-1],
                            sma_20[-1],
                            sma_50[-1]
                        )
                    }

            return result

        except Exception as e:
            logger.error(f"Technical analysis failed: {e}")
            return {"error": str(e)}

    def _interpret_rsi(self, rsi: float) -> str:
        """解读RSI"""
        if rsi > 70:
            return "超买(overbought)"
        elif rsi < 30:
            return "超卖(oversold)"
        else:
            return "中性(neutral)"

    def _interpret_macd(self, macd_data: Dict) -> str:
        """解读MACD"""
        histogram = macd_data["histogram"][-1]
        if histogram > 0:
            return "看涨(bullish)"
        else:
            return "看跌(bearish)"

    def _interpret_sma(
        self,
        price: float,
        sma_20: float,
        sma_50: float
    ) -> str:
        """解读均线"""
        if price > sma_20 > sma_50:
            return "强势上涨趋势"
        elif price < sma_20 < sma_50:
            return "强势下跌趋势"
        else:
            return "震荡或趋势不明"

    def to_function_schema(self) -> Dict[str, Any]:
        """OpenAI function格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "交易对"
                        },
                        "indicators": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["rsi", "macd", "sma", "bollinger"]
                            },
                            "description": "要计算的指标列表"
                        }
                    },
                    "required": ["symbol", "indicators"]
                }
            }
        }


class MemorySearchTool:
    """记忆搜索工具"""

    name = "memory_search"
    description = "搜索历史交易经验，找到相似情况下的决策和结果"

    def __init__(self, memory_retrieval: IMemoryRetrieval):
        self.memory = memory_retrieval

    async def execute(
        self,
        query: str,
        outcome_filter: str | None = None
    ) -> Dict[str, Any]:
        """
        搜索记忆

        Args:
            query: 查询描述
            outcome_filter: 结果过滤，"success"或"failure"

        Returns:
            相似经验列表
        """
        try:
            from src.models.memory import MemoryQuery

            memory_query = MemoryQuery(
                query_text=query,
                top_k=3,
                filters={"outcome": outcome_filter} if outcome_filter else {}
            )

            # 这里需要先实现long_term memory
            # 暂时返回示例
            return {
                "query": query,
                "results": [
                    {
                        "situation": "示例情况",
                        "decision": "示例决策",
                        "outcome": "success",
                        "lessons": ["经验1", "经验2"]
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return {"error": str(e)}

    def to_function_schema(self) -> Dict[str, Any]:
        """OpenAI function格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "描述当前情况，系统会找到相似的历史经验"
                        },
                        "outcome_filter": {
                            "type": "string",
                            "enum": ["success", "failure"],
                            "description": "只返回成功或失败的案例"
                        }
                    },
                    "required": ["query"]
                }
            }
        }


class RiskCalculatorTool:
    """风险计算工具"""

    name = "risk_calculator"
    description = "计算交易风险指标，如仓位大小、止损止盈价格等"

    async def execute(
        self,
        entry_price: float,
        stop_loss_pct: float,
        risk_amount: float
    ) -> Dict[str, Any]:
        """
        计算风险参数

        Args:
            entry_price: 入场价格
            stop_loss_pct: 止损百分比
            risk_amount: 风险金额

        Returns:
            计算结果
        """
        try:
            # 计算止损价格
            stop_loss_price = entry_price * (1 - stop_loss_pct / 100)

            # 计算仓位大小
            risk_per_unit = entry_price - stop_loss_price
            position_size = risk_amount / risk_per_unit

            # 计算止盈(风险回报比2:1)
            take_profit_price = entry_price + (entry_price - stop_loss_price) * 2

            return {
                "entry_price": entry_price,
                "stop_loss_price": round(stop_loss_price, 2),
                "take_profit_price": round(take_profit_price, 2),
                "position_size": round(position_size, 4),
                "risk_amount": risk_amount,
                "potential_profit": round(risk_amount * 2, 2),
                "risk_reward_ratio": "1:2"
            }

        except Exception as e:
            logger.error(f"Risk calculation failed: {e}")
            return {"error": str(e)}

    def to_function_schema(self) -> Dict[str, Any]:
        """OpenAI function格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entry_price": {
                            "type": "number",
                            "description": "计划入场价格"
                        },
                        "stop_loss_pct": {
                            "type": "number",
                            "description": "止损百分比，如5表示5%"
                        },
                        "risk_amount": {
                            "type": "number",
                            "description": "愿意承担的风险金额(USD)"
                        }
                    },
                    "required": ["entry_price", "stop_loss_pct", "risk_amount"]
                }
            }
        }


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self.tools: Dict[str, ITool] = {}

    def register(self, tool: ITool):
        """注册工具"""
        self.tools[tool.name] = tool
        logger.info(f"Tool registered: {tool.name}")

    def get_tool(self, name: str) -> ITool | None:
        """获取工具"""
        return self.tools.get(name)

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """获取所有工具的schema"""
        return [tool.to_function_schema() for tool in self.tools.values()]

    async def execute_tool(
        self,
        name: str,
        **kwargs
    ) -> Any:
        """执行工具"""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool not found: {name}")

        logger.info(f"Executing tool: {name} with args: {kwargs}")
        result = await tool.execute(**kwargs)
        logger.info(f"Tool {name} execution completed")

        return result
```

## 4. 战略决策器实现

```python
# src/decision/strategist.py

from typing import Dict, Any
from datetime import datetime, timedelta
import json

from src.decision.llm_client import DeepSeekClient, Message
from src.decision.prompts import PromptTemplates
from src.decision.tools import ToolRegistry
from src.memory.retrieval import IMemoryRetrieval
from src.models.portfolio import Portfolio
from src.models.decision import StrategyConfig
from src.core.logger import get_logger

logger = get_logger(__name__)


class LLMStrategist:
    """战略决策器"""

    def __init__(
        self,
        llm_client: DeepSeekClient,
        memory_retrieval: IMemoryRetrieval,
        tool_registry: ToolRegistry
    ):
        self.llm = llm_client
        self.memory = memory_retrieval
        self.tools = tool_registry

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
        logger.info(f"Analyzing market regime for {symbol}")

        # 构建消息
        messages = [
            Message(
                role="system",
                content=PromptTemplates.strategist_system_prompt()
            ),
            Message(
                role="user",
                content=f"""请分析{symbol}的当前市场状态。

要求：
1. 使用market_data_query获取最新价格数据
2. 使用technical_analysis分析技术指标
3. 综合判断市场regime（牛市/熊市/震荡）
4. 说明判断依据
"""
            )
        ]

        # 调用LLM with tools
        response = await self._chat_with_tools(messages)

        # 解析结果（这里简化处理，实际需要从response.content提取）
        return {
            "regime": "bull",  # 从LLM响应中提取
            "confidence": 0.75,
            "reasoning": response.content or "",
            "key_factors": []
        }

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
        """
        logger.info("Making strategic decision")

        # 1. 构建上下文
        context = await self._build_context(portfolio)

        # 2. 构建prompt
        messages = [
            Message(
                role="system",
                content=PromptTemplates.strategist_system_prompt()
            ),
            Message(
                role="user",
                content=PromptTemplates.build_strategist_prompt(context)
            )
        ]

        # 3. 调用LLM
        response = await self._chat_with_tools(messages)

        # 4. 解析响应并构建策略
        # 实际应该从LLM的结构化输出解析
        strategy = StrategyConfig(
            name="adaptive_strategy",
            version="1.0.0",
            description=response.content or "AI generated strategy",
            max_position_size=Decimal("0.2"),
            max_single_trade=Decimal("1000"),
            max_open_positions=3,
            max_daily_loss=Decimal("0.05"),
            max_drawdown=Decimal("0.15"),
            stop_loss_percentage=Decimal("5"),
            take_profit_percentage=Decimal("10"),
            trading_pairs=["BTC/USDT", "ETH/USDT"],
            timeframes=["1h", "4h"],
            updated_at=datetime.utcnow(),
            reason_for_update=f"Strategic review: {response.content[:100]}"
        )

        logger.info(f"Strategy created: {strategy.name} v{strategy.version}")
        return strategy

    async def _build_context(
        self,
        portfolio: Portfolio
    ) -> Dict[str, Any]:
        """构建决策上下文"""
        # 从portfolio提取信息
        context = {
            "portfolio": {
                "total_value": float(portfolio.total_value),
                "cash": float(portfolio.cash),
                "positions": [
                    {
                        "symbol": pos.symbol,
                        "value": float(pos.value),
                        "pnl": float(pos.unrealized_pnl)
                    }
                    for pos in portfolio.positions
                ],
                "total_return": float(portfolio.total_return)
            },
            "performance": {
                "7d_return": 0.0,  # 需要从数据库查询
                "30d_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0
            }
        }

        # 检索相关记忆
        similar_exp = await self.memory.retrieve_relevant_context(
            f"Portfolio value ${portfolio.total_value}, "
            f"return {portfolio.total_return}%",
            top_k=3
        )
        context["similar_experiences"] = str(similar_exp)

        return context

    async def _chat_with_tools(
        self,
        messages: list[Message]
    ) -> Any:
        """调用LLM并处理工具调用"""
        tools = self.tools.get_all_schemas()
        max_iterations = 5

        for i in range(max_iterations):
            response = await self.llm.chat(messages, tools=tools)

            # 如果没有工具调用，返回结果
            if not response.tool_calls:
                return response

            # 执行工具调用
            for tool_call in response.tool_calls:
                logger.info(f"Tool call: {tool_call.name}")

                # 执行工具
                tool_result = await self.tools.execute_tool(
                    tool_call.name,
                    **tool_call.arguments
                )

                # 添加工具结果到消息历史
                messages.append(Message(
                    role="assistant",
                    content=json.dumps({
                        "tool_call_id": tool_call.id,
                        "function": tool_call.name
                    })
                ))
                messages.append(Message(
                    role="tool",
                    content=json.dumps(tool_result),
                    name=tool_call.name
                ))

        # 超过最大迭代次数
        logger.warning("Max tool call iterations reached")
        return response
```

## 5. 战术交易器实现

战术交易器的实现类似战略决策器，主要区别在于：
- 使用trader的system prompt
- 关注具体交易信号
- 更频繁的决策更新

实现代码参考`src/decision/trader.py`，结构与strategist.py类似。

## 6. 测试

```python
# tests/decision/test_strategist.py

import pytest
from unittest.mock import Mock, AsyncMock
from decimal import Decimal

from src.decision.strategist import LLMStrategist
from src.models.portfolio import Portfolio


@pytest.fixture
def mock_llm():
    llm = Mock()
    llm.chat = AsyncMock()
    return llm


@pytest.fixture
def mock_memory():
    memory = Mock()
    memory.retrieve_relevant_context = AsyncMock(return_value={})
    return memory


@pytest.fixture
def mock_tools():
    tools = Mock()
    tools.get_all_schemas = Mock(return_value=[])
    return tools


@pytest.mark.asyncio
async def test_analyze_market_regime(mock_llm, mock_memory, mock_tools):
    """测试市场分析"""
    strategist = LLMStrategist(mock_llm, mock_memory, mock_tools)

    result = await strategist.analyze_market_regime("BTC/USDT")

    assert "regime" in result
    assert "confidence" in result
    assert result["regime"] in ["bull", "bear", "sideways"]


@pytest.mark.asyncio
async def test_make_strategic_decision(mock_llm, mock_memory, mock_tools):
    """测试战略决策"""
    strategist = LLMStrategist(mock_llm, mock_memory, mock_tools)

    # 创建测试组合
    portfolio = Portfolio(
        timestamp=int(datetime.utcnow().timestamp() * 1000),
        datetime=datetime.utcnow(),
        total_value=Decimal("10000"),
        cash=Decimal("5000"),
        positions=[]
    )

    strategy = await strategist.make_strategic_decision(portfolio)

    assert strategy.name is not None
    assert strategy.max_position_size > 0
    assert len(strategy.trading_pairs) > 0
```

## 7. 使用示例

```python
# 初始化
from src.decision.llm_client import DeepSeekClient
from src.decision.strategist import LLMStrategist
from src.decision.tools import ToolRegistry, MarketDataQueryTool
from src.core.config import Config

config = Config()

# 创建LLM客户端
llm = DeepSeekClient(
    api_key=config.get_ai_model_config("strategist").api_key
)

# 创建工具
tool_registry = ToolRegistry()
tool_registry.register(MarketDataQueryTool(market_collector))

# 创建决策器
strategist = LLMStrategist(llm, memory_retrieval, tool_registry)

# 使用
strategy = await strategist.make_strategic_decision(portfolio)
print(f"New strategy: {strategy.name}")
```

## 8. 注意事项

1. **Token管理**: 监控token使用，避免超出限制
2. **错误处理**: LLM调用可能失败，要有降级方案
3. **Prompt优化**: 持续测试和优化prompt效果
4. **工具安全**: 工具执行要有权限检查
5. **日志记录**: 记录完整的决策过程用于审计

## 9. 优化建议

1. **缓存**: 相似问题缓存LLM响应
2. **批处理**: 合并多个查询减少API调用
3. **流式输出**: 使用streaming减少延迟
4. **本地模型**: 考虑部署本地模型减少成本
