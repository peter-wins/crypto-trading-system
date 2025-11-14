"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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

interface EquityPoint {
  timestamp: string
  value: number
}

interface EquityChartProps {
  data: EquityPoint[]
  isLoading?: boolean
}

export function EquityChart({ data, isLoading }: EquityChartProps) {
  if (isLoading) {
    return (
      <Card className="col-span-4">
        <CardHeader>
          <CardTitle>净值曲线</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[300px]">
            <p className="text-muted-foreground">加载中...</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card className="col-span-4">
        <CardHeader>
          <CardTitle>净值曲线</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[300px]">
            <p className="text-muted-foreground">暂无数据</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  // 转换数据格式
  // 按日期分组数据，每天只保留几个关键点
  const groupedByDay = new Map<string, EquityPoint[]>()

  data.forEach(point => {
    const dayKey = format(new Date(point.timestamp), "yyyy-MM-dd")
    if (!groupedByDay.has(dayKey)) {
      groupedByDay.set(dayKey, [])
    }
    groupedByDay.get(dayKey)!.push(point)
  })

  console.log('Equity data grouped by day:', {
    totalPoints: data.length,
    uniqueDays: groupedByDay.size,
    days: Array.from(groupedByDay.keys()),
    pointsPerDay: Array.from(groupedByDay.entries()).map(([day, points]) => ({
      day,
      count: points.length
    }))
  })

  // 检查数据是否都在同一天
  const isSameDay = groupedByDay.size === 1

  // 如果是多天数据，每天采样几个点；如果是单天数据，显示所有点
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
    <Card className="col-span-4">
      <CardHeader>
        <CardTitle>净值曲线</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
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
            <Legend />
            <Line
              type="monotone"
              dataKey="value"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              dot={false}
              name="账户净值"
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
