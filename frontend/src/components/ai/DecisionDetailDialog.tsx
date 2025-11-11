"use client"

import { DecisionRecord } from "@/types/decision"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { format } from "date-fns"
import { zhCN } from "date-fns/locale"
import { getSignalLabel, getSignalColor } from "@/lib/utils/signal"
import { formatSymbol } from "@/lib/utils/symbol"

interface DecisionDetailDialogProps {
  decision: DecisionRecord | null
  open: boolean
  onClose: () => void
}

export function DecisionDetailDialog({
  decision,
  open,
  onClose,
}: DecisionDetailDialogProps) {
  if (!decision) return null

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            决策详情
            <Badge variant={decision.decision_type === "STRATEGIC" ? "default" : "outline"}>
              {decision.decision_type === "STRATEGIC" ? "战略" : "战术"}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            {format(new Date(decision.timestamp), "PPpp", { locale: zhCN })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 基本信息 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">决策信息</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-8 mb-4">
                <div>
                  <p className="text-sm text-muted-foreground mb-1">交易对</p>
                  <p className="font-medium">{decision.symbol ? formatSymbol(decision.symbol) : "全局"}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground mb-1">置信度</p>
                  <p className="font-medium">{(decision.confidence * 100).toFixed(0)}%</p>
                </div>
                {decision.signal ? (
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">信号</p>
                    <Badge className={getSignalColor(decision.signal)}>
                      {getSignalLabel(decision.signal)}
                    </Badge>
                  </div>
                ) : (
                  <div></div>
                )}
              </div>
              {decision.model_used && (
                <div className="pt-4 border-t">
                  <p className="text-sm text-muted-foreground mb-1">使用模型</p>
                  <p className="font-medium text-sm font-mono">{decision.model_used}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 决策理由 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">决策理由</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm whitespace-pre-wrap">{decision.reasoning}</p>
            </CardContent>
          </Card>

          {/* 上下文信息 */}
          {decision.context && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">上下文信息</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="text-xs overflow-x-auto bg-muted p-4 rounded-lg">
                  <code>{JSON.stringify(decision.context, null, 2)}</code>
                </pre>
              </CardContent>
            </Card>
          )}

          {/* 工具调用 */}
          {decision.tool_calls && decision.tool_calls.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">工具调用</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {decision.tool_calls.map((tool, idx) => (
                    <div key={idx} className="border-l-2 pl-3">
                      <p className="text-sm font-medium">{tool.name}</p>
                      <p className="text-xs text-muted-foreground">
                        参数: {JSON.stringify(tool.arguments)}
                      </p>
                      {tool.result && (
                        <p className="text-xs text-muted-foreground">
                          结果: {JSON.stringify(tool.result)}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* 执行状态 */}
          {decision.outcome && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">执行状态</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <Badge variant={decision.outcome === "executed" ? "default" : "secondary"}>
                    {decision.outcome === "executed" ? "已执行" : "待执行"}
                  </Badge>
                  <p className="text-sm text-muted-foreground">
                    {decision.outcome}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
