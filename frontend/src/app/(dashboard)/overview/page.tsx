"use client"

import { StatCard } from "@/components/ui/stat-card"
import { PositionList } from "@/components/portfolio/PositionList"
import { EquityChart } from "@/components/charts/EquityChart"
import { DecisionLog } from "@/components/ai/DecisionLog"
import { usePortfolio, usePositions, useEquityCurve } from "@/lib/hooks/usePortfolio"
import { useDecisionHistory } from "@/lib/hooks/useDecisions"
import { Wallet, TrendingUp, Percent, Package } from "lucide-react"

export default function OverviewPage() {
  // 获取数据
  const { data: portfolio, isLoading: portfolioLoading } = usePortfolio()
  const { data: positions, isLoading: positionsLoading } = usePositions()
  const { data: equityCurve, isLoading: equityLoading } = useEquityCurve()
  const { data: decisions, isLoading: decisionsLoading } = useDecisionHistory(10)

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-8">
      {/* 统计卡片网格 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="钱包余额"
          value={portfolio?.wallet_balance || 0}
          change={portfolio?.daily_pnl_percentage}
          changeLabel="较昨日"
          icon={Wallet}
        />
        <StatCard
          title="未实现盈亏"
          value={portfolio?.unrealized_pnl || 0}
          change={portfolio?.unrealized_pnl_percentage}
          changeLabel="收益率"
          icon={TrendingUp}
        />
        <StatCard
          title="可用保证金"
          value={portfolio?.available_balance || 0}
          icon={Percent}
        />
        <StatCard
          title="持仓数量"
          value={`${positions?.length || 0}`}
          description={`保证金占用 ${portfolio?.margin_balance?.toFixed(0) || 0} USDT`}
          icon={Package}
        />
      </div>

      {/* 图表区域 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        {/* 净值曲线 */}
        <EquityChart
          data={equityCurve || []}
          isLoading={equityLoading}
        />

        {/* 决策日志 */}
        <DecisionLog
          decisions={decisions || []}
          isLoading={decisionsLoading}
          limit={5}
        />
      </div>

      {/* 持仓列表 */}
      <PositionList
        positions={positions || []}
        isLoading={positionsLoading}
      />
    </div>
  )
}
