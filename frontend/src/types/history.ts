import { z } from "zod"

// ===== 已平仓记录 =====

export const ClosedPositionSchema = z.object({
  id: z.number(),
  symbol: z.string(),
  side: z.string(), // buy/sell

  // 开仓信息
  entry_order_id: z.string().nullable(),
  entry_price: z.number(),
  entry_time: z.string(),

  // 平仓信息
  exit_order_id: z.string().nullable(),
  exit_price: z.number(),
  exit_time: z.string(),

  // 数量和金额
  amount: z.number(),
  entry_value: z.number(),
  exit_value: z.number(),

  // 盈亏
  realized_pnl: z.number(),
  realized_pnl_percentage: z.number(),

  // 其他
  holding_duration_seconds: z.number().nullable(),
  holding_duration_display: z.string().nullable(),
  leverage: z.number().nullable(),
})

export type ClosedPosition = z.infer<typeof ClosedPositionSchema>

// ===== 订单历史 =====

export const OrderHistorySchema = z.object({
  id: z.string(),
  client_order_id: z.string(),
  symbol: z.string(),
  side: z.string(), // buy/sell
  type: z.string(),
  status: z.string(),

  price: z.number().nullable(),
  amount: z.number(),
  filled: z.number(),
  cost: z.number(),
  average: z.number().nullable(),
  fee: z.number().nullable(),

  datetime: z.string(),
})

export type OrderHistory = z.infer<typeof OrderHistorySchema>
