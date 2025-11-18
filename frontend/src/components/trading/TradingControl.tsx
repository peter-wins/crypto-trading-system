"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Play, Pause, RefreshCw, AlertCircle } from "lucide-react"

export function TradingControl() {
  const [isRunning, setIsRunning] = useState(true)
  const [isLoading, setIsLoading] = useState(false)

  const handleToggle = async () => {
    setIsLoading(true)
    // TODO: 调用API暂停/恢复AI交易
    await new Promise(resolve => setTimeout(resolve, 500))
    setIsRunning(!isRunning)
    setIsLoading(false)
  }

  const handleRestart = async () => {
    setIsLoading(true)
    // TODO: 调用API重启AI交易系统
    await new Promise(resolve => setTimeout(resolve, 1000))
    setIsRunning(true)
    setIsLoading(false)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>AI交易控制</CardTitle>
            <CardDescription>管理AI自主交易系统状态</CardDescription>
          </div>
          <Badge
            variant={isRunning ? "default" : "secondary"}
            className={isRunning
              ? "bg-profit hover:bg-green-700 dark:hover:bg-green-600 text-white border-0"
              : "bg-gray-400 dark:bg-gray-600 text-white border-0"
            }
          >
            {isRunning ? "运行中" : "已暂停"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 系统状态 */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">决策引擎</div>
            <div className="flex items-center gap-2">
              <div className={`h-2 w-2 rounded-full ${isRunning ? 'bg-green-500 dark:bg-green-400 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-gray-300 dark:bg-gray-600'}`} />
              <span className="text-sm font-medium">
                {isRunning ? "正常运行" : "已停止"}
              </span>
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">数据采集</div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-green-500 dark:bg-green-400 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]" />
              <span className="text-sm font-medium">正常运行</span>
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">风险控制</div>
            <div className="flex items-center gap-2">
              <div className={`h-2 w-2 rounded-full ${isRunning ? 'bg-green-500 dark:bg-green-400 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-gray-300 dark:bg-gray-600'}`} />
              <span className="text-sm font-medium">
                {isRunning ? "监控中" : "已停止"}
              </span>
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-sm text-muted-foreground">订单执行</div>
            <div className="flex items-center gap-2">
              <div className={`h-2 w-2 rounded-full ${isRunning ? 'bg-green-500 dark:bg-green-400 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-gray-300 dark:bg-gray-600'}`} />
              <span className="text-sm font-medium">
                {isRunning ? "就绪" : "已停止"}
              </span>
            </div>
          </div>
        </div>

        {/* 控制按钮 */}
        <div className="flex gap-2 pt-2">
          <Button
            onClick={handleToggle}
            disabled={isLoading}
            variant={isRunning ? "destructive" : "default"}
            className="flex-1"
          >
            {isLoading ? (
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
            ) : isRunning ? (
              <Pause className="h-4 w-4 mr-2" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            {isRunning ? "暂停交易" : "开始交易"}
          </Button>

          <Button
            onClick={handleRestart}
            disabled={isLoading}
            variant="outline"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            重启系统
          </Button>
        </div>

        {/* 警告信息 */}
        {!isRunning && (
          <div className="flex items-start gap-2 p-3 bg-warning/10 border border-warning/20 rounded-lg">
            <AlertCircle className="h-4 w-4 text-warning mt-0.5" />
            <div className="flex-1 text-sm">
              <div className="font-medium text-warning">AI交易已暂停</div>
              <div className="text-muted-foreground mt-1">
                系统将不会执行任何新的交易决策，但会继续监控市场和持仓。
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
