"use client"

import { useState } from "react"
import { MetricsCard } from "@/components/performance/MetricsCard"
import { EquityChart } from "@/components/common/EquityChart"
import { TradesAnalysis } from "@/components/performance/TradesAnalysis"
import { TimeRangeSelector, TimeRange, TimeRangeValue } from "@/components/performance/TimeRangeSelector"
import { usePerformanceMetrics, useEquityCurve, useTradesStats } from "@/lib/hooks/usePerformance"

export default function PerformancePage() {
  // 时间范围状态 - 默认显示全部（使用 UTC 日期）
  const now = new Date()
  const utcToday = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))

  const formatUTCDate = (date: Date) =>
    `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`

  const [timeRange, setTimeRange] = useState<TimeRange>("all")
  const [dateParams, setDateParams] = useState<TimeRangeValue>({
    start_date: "2020-01-01",
    end_date: formatUTCDate(utcToday),
  })

  // 处理时间范围变化
  const handleTimeRangeChange = (range: TimeRange, dates: TimeRangeValue) => {
    setTimeRange(range)
    setDateParams(dates)
  }

  // 获取数据
  const { data: metrics, isLoading: metricsLoading } = usePerformanceMetrics(dateParams)
  const { data: equityCurve, isLoading: equityLoading } = useEquityCurve(dateParams)
  const { data: tradesStats, isLoading: tradesLoading } = useTradesStats()

  return (
    <div className="space-y-6">
      {/* 时间范围选择器 */}
      <TimeRangeSelector value={timeRange} onChange={handleTimeRangeChange} />

      {/* 关键指标卡片 */}
      <MetricsCard metrics={metrics} isLoading={metricsLoading} />

      {/* 净值曲线图表 */}
      <EquityChart
        data={equityCurve}
        isLoading={equityLoading}
        height={400}
        className="col-span-full"
        description="钱包余额变化趋势"
      />

      {/* 交易分析 */}
      <TradesAnalysis stats={tradesStats} isLoading={tradesLoading} />
    </div>
  )
}
