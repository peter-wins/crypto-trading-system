"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { cn, formatCurrency, formatPercentage, isProfit } from "@/lib/utils"
import { formatSymbol } from "@/lib/utils/symbol"
import { TrendingUp, TrendingDown } from "lucide-react"
import { Position } from "@/types/trading"

interface PositionListProps {
  positions: Position[]
  isLoading?: boolean
  onPositionClick?: (position: Position) => void
}

export function PositionList({ positions, isLoading, onPositionClick }: PositionListProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>持仓列表</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-40">
            <p className="text-muted-foreground">加载中...</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!positions || positions.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>持仓列表</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-40">
            <p className="text-muted-foreground">暂无持仓</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>持仓列表</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>交易对</TableHead>
              <TableHead>方向</TableHead>
              <TableHead className="text-right">数量</TableHead>
              <TableHead className="text-right">入场价</TableHead>
              <TableHead className="text-right">当前价</TableHead>
              <TableHead className="text-right">持仓价值</TableHead>
              <TableHead className="text-right">未实现盈亏</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {positions.map((position) => {
              const isProfitable = isProfit(position.unrealized_pnl)
              const TrendIcon = isProfitable ? TrendingUp : TrendingDown

              return (
                <TableRow
                  key={position.symbol}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => onPositionClick?.(position)}
                >
                  <TableCell className="font-medium">
                    {formatSymbol(position.symbol)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={position.side === "BUY" ? "success" : "destructive"}
                    >
                      {position.side === "BUY" ? "做多" : "做空"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {position.amount.toFixed(4)}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatCurrency(position.entry_price)}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatCurrency(position.current_price)}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatCurrency(position.value)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <TrendIcon
                        className={cn(
                          "h-4 w-4",
                          isProfitable ? "text-profit" : "text-loss"
                        )}
                      />
                      <span
                        className={cn(
                          "font-medium",
                          isProfitable ? "text-profit" : "text-loss"
                        )}
                      >
                        {formatCurrency(position.unrealized_pnl)}
                      </span>
                      <span
                        className={cn(
                          "text-xs ml-1",
                          isProfitable ? "text-profit" : "text-loss"
                        )}
                      >
                        ({formatPercentage(position.unrealized_pnl_percentage)})
                      </span>
                    </div>
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
