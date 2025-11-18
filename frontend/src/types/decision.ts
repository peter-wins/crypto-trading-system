import { z } from "zod"

/**
 * AI决策相关类型定义
 */

// 决策类型
export const DecisionTypeSchema = z.enum(["STRATEGIC", "TACTICAL"])
export type DecisionType = z.infer<typeof DecisionTypeSchema>

// 信号类型
export const SignalTypeSchema = z.enum(["ENTER_LONG", "EXIT_LONG", "ENTER_SHORT", "EXIT_SHORT", "HOLD"])
export type SignalType = z.infer<typeof SignalTypeSchema>

// 风险等级
export const RiskLevelSchema = z.enum(["LOW", "MEDIUM", "HIGH"])
export type RiskLevel = z.infer<typeof RiskLevelSchema>

// 恐慌贪婪标签
export const FearGreedLabelSchema = z.enum(["EXTREME_FEAR", "FEAR", "NEUTRAL", "GREED", "EXTREME_GREED"])
export type FearGreedLabel = z.infer<typeof FearGreedLabelSchema>

// 决策上下文
export const DecisionContextSchema = z.object({
  // 基本信息
  symbol: z.string().optional(),
  regime: z.string().optional(),
  trading_mode: z.string().optional(),
  risk_level: z.string().optional(), // 保持字符串以兼容后端
  cash_ratio: z.number().optional(),
  position_multiplier: z.number().optional(),

  // 战术决策特有字段
  bias: z.string().optional(), // 战术偏向 (bearish/bullish)
  market_structure: z.string().optional(), // 市场结构 (extreme/normal)

  // 投资组合
  portfolio: z.object({
    cash: z.string(),
    daily_pnl: z.string(),
    total_value: z.string(),
    positions_count: z.number(),
  }).optional(),

  // 市场快照
  market_snapshot: z.object({
    latest_price: z.string(),
  }).optional(),

  // 现有持仓
  existing_position: z.object({
    side: z.string(), // 保持字符串,因为后端返回小写 "buy"/"sell"
    amount: z.string(),
    leverage: z.number().nullable().optional(),
    entry_price: z.string(),
    current_price: z.string(),
    unrealized_pnl: z.string(),
    unrealized_pnl_pct: z.string(),
  }).optional(),

  // 环境数据（战略决策）
  sentiment: z.object({
    fear_greed_index: z.number().nullable(),
    fear_greed_label: z.string().nullable(), // 保持字符串以兼容后端
  }).optional(),
  macro_data: z.object({
    fed_rate: z.number().nullable(),
    dxy_change_24h: z.number().nullable(),
  }).optional(),
  environment_summary: z.string().optional().nullable(),
  environment_data_completeness: z.number().optional().nullable(),
}).passthrough() // 改回 passthrough 以允许后端的额外字段

export type DecisionContext = z.infer<typeof DecisionContextSchema>

// 决策记录
export const DecisionRecordSchema = z.object({
  id: z.string(),
  timestamp: z.string(),
  decision_type: DecisionTypeSchema,
  symbol: z.string().nullable().optional(),
  signal: SignalTypeSchema.nullable().optional(),
  reasoning: z.string(),
  confidence: z.number(),
  context: DecisionContextSchema.nullable().optional(),
  tool_calls: z.array(z.object({
    name: z.string(),
    arguments: z.record(z.string(), z.unknown()), // 使用 unknown 替代 any
    result: z.unknown().nullable().optional(), // 使用 unknown 替代 any
  })).nullable().optional(),
  outcome: z.string().nullable().optional(),
  model_used: z.string().nullable().optional(),
})

export type DecisionRecord = z.infer<typeof DecisionRecordSchema>

// 市场状态
export const MarketRegimeSchema = z.enum(["BULL", "BEAR", "SIDEWAYS", "VOLATILE"])
export type MarketRegime = z.infer<typeof MarketRegimeSchema>

// 战略决策
export const StrategyConfigSchema = z.object({
  market_regime: MarketRegimeSchema,
  confidence: z.number(),
  risk_level: z.number(),
  max_position_size: z.number(),
  active_symbols: z.array(z.string()),
  reasoning: z.string(),
})

export type StrategyConfig = z.infer<typeof StrategyConfigSchema>
