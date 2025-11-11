"""
Prompt Templates for the Decision Engine.

Provides reusable system and task prompts for strategist and trader roles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from src.decision.prompt_templates import PromptTemplateConfig, PromptStyle
from src.core.config import get_config


class PromptTemplates:
    """Static collection of prompt builders for decision making agents."""

    @staticmethod
    def _get_prompt_style() -> PromptStyle:
        """获取当前配置的提示词风格"""
        config = get_config()
        style_str = getattr(config, 'prompt_style', 'balanced')
        try:
            return PromptStyle(style_str)
        except ValueError:
            return PromptStyle.BALANCED

    @staticmethod
    def strategist_system_prompt(strategist_interval_hours: float = 1.0) -> str:
        """System prompt for the strategic decision maker."""
        style = PromptTemplates._get_prompt_style()
        template = PromptTemplateConfig.get_strategist_system_prompt(style)
        # 替换决策间隔占位符
        return template.format(strategist_interval_hours=strategist_interval_hours)

    @staticmethod
    def trader_system_prompt(trader_interval_minutes: float = 3.0, strategist_interval_hours: float = 1.0) -> str:
        """System prompt for the tactical trader."""
        style = PromptTemplates._get_prompt_style()
        template = PromptTemplateConfig.get_trader_system_prompt(style)
        # 替换决策间隔占位符
        return template.format(
            trader_interval_minutes=trader_interval_minutes,
            strategist_interval_hours=strategist_interval_hours
        )

    @staticmethod
    def reflection_prompt() -> str:
        """Prompt for post-trade reflection."""
        return (
            "请对以下交易进行深入反思：\n\n"
            "交易信息：\n"
            "{trade_info}\n\n"
            "决策过程：\n"
            "{decision_process}\n\n"
            "结果：\n"
            "{outcome}\n\n"
            "请回答：\n"
            "1. 决策的优点是什么？\n"
            "2. 有哪些可以改进的地方？\n"
            "3. 学到了哪些经验？\n"
            "4. 下次遇到类似情况应该怎样做？\n\n"
            "请保持客观和具体，避免模糊或空泛的总结。"
        )

    @staticmethod
    def build_strategist_prompt(context: Dict[str, Any]) -> str:
        """Build task prompt for the strategist using contextual information."""
        portfolio = context.get("portfolio", {})
        performance = context.get("performance", {})
        experiences = context.get("similar_experiences", "暂无相关经验")
        symbols = context.get("symbols", [])  # 获取交易对列表

        def _fmt_percentage(value: Any, default: float = 0.0) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # 交易对格式提示
        symbols_hint = ""
        if symbols:
            symbols_hint = (
                f"\n\n=== 监控的交易对 ===\n"
                + "\n".join([f"  - {sym}" for sym in symbols])
                + "\n\nℹ️ **说明**：这些是数据源的交易对格式，用于查询市场数据。\n"
                + "   系统会自动将策略映射到交易所支持的格式。\n"
                + "\n⚠️ **重要**：调用工具时，symbol 参数必须严格使用上述格式。"
            )

        prompt = (
            f"当前时间：{now_str}\n\n"
            "=== 投资组合状态 ===\n"
            f"总价值: ${portfolio.get('total_value', 0):,.2f}\n"
            f"现金: ${portfolio.get('cash', 0):,.2f}\n"
            f"持仓数量: {len(portfolio.get('positions', []))}\n"
            f"累计收益率: {_fmt_percentage(portfolio.get('total_return')):.2f}%\n"
            f"{symbols_hint}\n\n"
            "=== 最近绩效 ===\n"
            f"7日收益: {_fmt_percentage(performance.get('7d_return')):.2f}%\n"
            f"30日收益: {_fmt_percentage(performance.get('30d_return')):.2f}%\n"
            f"夏普比率: {_fmt_percentage(performance.get('sharpe_ratio')):.2f}\n"
            f"最大回撤: {_fmt_percentage(performance.get('max_drawdown')):.2f}%\n\n"
            "=== 历史相似经验 ===\n"
            f"{experiences}\n\n"
            "=== 任务 ===\n"
            "1. 判断当前市场regime（牛市/熊市/震荡）\n"
            "2. 建议资产配置（现金比例、目标持仓）\n"
            "3. 设定风险参数（最大仓位、止损比例等）\n"
            "4. 说明决策理由与潜在风险\n\n"
            "请充分使用可用工具（使用上述交易对格式），最后以结构化JSON输出：\n"
            '{"regime": ..., "confidence": ..., "strategy": {...}, "risk_parameters": {...}, "reasoning": "..."}'
        )

        return prompt

    @staticmethod
    def build_batch_trader_prompt(batch_context: Dict[str, Any]) -> str:
        """构建批量分析多个交易对的提示词"""
        symbols_data = batch_context.get("symbols_data", {})
        strategy = batch_context.get("strategy", "无策略描述")
        risk_params = batch_context.get("risk_params", {})
        account_info = batch_context.get("account_info", "无账户信息")
        portfolio_positions = batch_context.get("portfolio_positions", {})

        def _format_percentage(value: Any, default: float = 0.0) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # 构建每个币种的数据部分
        symbols_sections = []
        for symbol, data in symbols_data.items():
            market_data = data.get("market_data", "暂无市场数据")
            position_info = portfolio_positions.get(symbol, f"当前无 {symbol} 持仓")

            symbol_section = (
                f"### {symbol} ###\n"
                f"{market_data}\n\n"
                f"持仓状态:\n{position_info}\n"
            )
            symbols_sections.append(symbol_section)

        symbols_content = "\n".join(symbols_sections)

        prompt = (
            f"当前时间：{now_str}\n\n"
            "=== 批量分析任务 ===\n"
            f"你需要同时分析 {len(symbols_data)} 个交易对，为每个交易对生成独立的交易信号。\n\n"
            "=== 账户状态 ===\n"
            f"{account_info}\n\n"
            "=== 当前策略 ===\n"
            f"{strategy}\n\n"
            "=== 风险参数 ===\n"
            f"最大仓位: {_format_percentage(risk_params.get('max_position_size')):.2f}%\n"
            f"止损比例: {_format_percentage(risk_params.get('stop_loss_percentage')):.2f}%\n"
            f"止盈比例: {_format_percentage(risk_params.get('take_profit_percentage')):.2f}%\n"
            f"单笔最大交易额: {risk_params.get('max_single_trade', '未设定')}\n\n"
            "=== 各交易对市场数据 ===\n"
            f"{symbols_content}\n"
            "=== 分析要求 ===\n\n"
            "**请为每个交易对独立分析：**\n\n"
            "1. **分析市场数据**：\n"
            "   - 查看价格、RSI、MACD、均线、布林带\n"
            "   - 判断趋势和信号强度\n\n"
            "2. **评估持仓状态**：\n"
            "   - 如果有持仓，评估盈亏和风险\n"
            "   - 如果无持仓，评估入场机会\n\n"
            "3. **跨币种比较**（重要优势！）：\n"
            "   - 比较各币种的机会质量\n"
            "   - 优先推荐信号更强、风险更低的币种\n"
            "   - 如果多个币种同时有机会，考虑分散风险\n\n"
            "4. **制定交易决策**：\n"
            "   - 对于强信号且风险可控的币种，建议开仓或加仓\n"
            "   - 对于弱信号或高风险的币种，建议观望或减仓\n"
            "   - 对于亏损持仓，评估是否止损或等待反弹\n\n"
            "**输出格式（JSON数组）：**\n"
            "[\n"
            "  {\n"
            '    "symbol": "BTC/USDC:USDC",\n'
            '    "signal_type": "enter_long",  // enter_long/exit_long/enter_short/exit_short/hold\n'
            '    "confidence": 0.75,  // 0-1之间\n'
            '    "suggested_price": 75000.0,\n'
            '    "suggested_amount": 0.01,\n'
            '    "stop_loss": 73000.0,\n'
            '    "take_profit": 78000.0,\n'
            '    "reasoning": "BTC技术指标强势，MACD金叉，RSI适中，建议做多"\n'
            "  },\n"
            "  {\n"
            '    "symbol": "ETH/USDC:USDC",\n'
            '    "signal_type": "hold",\n'
            '    "confidence": 0.3,\n'
            '    "reasoning": "ETH信号不明确，相比BTC机会较弱，建议观望"\n'
            "  }\n"
            "]\n\n"
            "**注意事项：**\n"
            "- 每个币种都必须输出一个信号（即使是hold）\n"
            "- 优先推荐高置信度、高胜率的机会\n"
            "- 考虑账户总体风险暴露，避免过度集中\n"
            "- reasoning要简洁说明决策依据和跨币种比较的结论"
        )

        return prompt

    @staticmethod
    def build_trader_prompt(symbol: str, context: Dict[str, Any]) -> str:
        """Build task prompt for the trader."""
        strategy_description = context.get("strategy", "无策略描述")
        risk_params = context.get("risk_params", {})
        current_position = context.get("current_position", "暂无持仓")
        account_info = context.get("account_info", "无账户信息")
        similar_cases = context.get("similar_cases", "暂无相关案例")

        def _format_percentage(value: Any, default: float = 0.0) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        # 市场数据
        market_data = context.get("market_data")
        market_section = ""
        if market_data:
            market_section = f"=== {symbol} 市场数据 ===\n{market_data}\n\n"

        prompt = (
            f"当前时间：{now_str}\n\n"
            f"=== 分析目标 ===\n{symbol}\n"
            f"ℹ️ **说明**：这是数据源的交易对格式。系统会自动将你的决策映射到交易所支持的格式进行下单。\n\n"
            "=== 账户状态 ===\n"
            f"{account_info}\n\n"
            f"=== {symbol} 当前持仓 ===\n"
            f"{current_position}\n\n"
            f"{market_section}"
            "=== 当前策略 ===\n"
            f"{strategy_description}\n\n"
            "=== 风险参数 ===\n"
            f"最大仓位: {_format_percentage(risk_params.get('max_position_size')):.2f}%\n"
            f"止损比例: {_format_percentage(risk_params.get('stop_loss_percentage')):.2f}%\n"
            f"止盈比例: {_format_percentage(risk_params.get('take_profit_percentage')):.2f}%\n"
            f"单笔最大交易额: {risk_params.get('max_single_trade', '未设定')}\n\n"
            "=== 历史相似案例 ===\n"
            f"{similar_cases}\n\n"
            "=== 任务 ===\n"
            f"请分析 {symbol} 当前的交易机会：\n\n"
            "**分析步骤：**\n"
            "1. **分析当前市场数据**（上方已提供）：\n"
            "   - 查看最新价格和技术指标（RSI、MACD、均线、布林带）\n"
            "   - 判断市场趋势和关键信号\n"
            "   - RSI: <30超卖（考虑做多）、>70超买（考虑做空）\n"
            "   - MACD: 金叉（做多信号）、死叉（做空信号）\n"
            "   - 布林带: 突破上轨（强势）、跌破下轨（弱势）\n\n"
            "2. **评估账户和持仓状态**：\n"
            "   - 检查可用现金是否足够开新仓\n"
            "   - 如果已有持仓，评估当前盈亏和风险\n"
            "   - 评估总体风险暴露是否过高\n\n"
            "3. **制定交易策略**：\n"
            "   \n"
            "   **如果无持仓：**\n"
            "   - 评估是否有高胜率的入场机会\n"
            "   - 计算合理的仓位大小（可以保守一点，留有余地）\n"
            "   - 确保有足够的现金\n"
            "   \n"
            "   **如果有亏损持仓（这是关键！）：**\n"
            "   - 🎯 核心目标：**尽最大可能挽回损失**\n"
            "   - 深度思考以下问题：\n"
            "     1. 这是技术性回调还是趋势已经反转？\n"
            "     2. 如果全部止损，损失是X；如果等待反弹，最好情况收益Y，最坏情况损失Z\n"
            "     3. 如果部分止损（如50%），风险和收益如何平衡？\n"
            "     4. 如果设置更紧的止损价继续持有，给反弹机会，风险可控吗？\n"
            "   - 可选策略（自主选择，不限于此）：\n"
            "     * 立即全部止损（适用于：趋势明确反转，无反弹希望）\n"
            "     * 部分止损30-70%（适用于：降低风险但保留反弹机会）\n"
            "     * 继续持有+紧止损（适用于：技术指标显示可能反弹）\n"
            "     * 分批止损（在不同价位分批退出）\n"
            "   - **关键**：在reasoning中详细说明你的分析和选择理由\n"
            "   \n"
            "   **如果有盈利持仓：**\n"
            "   - 评估是否达到预期目标\n"
            "   - 判断趋势是否还能延续\n"
            "   - 考虑部分止盈（锁定利润）或全部止盈\n"
            "   - 或者移动止盈点，让利润奔跑\n"
            "   \n"
            "   **如果现金不足：**\n"
            "   - 只能管理现有持仓，不能开新仓\n"
            "   - 重点关注如何优化现有持仓\n\n"
            "5. **计算具体参数**：\n"
            "   - 入场价、止损价、止盈价\n"
            "   - 评估信心度和风险回报比\n\n"
            "**决策标准：**\n"
            "- 技术指标共振（多个指标同向）→ 信心度 0.7-0.9\n"
            "- 单一指标明确信号 → 信心度 0.6-0.7\n"
            "- 指标矛盾或无明确方向 → 信心度 <0.6，选择 hold\n"
            "- **持仓管理优先**：已有持仓时，止损止盈决策比开新仓更重要\n\n"
            "**输出JSON格式：**\n"
            "```json\n"
            '{\n'
            '  "signal_type": "enter_long",  // enter_long|exit_long|enter_short|exit_short|hold\n'
            '  "confidence": 0.75,  // 0-1之间，>0.6应执行\n'
            '  "suggested_price": 45000.0,  // 建议入场价\n'
            '  "stop_loss": 43500.0,  // 止损价\n'
            '  "take_profit": 48000.0,  // 止盈价\n'
            '  "suggested_amount": 0.01,  // 建议数量（可选）\n'
            '  "reasoning": "MACD金叉，RSI从30区域反弹，布林带下轨附近支撑，多个指标共振显示做多机会",\n'
            '  "factors": {\n'
            '    "supporting": ["MACD金叉", "RSI超卖反弹", "布林带下轨支撑"],\n'
            '    "risks": ["大盘走弱", "成交量偏低"]\n'
            '  }\n'
            '}\n'
            "```\n\n"
            "**记住**：作为交易员，你的职责是发现并执行交易机会。当技术指标给出信号时，应该果断行动！"
        )

        return prompt
