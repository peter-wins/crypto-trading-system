"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn, formatCurrency, formatPercentage, isProfit } from "@/lib/utils"
import { LucideIcon } from "lucide-react"

interface StatCardProps {
  title: string
  value: string | number
  change?: number
  changeLabel?: string
  icon?: LucideIcon
  prefix?: string
  suffix?: string
  description?: string
}

export function StatCard({
  title,
  value,
  change,
  changeLabel = "较昨日",
  icon: Icon,
  prefix = "",
  suffix = "",
  description,
}: StatCardProps) {
  const displayValue = typeof value === "number"
    ? `${prefix}${formatCurrency(value)}${suffix}`
    : value

  const hasChange = typeof change === "number"
  const isProfitable = hasChange && isProfit(change)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {Icon && (
          <Icon className="h-4 w-4 text-muted-foreground" />
        )}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{displayValue}</div>
        {hasChange && (
          <p className={cn(
            "text-xs mt-1",
            isProfitable ? "text-profit" : "text-loss"
          )}>
            <span className="font-medium">
              {formatPercentage(change!)}
            </span>
            {" "}
            <span className="text-muted-foreground">{changeLabel}</span>
          </p>
        )}
        {description && (
          <p className="text-xs text-muted-foreground mt-1">
            {description}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
