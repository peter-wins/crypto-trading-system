"use client"

import { useState } from "react"
import { usePositions } from "@/lib/hooks/usePortfolio"
import { PositionList } from "@/components/portfolio/PositionList"
import { PositionDetail } from "@/components/portfolio/PositionDetail"
import { Position } from "@/types/trading"
import { portfolioAPI } from "@/lib/api"
import { useQueryClient } from "@tanstack/react-query"

export default function PositionsPage() {
  const { data: positions, isLoading } = usePositions()
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null)
  const queryClient = useQueryClient()

  const handleClosePosition = async (symbol: string) => {
    await portfolioAPI.closePosition(symbol)
    // 刷新持仓列表
    queryClient.invalidateQueries({ queryKey: ["positions"] })
    queryClient.invalidateQueries({ queryKey: ["portfolio"] })
  }

  const handleUpdateStopLoss = async (symbol: string, stopLoss: number) => {
    await portfolioAPI.updateStopLoss(symbol, stopLoss)
    // 刷新持仓列表
    queryClient.invalidateQueries({ queryKey: ["positions"] })
  }

  const handleUpdateTakeProfit = async (symbol: string, takeProfit: number) => {
    await portfolioAPI.updateTakeProfit(symbol, takeProfit)
    // 刷新持仓列表
    queryClient.invalidateQueries({ queryKey: ["positions"] })
  }

  return (
    <div className="space-y-6">
      <PositionList
        positions={positions || []}
        isLoading={isLoading}
        onPositionClick={setSelectedPosition}
      />

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
