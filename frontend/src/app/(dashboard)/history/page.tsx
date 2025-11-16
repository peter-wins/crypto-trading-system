"use client"

import { useState, useMemo } from "react"
import { useDecisionHistory } from "@/lib/hooks/useDecisions"
import { DecisionHistory } from "@/components/ai/DecisionHistory"
import { DecisionDetailDialog } from "@/components/ai/DecisionDetailDialog"
import { DecisionRecord } from "@/types/decision"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { getSignalLabel } from "@/lib/utils/signal"

export default function HistoryPage() {
  const { data: decisions, isLoading, error } = useDecisionHistory(10000)
  const [selectedDecision, setSelectedDecision] = useState<DecisionRecord | null>(null)
  const [searchTerm, setSearchTerm] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [actionFilter, setActionFilter] = useState<string>("all")
  const [executedFilter, setExecutedFilter] = useState<string>("all")
  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 20

  // 筛选决策
  const filteredDecisions = useMemo(() => {
    if (!decisions) return []

    return decisions.filter((decision) => {
      // 搜索过滤
      if (searchTerm) {
        const search = searchTerm.toLowerCase()
        const matchesSearch =
          decision.reasoning.toLowerCase().includes(search) ||
          decision.symbol?.toLowerCase().includes(search) ||
          decision.signal?.toLowerCase().includes(search)
        if (!matchesSearch) return false
      }

      // 类型过滤
      if (typeFilter !== "all" && decision.decision_type !== typeFilter) {
        return false
      }

      // 操作过滤
      if (actionFilter !== "all") {
        if (actionFilter === "none" && decision.signal) return false
        if (actionFilter !== "none" && decision.signal !== actionFilter) return false
      }

      // 执行状态过滤
      if (executedFilter !== "all") {
        const isExecuted = decision.outcome === "executed"
        if (executedFilter === "executed" && !isExecuted) return false
        if (executedFilter === "not_executed" && isExecuted) return false
      }

      return true
    })
  }, [decisions, searchTerm, typeFilter, actionFilter, executedFilter])

  // 获取所有唯一的信号类型
  const signalTypes = useMemo(() => {
    if (!decisions) return []
    const signals = new Set(
      decisions.map((d) => d.signal).filter((s): s is NonNullable<typeof s> => !!s)
    )
    return Array.from(signals)
  }, [decisions])

  // 分页逻辑
  const totalPages = Math.ceil(filteredDecisions.length / itemsPerPage)
  const paginatedDecisions = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage
    const endIndex = startIndex + itemsPerPage
    return filteredDecisions.slice(startIndex, endIndex)
  }, [filteredDecisions, currentPage, itemsPerPage])

  // 当筛选条件改变时，重置到第一页
  useMemo(() => {
    setCurrentPage(1)
  }, [searchTerm, typeFilter, actionFilter, executedFilter])

  return (
    <div className="space-y-6">
      {/* 筛选器 */}
      <Card>
        <CardHeader>
          <CardTitle>筛选器</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            {/* 搜索 */}
            <div className="space-y-2">
              <Label htmlFor="search">搜索</Label>
              <Input
                id="search"
                placeholder="搜索理由、交易对或操作..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>

            {/* 决策类型 */}
            <div className="space-y-2">
              <Label htmlFor="type">决策类型</Label>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger id="type">
                  <SelectValue placeholder="选择类型" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="STRATEGIC">战略</SelectItem>
                  <SelectItem value="TACTICAL">战术</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* 信号类型 */}
            <div className="space-y-2">
              <Label htmlFor="action">信号</Label>
              <Select value={actionFilter} onValueChange={setActionFilter}>
                <SelectTrigger id="action">
                  <SelectValue placeholder="选择信号" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="none">无信号</SelectItem>
                  {signalTypes.map((signal) => (
                    <SelectItem key={signal} value={signal}>
                      {getSignalLabel(signal)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* 执行状态 */}
            <div className="space-y-2">
              <Label htmlFor="executed">执行状态</Label>
              <Select value={executedFilter} onValueChange={setExecutedFilter}>
                <SelectTrigger id="executed">
                  <SelectValue placeholder="选择状态" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="executed">已执行</SelectItem>
                  <SelectItem value="not_executed">未执行</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* 统计 */}
            <div className="space-y-2">
              <Label>统计</Label>
              <div className="flex items-center gap-2 h-10">
                <Badge variant="secondary">
                  {filteredDecisions.length} / {decisions?.length || 0}
                </Badge>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 决策列表 */}
      <DecisionHistory
        decisions={paginatedDecisions}
        isLoading={isLoading}
        onDecisionClick={setSelectedDecision}
      />

      {/* 分页控件 */}
      {totalPages > 1 && (
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div className="text-sm text-muted-foreground">
                显示 {(currentPage - 1) * itemsPerPage + 1} - {Math.min(currentPage * itemsPerPage, filteredDecisions.length)} 条，
                共 {filteredDecisions.length} 条
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                >
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  上一页
                </Button>

                <div className="flex items-center gap-1">
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    // 显示当前页附近的页码
                    let pageNum
                    if (totalPages <= 5) {
                      pageNum = i + 1
                    } else if (currentPage <= 3) {
                      pageNum = i + 1
                    } else if (currentPage >= totalPages - 2) {
                      pageNum = totalPages - 4 + i
                    } else {
                      pageNum = currentPage - 2 + i
                    }

                    return (
                      <Button
                        key={pageNum}
                        variant={currentPage === pageNum ? "default" : "outline"}
                        size="sm"
                        onClick={() => setCurrentPage(pageNum)}
                        className="w-10"
                      >
                        {pageNum}
                      </Button>
                    )
                  })}
                </div>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                >
                  下一页
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 决策详情弹窗 */}
      <DecisionDetailDialog
        decision={selectedDecision}
        open={!!selectedDecision}
        onClose={() => setSelectedDecision(null)}
      />
    </div>
  )
}
