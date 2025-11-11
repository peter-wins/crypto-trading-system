"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { TrendingUp, TrendingDown, Activity, Target, Award, BarChart3 } from "lucide-react"
import type { PerformanceMetrics } from "@/lib/api/performance"

interface MetricsCardProps {
  metrics: PerformanceMetrics | undefined
  isLoading: boolean
}

export function MetricsCard({ metrics, isLoading }: MetricsCardProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[...Array(6)].map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-24 mb-2" />
              <Skeleton className="h-3 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  if (!metrics) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        暂无绩效数据
      </div>
    )
  }

  const metricCards = [
    {
      title: "累计总收益",
      value: `$${metrics.total_return.toFixed(2)}`,
      description: `累计收益率 ${metrics.total_return_percentage.toFixed(2)}%`,
      icon: metrics.total_return >= 0 ? TrendingUp : TrendingDown,
      color: metrics.total_return >= 0 ? "text-profit" : "text-loss",
    },
    {
      title: "夏普比率",
      value: metrics.sharpe_ratio.toFixed(2),
      description: metrics.sharpe_ratio > 1 ? "风险调整后收益良好" : "需要优化",
      icon: Activity,
      color: metrics.sharpe_ratio > 1 ? "text-profit" : "text-muted-foreground",
    },
    {
      title: "最大回撤",
      value: `${metrics.max_drawdown_percentage.toFixed(2)}%`,
      description: `金额 $${Math.abs(metrics.max_drawdown).toFixed(2)}`,
      icon: TrendingDown,
      color: "text-loss",
    },
    {
      title: "胜率",
      value: `${metrics.win_rate.toFixed(1)}%`,
      description: `${metrics.profitable_trades}胜 / ${metrics.losing_trades}败`,
      icon: Target,
      color: metrics.win_rate > 50 ? "text-profit" : "text-muted-foreground",
    },
    {
      title: "盈亏比",
      value: metrics.profit_factor.toFixed(2),
      description: `平均盈利 $${metrics.average_profit.toFixed(2)}`,
      icon: Award,
      color: metrics.profit_factor > 1.5 ? "text-profit" : "text-muted-foreground",
    },
    {
      title: "总交易次数",
      value: metrics.total_trades.toString(),
      description: `平均亏损 $${Math.abs(metrics.average_loss).toFixed(2)}`,
      icon: BarChart3,
      color: "text-muted-foreground",
    },
  ]

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {metricCards.map((card, index) => {
        const Icon = card.icon
        return (
          <Card key={index}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {card.title}
              </CardTitle>
              <Icon className={`h-4 w-4 ${card.color}`} />
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${card.color}`}>
                {card.value}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {card.description}
              </p>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
