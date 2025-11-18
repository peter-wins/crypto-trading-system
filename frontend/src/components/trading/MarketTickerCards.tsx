"use client"

import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useMultipleTickers } from "@/lib/hooks/useMarket"
import { formatSymbol } from "@/lib/utils/symbol"
import { TrendingUp, TrendingDown } from "lucide-react"
import { memo } from "react"

interface MarketTickerCardsProps {
  symbols: string[]
}

export const MarketTickerCards = memo(function MarketTickerCards({ symbols }: MarketTickerCardsProps) {
  const { data: tickers, isLoading } = useMultipleTickers(symbols)

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-4">
        {symbols.map((symbol) => (
          <Skeleton key={symbol} className="h-24" />
        ))}
      </div>
    )
  }

  if (!tickers || tickers.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        暂无市场数据
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-4">
      {tickers.map((ticker) => {
        const isPositive = (ticker.change_percentage_24h || 0) >= 0
        const changeColor = isPositive ? "text-profit" : "text-loss"

        return (
          <Card key={ticker.symbol} className="overflow-hidden hover:shadow-md transition-shadow cursor-pointer">
            <CardContent className="p-4">
              <div className="space-y-2">
                {/* 交易对 */}
                <div className="font-semibold text-sm">
                  {formatSymbol(ticker.symbol)}
                </div>

                {/* 价格 */}
                <div className="text-2xl font-bold">
                  ${ticker.last.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </div>

                {/* 24h涨跌 */}
                <div className={`flex items-center gap-1 text-sm font-medium ${changeColor}`}>
                  {isPositive ? (
                    <TrendingUp className="h-4 w-4" />
                  ) : (
                    <TrendingDown className="h-4 w-4" />
                  )}
                  <span>
                    {isPositive ? "+" : ""}
                    {(ticker.change_percentage_24h || 0).toFixed(2)}%
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}, (prevProps, nextProps) => {
  // 仅当 symbols 数组内容改变时重新渲染
  return JSON.stringify(prevProps.symbols) === JSON.stringify(nextProps.symbols)
})
