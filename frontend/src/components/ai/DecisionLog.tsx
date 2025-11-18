"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { formatDistanceToNow } from "date-fns"
import { zhCN } from "date-fns/locale"
import { Brain } from "lucide-react"
import { cn } from "@/lib/utils"
import { DecisionRecord } from "@/types/decision"
import { getSignalLabel, getSignalColor } from "@/lib/utils/signal"
import { formatSymbol } from "@/lib/utils/symbol"

interface DecisionLogProps {
  decisions: DecisionRecord[]
  isLoading?: boolean
  limit?: number
}

export function DecisionLog({ decisions, isLoading, limit = 5 }: DecisionLogProps) {
  if (isLoading) {
    return (
      <Card className="col-span-3">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            最近决策
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[300px]">
            <p className="text-muted-foreground">加载中...</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const displayDecisions = decisions?.slice(0, limit) || []

  if (displayDecisions.length === 0) {
    return (
      <Card className="col-span-3">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            最近决策
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[300px]">
            <p className="text-muted-foreground">暂无决策记录</p>
          </div>
        </CardContent>
      </Card>
    )
  }


  return (
    <Card className="col-span-3">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5" />
          最近决策
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {displayDecisions.map((decision, index) => (
            <div
              key={decision.id}
              className={cn(
                "border-l-2 pl-4 py-2",
                decision.decision_type === "STRATEGIC"
                  ? "border-primary"
                  : "border-muted"
              )}
            >
              {/* 决策头部 */}
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Badge
                    variant={
                      decision.decision_type === "STRATEGIC"
                        ? "default"
                        : "outline"
                    }
                  >
                    {decision.decision_type === "STRATEGIC" ? "战略" : "战术"}
                  </Badge>
                  {decision.symbol && (
                    <span className="text-sm font-medium">
                      {formatSymbol(decision.symbol)}
                    </span>
                  )}
                  {decision.signal && (
                    <Badge className={getSignalColor(decision.signal)}>
                      {getSignalLabel(decision.signal)}
                    </Badge>
                  )}
                </div>
              </div>

              {/* 决策推理 */}
              <p className="text-sm text-muted-foreground mb-2">
                {decision.reasoning}
              </p>

              {/* 决策底部信息 */}
              <div className="flex items-center justify-between text-xs">
                <span className={
                  decision.confidence >= 0.8
                    ? "text-profit font-medium"
                    : decision.confidence >= 0.6
                    ? "text-yellow-600 dark:text-yellow-400 font-medium"
                    : "text-orange-600 dark:text-orange-400 font-medium"
                }>
                  置信度: {(decision.confidence * 100).toFixed(0)}%
                </span>
                <span className="text-muted-foreground">
                  {formatDistanceToNow(new Date(decision.timestamp), {
                    addSuffix: true,
                    locale: zhCN,
                  })}
                </span>
              </div>
            </div>
          ))}
        </div>

        {decisions && decisions.length > limit && (
          <div className="mt-4 text-center">
            <a
              href="/history"
              className="text-sm text-primary hover:underline"
            >
              查看全部 {decisions.length} 条决策 →
            </a>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
