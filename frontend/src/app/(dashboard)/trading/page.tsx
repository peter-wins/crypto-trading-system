"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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
import { MarketTickerCards } from "@/components/trading/MarketTickerCards"
import { OrderBook } from "@/components/trading/OrderBook"
import { PositionList } from "@/components/portfolio/PositionList"
import { PositionDetail } from "@/components/portfolio/PositionDetail"
import { usePositions } from "@/lib/hooks/usePortfolio"
import { getClosedPositions } from "@/lib/api/history"
import { Position } from "@/types/trading"
import { portfolioAPI } from "@/lib/api"
import { useQueryClient } from "@tanstack/react-query"
import { formatCurrency } from "@/lib/utils"
import { formatSymbol } from "@/lib/utils/symbol"

export default function TradingPage() {
  // 监控的交易对
  const symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT"]

  // 持仓管理
  const { data: positions, isLoading: positionsLoading } = usePositions()
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null)
  const queryClient = useQueryClient()

  // 交易历史
  const { data: closedPositions, isLoading: historyLoading } = useQuery({
    queryKey: ["closedPositions"],
    queryFn: () => getClosedPositions({ limit: 50 }),
    refetchInterval: 30000,
  })

  const handleClosePosition = async (symbol: string) => {
    await portfolioAPI.closePosition(symbol)
    queryClient.invalidateQueries({ queryKey: ["positions"] })
    queryClient.invalidateQueries({ queryKey: ["portfolio"] })
  }

  const handleUpdateStopLoss = async (symbol: string, stopLoss: number) => {
    await portfolioAPI.updateStopLoss(symbol, stopLoss)
    queryClient.invalidateQueries({ queryKey: ["positions"] })
  }

  const handleUpdateTakeProfit = async (symbol: string, takeProfit: number) => {
    await portfolioAPI.updateTakeProfit(symbol, takeProfit)
    queryClient.invalidateQueries({ queryKey: ["positions"] })
  }

  // 格式化时间
  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString)
      return date.toLocaleString("zh-CN", {
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

  // 获取方向标签
  const getSideDisplay = (side: string) => {
    if (side === "buy") {
      return <Badge className="bg-green-600 dark:bg-green-500 text-white">做多</Badge>
    } else {
      return <Badge className="bg-red-600 dark:bg-red-500 text-white">做空</Badge>
    }
  }

  return (
    <div className="space-y-6">
      {/* 实时行情卡片 */}
      <MarketTickerCards symbols={symbols} />

      {/* Tabs: 当前持仓 / 交易历史 */}
      <Tabs defaultValue="positions" className="space-y-4">
        <TabsList>
          <TabsTrigger value="positions">当前持仓</TabsTrigger>
          <TabsTrigger value="history">交易历史</TabsTrigger>
        </TabsList>

        <TabsContent value="positions" className="space-y-4">
          <PositionList
            positions={positions || []}
            isLoading={positionsLoading}
            onPositionClick={setSelectedPosition}
          />
        </TabsContent>

        <TabsContent value="history" className="space-y-4">
          <Card>
            <CardContent className="pt-6">
              {historyLoading ? (
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
        </TabsContent>
      </Tabs>

      {/* 订单簿 */}
      <div className="grid gap-6 md:grid-cols-2">
        <OrderBook symbol="BTCUSDT" limit={10} />
        <OrderBook symbol="ETHUSDT" limit={10} />
      </div>

      {/* 持仓详情弹窗 */}
      <PositionDetail
        position={selectedPosition}
        open={!!selectedPosition}
        onClose={() => setSelectedPosition(null)}
        onClosePosition={handleClosePosition}
        onUpdateStopLoss={handleUpdateStopLoss}
        onUpdateTakeProfit={handleUpdateTakeProfit}
      />
    </div>
  )
}
