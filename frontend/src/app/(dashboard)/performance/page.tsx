"use client"

import { MetricsCard } from "@/components/performance/MetricsCard"
import { EquityChart } from "@/components/performance/EquityChart"
import { TradesAnalysis } from "@/components/performance/TradesAnalysis"
import { usePerformanceMetrics, useEquityCurve, useTradesStats } from "@/lib/hooks/usePerformance"

export default function PerformancePage() {
  // 获取数据
  const { data: metrics, isLoading: metricsLoading } = usePerformanceMetrics()
  const { data: equityCurve, isLoading: equityLoading } = useEquityCurve()
  const { data: tradesStats, isLoading: tradesLoading } = useTradesStats()

  return (
    <div className="space-y-6">
      {/* 关键指标卡片 */}
      <MetricsCard metrics={metrics} isLoading={metricsLoading} />

      {/* 净值曲线图表 */}
      <EquityChart data={equityCurve} isLoading={equityLoading} />

      {/* 交易分析 */}
      <TradesAnalysis stats={tradesStats} isLoading={tradesLoading} />
    </div>
  )
}
