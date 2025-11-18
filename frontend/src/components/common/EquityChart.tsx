"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { formatCurrency } from "@/lib/utils"
import { format } from "date-fns"
import { memo } from "react"

interface EquityPoint {
  timestamp: string
  value: number
}

interface EquityChartProps {
  data: EquityPoint[] | undefined
  isLoading?: boolean
  title?: string
  description?: string
  height?: number
  className?: string
  showLegend?: boolean
}

/**
 * 统一的净值曲线组件
 * 支持单天和多天数据的智能展示
 */
export const EquityChart = memo(function EquityChart({
  data,
  isLoading = false,
  title = "净值曲线",
  description = "查看资产净值随时间的变化趋势",
  height = 300,
  className = "col-span-4",
  showLegend = false,
}: EquityChartProps) {
  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-4 w-48 mt-2" />
        </CardHeader>
        <CardContent>
          <Skeleton className={`h-[${height}px] w-full`} />
        </CardContent>
      </Card>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent>
          <div className={`flex items-center justify-center h-[${height}px]`}>
            <p className="text-muted-foreground">暂无数据</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  // 转换数据格式 - 按日期分组数据
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
  let chartData: { date: string; value: number; fullDate: string }[] = []

  if (isSameDay) {
    // 单天数据：显示所有时间点
    chartData = data.map((point) => {
      const date = new Date(point.timestamp)
      return {
        date: format(date, "HH:mm"),
        value: point.value,
        fullDate: date.toISOString(),
      }
    })
  } else {
    // 多天数据：第一天取开盘价（可能是初始资金），其他天取收盘价
    const sortedDays = Array.from(groupedByDay.entries()).sort((a, b) => {
      return new Date(a[0]).getTime() - new Date(b[0]).getTime()
    })

    sortedDays.forEach(([dayKey, points], index) => {
      const sortedPoints = points.sort((a, b) =>
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )

      // 第一天取第一个点（可能是初始资金），其他天取最后一个点（收盘价）
      const point = index === 0 ? sortedPoints[0] : sortedPoints[sortedPoints.length - 1]
      const pointDate = new Date(point.timestamp)
      chartData.push({
        date: format(pointDate, "MM/dd"),
        value: point.value,
        fullDate: pointDate.toISOString(),
      })
    })
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="date"
              className="text-xs"
              tick={{ fill: "currentColor" }}
              interval="preserveStartEnd"
              tickMargin={5}
            />
            <YAxis
              className="text-xs"
              tick={{ fill: "currentColor" }}
              tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "0.5rem",
              }}
              labelStyle={{ color: "hsl(var(--foreground))" }}
              formatter={(value: number) => [formatCurrency(value), "净值"]}
            />
            {showLegend && <Legend />}
            <Line
              type="monotone"
              dataKey="value"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              name="账户净值"
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
})
