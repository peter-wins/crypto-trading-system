"use client"

import { useState } from "react"
import { Position } from "@/types/trading"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { formatCurrency, formatPercentage } from "@/lib/utils"
import { formatSymbol } from "@/lib/utils/symbol"

interface PositionDetailProps {
  position: Position | null
  open: boolean
  onClose: () => void
  onClosePosition: (symbol: string) => Promise<void>
  onUpdateStopLoss: (symbol: string, stopLoss: number) => Promise<void>
  onUpdateTakeProfit: (symbol: string, takeProfit: number) => Promise<void>
}

export function PositionDetail({
  position,
  open,
  onClose,
  onClosePosition,
  onUpdateStopLoss,
  onUpdateTakeProfit,
}: PositionDetailProps) {
  const [stopLoss, setStopLoss] = useState("")
  const [takeProfit, setTakeProfit] = useState("")
  const [isClosing, setIsClosing] = useState(false)
  const [isUpdating, setIsUpdating] = useState(false)

  if (!position) return null

  const isProfitable = position.unrealized_pnl > 0
  const pnlPercentage = (position.unrealized_pnl / (position.entry_price * position.amount)) * 100

  const handleClose = async () => {
    setIsClosing(true)
    try {
      await onClosePosition(position.symbol)
      onClose()
    } catch (error) {
      console.error("平仓失败:", error)
    } finally {
      setIsClosing(false)
    }
  }

  const handleUpdateStopLoss = async () => {
    const value = parseFloat(stopLoss)
    if (!value || value <= 0) return

    setIsUpdating(true)
    try {
      await onUpdateStopLoss(position.symbol, value)
      setStopLoss("")
    } catch (error) {
      console.error("更新止损失败:", error)
    } finally {
      setIsUpdating(false)
    }
  }

  const handleUpdateTakeProfit = async () => {
    const value = parseFloat(takeProfit)
    if (!value || value <= 0) return

    setIsUpdating(true)
    try {
      await onUpdateTakeProfit(position.symbol, value)
      setTakeProfit("")
    } catch (error) {
      console.error("更新止盈失败:", error)
    } finally {
      setIsUpdating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {formatSymbol(position.symbol)}
            <Badge variant={position.side === "LONG" ? "default" : "destructive"}>
              {position.side === "LONG" ? "做多" : "做空"}
            </Badge>
          </DialogTitle>
          <DialogDescription>持仓详情和管理</DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* 基本信息 */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-muted-foreground">持仓数量</Label>
              <p className="text-lg font-semibold">{position.amount.toFixed(4)}</p>
            </div>
            <div>
              <Label className="text-muted-foreground">入场价格</Label>
              <p className="text-lg font-semibold">{formatCurrency(position.entry_price)}</p>
            </div>
            <div>
              <Label className="text-muted-foreground">当前价格</Label>
              <p className="text-lg font-semibold">{formatCurrency(position.current_price)}</p>
            </div>
            <div>
              <Label className="text-muted-foreground">持仓价值</Label>
              <p className="text-lg font-semibold">
                {formatCurrency(position.current_price * position.amount)}
              </p>
            </div>
          </div>

          {/* 盈亏信息 */}
          <div className="rounded-lg border p-4">
            <Label className="text-muted-foreground">未实现盈亏</Label>
            <p className={`text-2xl font-bold ${isProfitable ? "text-profit" : "text-loss"}`}>
              {formatCurrency(position.unrealized_pnl)}
            </p>
            <p className={`text-sm ${isProfitable ? "text-profit" : "text-loss"}`}>
              {formatPercentage(pnlPercentage)}
            </p>
          </div>

          {/* 止损止盈设置 */}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>当前止损</Label>
                <p className="text-sm">
                  {position.stop_loss ? formatCurrency(position.stop_loss) : "未设置"}
                </p>
              </div>
              <div className="space-y-2">
                <Label>当前止盈</Label>
                <p className="text-sm">
                  {position.take_profit ? formatCurrency(position.take_profit) : "未设置"}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="stopLoss">设置止损价格</Label>
                <div className="flex gap-2">
                  <Input
                    id="stopLoss"
                    type="number"
                    placeholder="输入止损价格"
                    value={stopLoss}
                    onChange={(e) => setStopLoss(e.target.value)}
                    disabled={isUpdating}
                  />
                  <Button
                    onClick={handleUpdateStopLoss}
                    disabled={isUpdating || !stopLoss}
                    size="sm"
                  >
                    设置
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="takeProfit">设置止盈价格</Label>
                <div className="flex gap-2">
                  <Input
                    id="takeProfit"
                    type="number"
                    placeholder="输入止盈价格"
                    value={takeProfit}
                    onChange={(e) => setTakeProfit(e.target.value)}
                    disabled={isUpdating}
                  />
                  <Button
                    onClick={handleUpdateTakeProfit}
                    disabled={isUpdating || !takeProfit}
                    size="sm"
                  >
                    设置
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
          <Button variant="destructive" onClick={handleClose} disabled={isClosing}>
            {isClosing ? "平仓中..." : "平仓"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
