"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { getClosedPositions } from "@/lib/api/history"
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
import { Skeleton } from "@/components/ui/skeleton"
import { formatCurrency } from "@/lib/utils"
import { formatSymbol } from "@/lib/utils/symbol"
import { formatDistanceToNow } from "date-fns"
import { zhCN } from "date-fns/locale"

export default function TradesPage() {
  const { data: closedPositions, isLoading } = useQuery({
    queryKey: ["closedPositions"],
    queryFn: () => getClosedPositions({ limit: 100 }),
    refetchInterval: 30000, // 30秒刷新一次
  })

  // 格式化时间
  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString)
      return date.toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    } catch {
      return isoString
    }
  }

  // 获取盈亏颜色
  const getPnlColor = (pnl: number) => {
    if (pnl > 0) return "text-green-600 dark:text-green-400"
    if (pnl < 0) return "text-red-600 dark:text-red-400"
    return "text-muted-foreground"
  }

  // 获取方向标签和颜色
  const getSideDisplay = (side: string) => {
    if (side === "buy") {
      return (
        <Badge className="bg-green-600 dark:bg-green-500 text-white">
          做多
        </Badge>
      )
    } else {
      return (
        <Badge className="bg-red-600 dark:bg-red-500 text-white">做空</Badge>
      )
    }
  }

  // 计算统计数据
  const stats = {
    totalTrades: closedPositions?.length || 0,
    profitableTrades:
      closedPositions?.filter((p) => p.realized_pnl > 0).length || 0,
    losingTrades:
      closedPositions?.filter((p) => p.realized_pnl < 0).length || 0,
    totalPnl:
      closedPositions?.reduce((sum, p) => sum + p.realized_pnl, 0) || 0,
    winRate:
      closedPositions && closedPositions.length > 0
        ? (closedPositions.filter((p) => p.realized_pnl > 0).length /
            closedPositions.length) *
          100
        : 0,
  }

  return (
    <div className="space-y-6">
      {/* 统计卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">总交易次数</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalTrades}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">盈利次数</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600 dark:text-green-400">
              {stats.profitableTrades}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">亏损次数</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600 dark:text-red-400">
              {stats.losingTrades}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">胜率</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats.winRate.toFixed(1)}%
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">总盈亏</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${getPnlColor(stats.totalPnl)}`}>
              {formatCurrency(stats.totalPnl)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 交易历史表格 */}
      <Card>
        <CardHeader>
          <CardTitle>交易记录</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(10)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : closedPositions && closedPositions.length > 0 ? (
            <div className="relative w-full overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>时间</TableHead>
                    <TableHead>交易对</TableHead>
                    <TableHead>方向</TableHead>
                    <TableHead className="text-right">入场价</TableHead>
                    <TableHead className="text-right">出场价</TableHead>
                    <TableHead className="text-right">数量</TableHead>
                    <TableHead className="text-right">盈亏</TableHead>
                    <TableHead>持仓时长</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {closedPositions.map((position) => (
                    <TableRow key={position.id}>
                      <TableCell className="whitespace-nowrap">
                        {formatTime(position.exit_time)}
                      </TableCell>
                      <TableCell className="font-medium">
                        {formatSymbol(position.symbol)}
                      </TableCell>
                      <TableCell>{getSideDisplay(position.side)}</TableCell>
                      <TableCell className="text-right">
                        {formatCurrency(position.entry_price)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatCurrency(position.exit_price)}
                      </TableCell>
                      <TableCell className="text-right">
                        {position.amount.toFixed(4)}
                      </TableCell>
                      <TableCell
                        className={`text-right font-medium ${getPnlColor(position.realized_pnl)}`}
                      >
                        <div>{formatCurrency(position.realized_pnl)}</div>
                        <div className="text-xs">
                          {position.realized_pnl_percentage > 0 ? "+" : ""}
                          {position.realized_pnl_percentage.toFixed(2)}%
                        </div>
                      </TableCell>
                      <TableCell>
                        {position.holding_duration_display || "-"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              暂无交易记录
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
