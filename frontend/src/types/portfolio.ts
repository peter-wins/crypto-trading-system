import { z } from "zod"
import { PositionSchema } from "./trading"

/**
 * 投资组合相关类型定义
 */

export const PortfolioSchema = z.object({
  // 币安对应字段
  wallet_balance: z.number(),
  available_balance: z.number(),
  margin_balance: z.number(),
  unrealized_pnl: z.number(),

  // 额外统计字段
  total_initial_margin: z.number(),
  unrealized_pnl_percentage: z.number(),
  daily_pnl: z.number(),
  daily_pnl_percentage: z.number(),

  positions: z.array(PositionSchema),
  updated_at: z.string(),

  // 兼容旧字段（可选）
  total_value: z.number().optional(),
  cash: z.number().optional(),
  invested: z.number().optional(),
})

export type Portfolio = z.infer<typeof PortfolioSchema>

// 绩效指标
export const PerformanceMetricsSchema = z.object({
  total_return: z.number(),
  total_return_percentage: z.number(),
  sharpe_ratio: z.number(),
  max_drawdown: z.number(),
  max_drawdown_percentage: z.number(),
  win_rate: z.number(),
  total_trades: z.number(),
  profitable_trades: z.number(),
  losing_trades: z.number(),
  average_profit: z.number(),
  average_loss: z.number(),
  profit_factor: z.number(),
})

export type PerformanceMetrics = z.infer<typeof PerformanceMetricsSchema>

// 净值数据点
export const EquityPointSchema = z.object({
  timestamp: z.string(),
  value: z.number(),
})

export type EquityPoint = z.infer<typeof EquityPointSchema>
