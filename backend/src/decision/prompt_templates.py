#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可配置的提示词模板系统

支持不同风险级别的提示词配置：
- conservative (保守 1-3): 严格风控，高门槛
- balanced (中性 4-6): 标准风控，适度门槛
- aggressive (激进 7-8): 追求收益，低门槛
"""

from typing import Dict, Any
from enum import Enum


class PromptStyle(str, Enum):
    """提示词风格"""
    CONSERVATIVE = "conservative"  # 保守
    BALANCED = "balanced"          # 中性
    AGGRESSIVE = "aggressive"       # 激进


class PromptTemplateConfig:
    """提示词模板配置"""

    # 不同风格的配置参数
    CONFIGS = {
        PromptStyle.CONSERVATIVE: {
            "name": "保守策略",
            "risk_level": "1-3/10",
            "description": "严格风控，优先保护本金",
            "strategist": {
                "system": (
                    "你是专业的加密货币宏观策略分析师(战略层)。"
                    "你每{strategist_interval_hours}小时被调用一次，负责判断市场regime、筛选币种、设定风险参数，为战术层提供决策指导。"
                    "原则：风险优先、资本保护。输出JSON。"
                ),
                "risk_emphasis": "风险优先、严格止损",
                "cash_ratios": "牛0.2-0.3, 熊0.6-0.8, 恐慌0.9-1.0",
            },
            "trader": {
                "system": (
                    "你是专业的加密货币交易员(战术层)。"
                    "你每{trader_interval_minutes}分钟被调用一次，负责分析技术指标并生成交易信号。"
                    "战略层每{strategist_interval_hours}小时提供一次宏观判断和币种筛选。"
                    "原则：风险收益比>2.0、严格止损、优先资本保护。输出JSON数组。"
                ),
                "risk_reward_ratio": ">2.0",
                "confidence_thresholds": {
                    "aggressive": 0.70,
                    "normal": 0.75,
                    "conservative": 0.80,
                    "defensive": 0.90,
                },
                "position_bias": "保守仓位，优先止损",
            },
        },
        PromptStyle.BALANCED: {
            "name": "中性策略",
            "risk_level": "4-6/10",
            "description": "平衡风险与收益",
            "strategist": {
                "system": (
                    "你是专业的加密货币宏观策略分析师(战略层)。"
                    "你每{strategist_interval_hours}小时被调用一次，负责判断市场regime、筛选币种、设定风险参数，为战术层提供决策指导。"
                    "原则：数据驱动、风险收益平衡。输出JSON。"
                ),
                "risk_emphasis": "风险收益平衡",
                "cash_ratios": "牛0.1-0.2, 熊0.4-0.6, 恐慌0.7-0.9",
            },
            "trader": {
                "system": (
                    "你是专业的加密货币交易员(战术层)。"
                    "你每{trader_interval_minutes}分钟被调用一次，负责分析技术指标并生成交易信号。"
                    "战略层每{strategist_interval_hours}小时提供一次宏观判断和币种筛选。"
                    "原则：风险收益比>1.2、抓住优质机会、适度风控。输出JSON数组，每个币种一个信号。"
                ),
                "risk_reward_ratio": ">1.2",
                "confidence_thresholds": {
                    "aggressive": 0.55,
                    "normal": 0.65,
                    "conservative": 0.70,
                    "defensive": 0.80,
                },
                "position_bias": "标准仓位，灵活调整",
            },
        },
        PromptStyle.AGGRESSIVE: {
            "name": "激进策略",
            "risk_level": "7-8/10",
            "description": "追求高收益，承担较高风险",
            "strategist": {
                "system": (
                    "你是专业的加密货币宏观策略分析师(战略层)。"
                    "你每{strategist_interval_hours}小时被调用一次，负责判断市场regime、筛选币种、设定风险参数，为战术层提供决策指导。"
                    "原则：机会优先、积极进取。输出JSON。"
                ),
                "risk_emphasis": "机会优先，积极进取",
                "cash_ratios": "牛0.05-0.1, 熊0.2-0.4, 恐慌0.5-0.7",
            },
            "trader": {
                "system": (
                    "你是专业的加密货币交易员(战术层)。"
                    "你每{trader_interval_minutes}分钟被调用一次，负责分析技术指标并生成交易信号。"
                    "战略层每{strategist_interval_hours}小时提供一次宏观判断和币种筛选。"
                    "原则：风险收益比>1.0、抓住趋势、适度止损。输出JSON数组。"
                ),
                "risk_reward_ratio": ">1.0",
                "confidence_thresholds": {
                    "aggressive": 0.50,
                    "normal": 0.60,
                    "conservative": 0.65,
                    "defensive": 0.75,
                },
                "position_bias": "积极开仓，趋势跟随",
            },
        },
    }

    @classmethod
    def get_strategist_system_prompt(cls, style: PromptStyle = PromptStyle.BALANCED) -> str:
        """获取战略层系统提示词"""
        config = cls.CONFIGS[style]["strategist"]
        return config["system"]

    @classmethod
    def get_trader_system_prompt(cls, style: PromptStyle = PromptStyle.BALANCED) -> str:
        """获取战术层系统提示词"""
        config = cls.CONFIGS[style]["trader"]
        return config["system"]

    @classmethod
    def get_strategist_user_template(cls, style: PromptStyle = PromptStyle.BALANCED) -> str:
        """获取战略层用户提示词模板"""
        config = cls.CONFIGS[style]["strategist"]

        # 使用 %s 占位符避免花括号冲突
        template = """
# 市场环境
%s

# 加密市场数据
%s

# 可交易币种池
%s

# 任务
分析市场regime并输出JSON:

**Regime分类**: bull(牛)/bear(熊)/sideways(震荡)/panic(恐慌)
**Risk_level**: low/medium/high/extreme
**风险管理**: %s
**币种筛选**: 从可交易币种池中选择。牛市→多币种, 熊市→BTC/ETH优先, 震荡→3-5个, 恐慌→BTC/ETH
**现金比例**: %s

**JSON格式** (示例):
{
    "regime": "bull",
    "confidence": 0.75,
    "recommended_symbols": ["BTC","ETH"],
    "max_symbols_to_trade": 5,
    "blacklist_symbols": [],
    "risk_level": "medium",
    "market_narrative": "1-2句话总结",
    "key_drivers": ["驱动因素1","驱动因素2"],
    "time_horizon": "medium",
    "suggested_allocation": {"BTC":0.5,"ETH":0.3},
    "cash_ratio": 0.2,
    "trading_mode": "normal",
    "position_sizing_multiplier": 1.0,
    "reasoning": "分析逻辑和风险"
}

输出JSON:
"""
        return template % (
            "{env_summary}",
            "{crypto_summary}",
            "{available_symbols}",
            config['risk_emphasis'],
            config['cash_ratios']
        )

    @classmethod
    def get_trader_user_template(cls, style: PromptStyle = PromptStyle.BALANCED) -> str:
        """获取战术层用户提示词模板"""
        config = cls.CONFIGS[style]["trader"]
        thresholds = config["confidence_thresholds"]

        # 使用 %s 占位符避免花括号冲突
        template = """
# 战略判断
Regime: %s | 风险: %s | 模式: %s | 仓位系数: %sx | 现金目标: %s
叙事: %s
驱动: %s
推荐: %s

# 账户信息
%s

# 持仓状态
%s

# 技术数据
%s

# 任务
基于战略指导和技术分析,为每个币种生成**多空双向**交易信号

**策略风格**: %s
**风险收益比要求**: %s

**交易模式约束**:
- aggressive: 信心≥%.2f可开仓, 止损可松
- normal: 信心≥%.2f开仓, 标准止损
- conservative: 信心≥%.2f开仓, 止损收紧
- defensive: 信心≥%.2f开仓, 优先止损

**信号类型说明/开仓/平仓判断参考** (signal_type):
- enter_long: 开多仓, RSI<30超卖反弹, MACD金叉, 突破上轨, 趋势向上
- exit_long: 平多仓, 已有多头持仓且 (1)触及止盈目标 (2)趋势反转做空信号 (3)亏损需止损
- enter_short: 开空仓, RSI>70超买回落, MACD死叉, 跌破下轨, 趋势向下
- exit_short: 平空仓, 已有空头持仓且 (1)触及止盈目标 (2)趋势反转做多信号 (3)亏损需止损
- hold: 持仓观望 (无明确信号)

**杠杆设置规则**:
- BTC/ETH: 5-50x (主流币种，建议 5-25x)
- 其他币种: 5-20x (山寨币风险高，建议 5-15x)
- 根据市场环境调整: 牛市可适度提高，熊市/恐慌降低

**期货仓位风控**:
- 单币种保证金占比上限: {max_position_size}%%
- 仓位计算公式: 保证金占比 = (数量 × 价格 / 杠杆) / 总资产
- 示例: 总资产4400 USDT, ETH价格3500, 杠杆8x, 最大占比30%%
  → 最大数量 = (4400 × 0.30 × 8) / 3500 = 3.01 ETH
  → 验证: (3.01 × 3500 / 8) / 4400 = 30%%

**重要提醒**:
1. **期货仓位计算**: 使用杠杆后的保证金占比，不是名义价值
2. **持仓状态分析**: 当前持仓的方向(多/空)、杠杆倍数、强平价格、盈亏情况、持仓时长
3. **避免方向冲突**: 如已有多头持仓，不要开空仓；已有空头持仓，不要开多仓
4. **合理分配仓位**: 计算保证金占比，不能超过{max_position_size}%%，否则风控不通过
5. **平仓决策**: 结合市场行情、技术指标、持仓时长和盈亏情况，自主判断是否需要平仓(止损/止盈已在开仓时挂单，无需手动平仓)
6. **交易纪律**: 作为专业交易员，避免被市场噪音误导，让盈利持仓充分发展，避免频繁开平同一币种

**JSON格式** (示例):
[
  {
    "symbol": "BTC/USDT",
    "signal_type": "enter_long",
    "confidence": 0.75,
    "suggested_price": 75000.0,
    "suggested_amount": 0.01,
    "stop_loss": 73000.0,
    "take_profit": 78000.0,
    "leverage": 3,
    "reasoning": "技术面+战略判断+多空方向选择+杠杆选择",
    "supporting_factors": ["因素1"],
    "risk_factors": ["风险1"]
  },
  {
    "symbol": "ETH/USDT",
    "signal_type": "exit_short",
    "confidence": 0.80,
    "reasoning": "空头持仓已达止盈目标，趋势反转信号出现，建议平仓锁定利润"
  }
]

输出JSON:%s
"""
        return template % (
            "{regime}",
            "{risk_level}",
            "{trading_mode}",
            "{position_multiplier}",
            "{cash_ratio}",
            "{market_narrative}",
            "{key_drivers}",
            "{recommended_symbols}",
            "{account_info}",
            "{portfolio_positions}",
            "{symbols_info}",
            config['position_bias'],
            config['risk_reward_ratio'],
            thresholds['aggressive'],
            thresholds['normal'],
            thresholds['conservative'],
            thresholds['defensive'],
            ""  # 用于填充末尾的 %s 占位符
        )

    @classmethod
    def get_config_info(cls, style: PromptStyle) -> Dict[str, Any]:
        """获取配置信息"""
        return cls.CONFIGS[style]
