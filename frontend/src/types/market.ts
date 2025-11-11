import { z } from "zod"

/**
 * 市场数据相关类型定义
 */

// Ticker数据
export const TickerSchema = z.object({
  symbol: z.string(),
  timestamp: z.number(),
  datetime: z.string(),
  last: z.number(),
  bid: z.number(),
  ask: z.number(),
  high: z.number(),
  low: z.number(),
  volume: z.number(),
  change_24h: z.number().optional(),
  change_percentage_24h: z.number().optional(),
})

export type Ticker = z.infer<typeof TickerSchema>

// K线数据
export const OHLCVSchema = z.object({
  symbol: z.string(),
  timestamp: z.number(),
  datetime: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number(),
})

export type OHLCV = z.infer<typeof OHLCVSchema>

// 订单簿
export const OrderBookLevelSchema = z.object({
  price: z.number(),
  amount: z.number(),
})

export const OrderBookSchema = z.object({
  symbol: z.string(),
  timestamp: z.number(),
  bids: z.array(OrderBookLevelSchema),
  asks: z.array(OrderBookLevelSchema),
})

export type OrderBook = z.infer<typeof OrderBookSchema>
export type OrderBookLevel = z.infer<typeof OrderBookLevelSchema>
