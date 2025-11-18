"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useMultipleTickers } from "@/lib/hooks/useMarket"
import { formatSymbol } from "@/lib/utils/symbol"
import { TrendingUp, TrendingDown } from "lucide-react"

interface MarketTickerProps {
  symbols: string[]
}

export function MarketTicker({ symbols }: MarketTickerProps) {
  const { data: tickers, isLoading } = useMultipleTickers(symbols)

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>实时行情</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[...Array(symbols.length)].map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!tickers || tickers.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>实时行情</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            暂无行情数据
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>实时行情</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>交易对</TableHead>
              <TableHead className="text-right">最新价</TableHead>
              <TableHead className="text-right">24h涨跌</TableHead>
              <TableHead className="text-right">24h涨跌幅</TableHead>
              <TableHead className="text-right">24h最高</TableHead>
              <TableHead className="text-right">24h最低</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tickers.map((ticker) => {
              const isPositive = (ticker.change_percentage_24h || 0) >= 0
              return (
                <TableRow key={ticker.symbol}>
                  <TableCell className="font-medium">
                    {formatSymbol(ticker.symbol)}
                  </TableCell>
                  <TableCell className="text-right font-semibold">
                    ${ticker.last.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className={`flex items-center justify-end gap-1 ${
                      isPositive ? 'text-profit' : 'text-loss'
                    }`}>
                      {isPositive ? (
                        <TrendingUp className="h-3 w-3" />
                      ) : (
                        <TrendingDown className="h-3 w-3" />
                      )}
                      <span>
                        {isPositive ? '+' : ''}
                        ${Math.abs(ticker.change_24h || 0).toFixed(2)}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge
                      variant={isPositive ? "default" : "destructive"}
                      className={isPositive
                        ? "bg-profit hover:bg-green-700 dark:hover:bg-green-600 text-white border-0"
                        : "bg-loss hover:bg-red-700 dark:hover:bg-red-600 text-white border-0"
                      }
                    >
                      {isPositive ? '+' : ''}
                      {(ticker.change_percentage_24h || 0).toFixed(2)}%
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    ${ticker.high.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    ${ticker.low.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
