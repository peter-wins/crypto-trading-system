"use client"

import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useMultipleTickers } from "@/lib/hooks/useMarket"
import { formatSymbol } from "@/lib/utils/symbol"
import { TrendingUp, TrendingDown } from "lucide-react"

interface MarketTickerCardsProps {
  symbols: string[]
}

export function MarketTickerCards({ symbols }: MarketTickerCardsProps) {
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
        const changeColor = isPositive
          ? "text-green-600 dark:text-green-400"
          : "text-red-600 dark:text-red-400"

        return (
          <Card key={ticker.symbol} className="overflow-hidden">
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
}
