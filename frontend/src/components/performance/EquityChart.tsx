"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts"
import { format } from "date-fns"
import { zhCN } from "date-fns/locale"
import type { EquityPoint } from "@/lib/api/performance"

interface EquityChartProps {
  data: EquityPoint[] | undefined
  isLoading: boolean
}

export function EquityChart({ data, isLoading }: EquityChartProps) {
  if (isLoading) {
    return (
      <Card className="col-span-full">
        <CardHeader>
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-4 w-48 mt-2" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[400px] w-full" />
        </CardContent>
      </Card>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card className="col-span-full">
        <CardHeader>
          <CardTitle>净值曲线</CardTitle>
          <CardDescription>
            查看资产净值随时间的变化趋势
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px] flex items-center justify-center text-muted-foreground">
            暂无净值数据
          </div>
        </CardContent>
      </Card>
    )
  }

  // 格式化数据用于图表显示
  // 按日期分组数据
  const groupedByDay = new Map<string, EquityPoint[]>()

  data.forEach(point => {
    const dayKey = format(new Date(point.timestamp), "yyyy-MM-dd")
    if (!groupedByDay.has(dayKey)) {
      groupedByDay.set(dayKey, [])
    }
    groupedByDay.get(dayKey)!.push(point)
  })

  // 检查数据是否都在同一天
  const isSameDay = groupedByDay.size === 1

  // 根据是否同一天选择不同的展示策略
  let chartData: { timestamp: string; value: number }[] = []

  if (isSameDay) {
    // 单天数据：显示所有时间点
    chartData = data.map((point) => {
      const date = new Date(point.timestamp)
      return {
        timestamp: format(date, "HH:mm"),
        value: point.value,
      }
    })
  } else {
    // 多天数据：每天取收盘价
    groupedByDay.forEach((points) => {
      const sortedPoints = points.sort((a, b) =>
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )

      // 取每天的最后一个点
      const closePoint = sortedPoints[sortedPoints.length - 1]
      const closeDate = new Date(closePoint.timestamp)
      chartData.push({
        timestamp: format(closeDate, "MM/dd"),  // 只显示日期
        value: closePoint.value,
      })
    })

    // 按时间排序
    chartData.sort((a, b) => {
      const aDate = new Date(a.timestamp)
      const bDate = new Date(b.timestamp)
      return aDate.getTime() - bDate.getTime()
    })
  }

  // 计算统计信息
  const firstValue = data[0].value
  const lastValue = data[data.length - 1].value
  const totalReturn = lastValue - firstValue
  const totalReturnPercentage = ((totalReturn / firstValue) * 100).toFixed(2)
  const isPositive = totalReturn >= 0

  return (
    <Card className="col-span-full">
      <CardHeader>
        <CardTitle>净值曲线</CardTitle>
        <CardDescription>
          期间收益: <span className={isPositive ? "text-profit font-semibold" : "text-loss font-semibold"}>
            ${totalReturn.toFixed(2)} ({isPositive ? '+' : ''}{totalReturnPercentage}%)
          </span>
          <span className="text-muted-foreground ml-2 text-xs">
            ({format(new Date(data[0].timestamp), "MM/dd")} - {format(new Date(data[data.length - 1].timestamp), "MM/dd")})
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={400}>
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="timestamp"
              tick={{ fontSize: 12 }}
              tickLine={false}
              className="text-muted-foreground"
              interval="preserveStartEnd"
              tickMargin={5}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              tickLine={false}
              className="text-muted-foreground"
              tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '6px',
              }}
              labelStyle={{ color: 'hsl(var(--foreground))' }}
              formatter={(value: number) => [`$${value.toFixed(2)}`, '净值']}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
