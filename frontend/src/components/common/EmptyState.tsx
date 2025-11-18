"use client"

import { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}

/**
 * 通用空状态组件
 * 用于显示无数据、无结果等空状态场景
 *
 * @example
 * <EmptyState
 *   icon={Package}
 *   title="暂无持仓"
 *   description="系统将自动分析市场并开仓"
 * />
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center h-64 gap-4 py-8",
        className
      )}
    >
      {Icon && (
        <Icon className="h-12 w-12 text-muted-foreground/30" strokeWidth={1.5} />
      )}
      <div className="text-center space-y-1 max-w-sm">
        <p className="font-medium text-muted-foreground">{title}</p>
        {description && (
          <p className="text-sm text-muted-foreground/60">{description}</p>
        )}
      </div>
      {action}
    </div>
  )
}
