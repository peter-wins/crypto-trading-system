"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Cell } from "recharts"
import type { TradesStats } from "@/lib/api/performance"

interface TradesAnalysisProps {
  stats: TradesStats | undefined
  isLoading: boolean
}

export function TradesAnalysis({ stats, isLoading }: TradesAnalysisProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-4 w-48 mt-2" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-[300px] w-full" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-4 w-48 mt-2" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-[300px] w-full" />
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>盈亏分布</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] flex items-center justify-center text-muted-foreground">
              暂无数据
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>持仓时长</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] flex items-center justify-center text-muted-foreground">
              暂无数据
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // 格式化盈亏分布数据
  const profitData = Object.entries(stats.profit_distribution).map(([range, count]) => ({
    range,
    count,
    isProfit: !range.startsWith('-'),
  }))

  // 格式化持仓时长数据
  const holdingData = Object.entries(stats.holding_period).map(([period, count]) => ({
    period,
    count,
  }))

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* 盈亏分布图 */}
      <Card>
        <CardHeader>
          <CardTitle>盈亏分布</CardTitle>
          <CardDescription>
            不同盈亏区间的交易次数分布
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={profitData}
              margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="range"
                tick={{ fontSize: 11 }}
                tickLine={false}
                className="text-muted-foreground"
              />
              <YAxis
                tick={{ fontSize: 12 }}
                tickLine={false}
                className="text-muted-foreground"
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px',
                }}
                labelStyle={{ color: 'hsl(var(--foreground))' }}
                formatter={(value: number) => [value, '交易次数']}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {profitData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.isProfit ? 'hsl(var(--profit))' : 'hsl(var(--loss))'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* 持仓时长分布图 */}
      <Card>
        <CardHeader>
          <CardTitle>持仓时长分布</CardTitle>
          <CardDescription>
            不同持仓时长的交易次数分布
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={holdingData}
              margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="period"
                tick={{ fontSize: 11 }}
                tickLine={false}
                className="text-muted-foreground"
              />
              <YAxis
                tick={{ fontSize: 12 }}
                tickLine={false}
                className="text-muted-foreground"
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px',
                }}
                labelStyle={{ color: 'hsl(var(--foreground))' }}
                formatter={(value: number) => [value, '交易次数']}
              />
              <Bar
                dataKey="count"
                fill="hsl(var(--primary))"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  )
}
