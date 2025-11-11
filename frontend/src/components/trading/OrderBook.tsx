"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useOrderBook } from "@/lib/hooks/useMarket"

interface OrderBookProps {
  symbol: string
  limit?: number
}

export function OrderBook({ symbol, limit = 10 }: OrderBookProps) {
  const { data: orderbook, isLoading } = useOrderBook(symbol, limit)

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>订单簿</CardTitle>
          <CardDescription>{symbol}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[...Array(limit * 2)].map((_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!orderbook) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>订单簿</CardTitle>
          <CardDescription>{symbol}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            暂无订单簿数据
          </div>
        </CardContent>
      </Card>
    )
  }

  // 计算最大数量用于进度条显示
  const maxAskAmount = Math.max(...orderbook.asks.map(a => a.amount))
  const maxBidAmount = Math.max(...orderbook.bids.map(b => b.amount))
  const maxAmount = Math.max(maxAskAmount, maxBidAmount)

  return (
    <Card>
      <CardHeader>
        <CardTitle>订单簿</CardTitle>
        <CardDescription>{symbol} 买卖盘深度</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 卖盘 (Ask) */}
        <div>
          <div className="flex justify-between text-xs font-medium text-muted-foreground mb-2 px-1">
            <span>卖盘价格</span>
            <span>数量</span>
          </div>
          <div className="space-y-1">
            {[...orderbook.asks].reverse().map((ask, index) => {
              const percentage = (ask.amount / maxAmount) * 100
              return (
                <div key={index} className="relative h-6 flex items-center justify-between px-2 text-sm">
                  {/* 背景进度条 */}
                  <div
                    className="absolute inset-0 bg-loss/10"
                    style={{ width: `${percentage}%`, marginLeft: `${100 - percentage}%` }}
                  />
                  {/* 数据 */}
                  <span className="relative z-10 text-loss font-medium">
                    ${ask.price.toFixed(2)}
                  </span>
                  <span className="relative z-10 text-muted-foreground">
                    {ask.amount.toFixed(4)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* 中间价格分隔线 */}
        <div className="border-t border-b py-3 flex justify-center items-center">
          <div className="text-center">
            <div className="text-2xl font-bold">
              ${orderbook.bids[0]?.price.toFixed(2) || '--'}
            </div>
            <div className="text-xs text-muted-foreground">最新价</div>
          </div>
        </div>

        {/* 买盘 (Bid) */}
        <div>
          <div className="flex justify-between text-xs font-medium text-muted-foreground mb-2 px-1">
            <span>买盘价格</span>
            <span>数量</span>
          </div>
          <div className="space-y-1">
            {orderbook.bids.map((bid, index) => {
              const percentage = (bid.amount / maxAmount) * 100
              return (
                <div key={index} className="relative h-6 flex items-center justify-between px-2 text-sm">
                  {/* 背景进度条 */}
                  <div
                    className="absolute inset-0 bg-profit/10"
                    style={{ width: `${percentage}%`, marginLeft: `${100 - percentage}%` }}
                  />
                  {/* 数据 */}
                  <span className="relative z-10 text-profit font-medium">
                    ${bid.price.toFixed(2)}
                  </span>
                  <span className="relative z-10 text-muted-foreground">
                    {bid.amount.toFixed(4)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
