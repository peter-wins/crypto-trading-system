import { z } from "zod"

/**
 * 交易相关类型定义
 */

// 订单方向
export const OrderSideSchema = z.enum(["BUY", "SELL"])
export type OrderSide = z.infer<typeof OrderSideSchema>

// 订单类型
export const OrderTypeSchema = z.enum(["MARKET", "LIMIT", "STOP_LOSS", "TAKE_PROFIT"])
export type OrderType = z.infer<typeof OrderTypeSchema>

// 订单状态
export const OrderStatusSchema = z.enum([
  "PENDING",
  "OPEN",
  "PARTIALLY_FILLED",
  "FILLED",
  "CANCELLED",
  "REJECTED",
])
export type OrderStatus = z.infer<typeof OrderStatusSchema>

// 订单
export const OrderSchema = z.object({
  id: z.string(),
  symbol: z.string(),
  side: OrderSideSchema,
  type: OrderTypeSchema,
  status: OrderStatusSchema,
  price: z.number().nullable(),
  amount: z.number(),
  filled: z.number(),
  remaining: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
})

export type Order = z.infer<typeof OrderSchema>

// 持仓
export const PositionSchema = z.object({
  symbol: z.string(),
  side: z.string(),
  amount: z.number(),
  entry_price: z.number(),
  average_price: z.number(),
  current_price: z.number(),
  unrealized_pnl: z.number(),
  unrealized_pnl_percentage: z.number(),
  value: z.number(),
  cost: z.number(),
  stop_loss: z.number().nullable().optional(),
  take_profit: z.number().nullable().optional(),
})

export type Position = z.infer<typeof PositionSchema>

// 交易记录
export const TradeSchema = z.object({
  id: z.string(),
  symbol: z.string(),
  side: OrderSideSchema,
  price: z.number(),
  amount: z.number(),
  value: z.number(),
  fee: z.number(),
  timestamp: z.string(),
  order_id: z.string(),
})

export type Trade = z.infer<typeof TradeSchema>
