"use client"

import { DecisionRecord } from "@/types/decision"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { format } from "date-fns"
import { zhCN } from "date-fns/locale"
import { CheckCircle2, XCircle } from "lucide-react"
import { getSignalLabel, getSignalColor } from "@/lib/utils/signal"
import { formatSymbol } from "@/lib/utils/symbol"

interface DecisionHistoryProps {
  decisions: DecisionRecord[]
  isLoading?: boolean
  onDecisionClick?: (decision: DecisionRecord) => void
}

export function DecisionHistory({
  decisions,
  isLoading,
  onDecisionClick,
}: DecisionHistoryProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>决策历史</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-40">
            <p className="text-muted-foreground">加载中...</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!decisions || decisions.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>决策历史</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-40">
            <p className="text-muted-foreground">暂无决策记录</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>决策历史</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>时间</TableHead>
              <TableHead>类型</TableHead>
              <TableHead>交易对</TableHead>
              <TableHead>操作</TableHead>
              <TableHead>理由</TableHead>
              <TableHead className="text-center">置信度</TableHead>
              <TableHead className="text-center">状态</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {decisions.map((decision) => (
              <TableRow
                key={decision.id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => onDecisionClick?.(decision)}
              >
                <TableCell className="font-medium">
                  {format(new Date(decision.timestamp), "MM-dd HH:mm", {
                    locale: zhCN,
                  })}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={
                      decision.decision_type === "STRATEGIC" ? "default" : "outline"
                    }
                  >
                    {decision.decision_type === "STRATEGIC" ? "战略" : "战术"}
                  </Badge>
                </TableCell>
                <TableCell>{decision.symbol ? formatSymbol(decision.symbol) : "-"}</TableCell>
                <TableCell>
                  {decision.signal ? (
                    <Badge className={getSignalColor(decision.signal)}>
                      {getSignalLabel(decision.signal)}
                    </Badge>
                  ) : (
                    "-"
                  )}
                </TableCell>
                <TableCell className="max-w-md truncate">
                  {decision.reasoning}
                </TableCell>
                <TableCell className="text-center">
                  {(decision.confidence * 100).toFixed(0)}%
                </TableCell>
                <TableCell className="text-center">
                  {decision.outcome === "executed" ? (
                    <CheckCircle2 className="h-5 w-5 text-profit mx-auto" />
                  ) : (
                    <XCircle className="h-5 w-5 text-muted-foreground mx-auto" />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
