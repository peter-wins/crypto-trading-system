"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Shield, Brain, Settings as SettingsIcon, AlertCircle, DollarSign, CheckCircle2, XCircle } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"

export default function SettingsPage() {
  const [initialCapital, setInitialCapital] = useState("")
  const [notes, setNotes] = useState("")
  const [currentConfig, setCurrentConfig] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [fetchLoading, setFetchLoading] = useState(true)
  const [message, setMessage] = useState<{type: 'success' | 'error', text: string} | null>(null)

  // 获取当前配置
  useEffect(() => {
    fetchInitialCapital()
  }, [])

  const fetchInitialCapital = async () => {
    try {
      setFetchLoading(true)
      const response = await fetch("/api/settings/initial-capital")
      if (response.ok) {
        const data = await response.json()
        setCurrentConfig(data)
        setInitialCapital(data.initial_capital.toString())
        setNotes(data.notes || "")
      } else if (response.status === 404) {
        // 没有配置过，这是正常的
        setCurrentConfig(null)
      } else {
        throw new Error("Failed to fetch initial capital")
      }
    } catch (error) {
      console.error("Error fetching initial capital:", error)
    } finally {
      setFetchLoading(false)
    }
  }

  const handleSaveInitialCapital = async () => {
    if (!initialCapital || parseFloat(initialCapital) <= 0) {
      setMessage({ type: 'error', text: '请输入有效的初始资金金额' })
      setTimeout(() => setMessage(null), 3000)
      return
    }

    try {
      setLoading(true)
      setMessage(null)
      const response = await fetch("/api/settings/initial-capital", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          initial_capital: parseFloat(initialCapital),
          notes: notes || undefined,
        }),
      })

      if (response.ok) {
        const data = await response.json()
        setCurrentConfig(data)
        setMessage({ type: 'success', text: '初始资金配置已更新' })
        setTimeout(() => setMessage(null), 3000)
      } else {
        const error = await response.json()
        throw new Error(error.detail || "Failed to save initial capital")
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: `保存失败: ${error.message}` })
      setTimeout(() => setMessage(null), 5000)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <Tabs defaultValue="account" className="space-y-4">
        <TabsList>
          <TabsTrigger value="account" className="gap-2">
            <DollarSign className="h-4 w-4" />
            账户设置
          </TabsTrigger>
          <TabsTrigger value="risk" className="gap-2">
            <Shield className="h-4 w-4" />
            风险管理
          </TabsTrigger>
          <TabsTrigger value="ai" className="gap-2">
            <Brain className="h-4 w-4" />
            AI 模型
          </TabsTrigger>
          <TabsTrigger value="trading" className="gap-2">
            <SettingsIcon className="h-4 w-4" />
            交易设置
          </TabsTrigger>
        </TabsList>

        {/* 账户设置 */}
        <TabsContent value="account" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>初始资金配置</CardTitle>
              <CardDescription>
                设置交易系统的初始资金，用于计算累计收益率
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {message && (
                <Alert className={message.type === 'success'
                  ? "bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800"
                  : "bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800"}>
                  {message.type === 'success' ? (
                    <CheckCircle2 className="h-4 w-4 text-profit" />
                  ) : (
                    <XCircle className="h-4 w-4 text-loss" />
                  )}
                  <AlertDescription className={message.type === 'success'
                    ? "text-green-800 dark:text-green-200"
                    : "text-red-800 dark:text-red-200"}>
                    {message.text}
                  </AlertDescription>
                </Alert>
              )}

              {fetchLoading ? (
                <div className="text-sm text-muted-foreground">加载中...</div>
              ) : currentConfig ? (
                <Alert className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
                  <AlertCircle className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                  <AlertDescription className="text-blue-800 dark:text-blue-200">
                    <div className="space-y-1">
                      <div>当前配置：<span className="font-semibold">{currentConfig.initial_capital.toFixed(2)} {currentConfig.capital_currency}</span></div>
                      <div className="text-xs">设置时间：{new Date(currentConfig.set_at).toLocaleString("zh-CN", { timeZone: "Asia/Dubai" })}</div>
                      {currentConfig.notes && <div className="text-xs">备注：{currentConfig.notes}</div>}
                    </div>
                  </AlertDescription>
                </Alert>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="initial-capital">初始资金 (USDT)</Label>
                <Input
                  id="initial-capital"
                  type="number"
                  step="0.01"
                  placeholder="3610.27"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  开始交易前的账户余额，用于计算累计收益率
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="notes">备注信息（可选）</Label>
                <Input
                  id="notes"
                  placeholder="例如：2025-11-13 系统启动时的初始资金"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  记录设置原因或说明
                </p>
              </div>

              <Alert className="bg-yellow-50 dark:bg-yellow-950 border-yellow-200 dark:border-yellow-800">
                <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
                <AlertDescription className="text-yellow-800 dark:text-yellow-200">
                  <div className="space-y-2">
                    <div className="font-semibold">重要提示：</div>
                    <ul className="list-disc list-inside text-xs space-y-1">
                      <li>初始资金应该是开始自动交易前的账户实际余额</li>
                      <li>修改初始资金会立即影响所有累计收益率的计算</li>
                      <li>建议只在系统初始化时设置一次，之后不要随意修改</li>
                      <li>如果第一笔交易已经执行，需要根据第一笔交易的盈亏反推真实的初始资金</li>
                    </ul>
                  </div>
                </AlertDescription>
              </Alert>

              <div className="flex justify-end">
                <Button onClick={handleSaveInitialCapital} disabled={loading}>
                  {loading ? "保存中..." : currentConfig ? "更新配置" : "保存配置"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* 风险管理 */}
        <TabsContent value="risk" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>仓位管理</CardTitle>
              <CardDescription>
                设置单个仓位和整体风险限制
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="max-position">最大仓位比例 (%)</Label>
                  <Input
                    id="max-position"
                    type="number"
                    placeholder="20"
                    defaultValue="20"
                  />
                  <p className="text-xs text-muted-foreground">
                    单个仓位最多占总资产的百分比
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="max-daily-loss">最大日损失 (%)</Label>
                  <Input
                    id="max-daily-loss"
                    type="number"
                    placeholder="5"
                    defaultValue="5"
                  />
                  <p className="text-xs text-muted-foreground">
                    单日最大允许亏损百分比
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="max-drawdown">最大回撤 (%)</Label>
                  <Input
                    id="max-drawdown"
                    type="number"
                    placeholder="15"
                    defaultValue="15"
                  />
                  <p className="text-xs text-muted-foreground">
                    从峰值允许的最大回撤
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="stop-loss">默认止损 (%)</Label>
                  <Input
                    id="stop-loss"
                    type="number"
                    placeholder="5"
                    defaultValue="5"
                  />
                  <p className="text-xs text-muted-foreground">
                    新开仓位的默认止损比例
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>杠杆限制</CardTitle>
              <CardDescription>
                不同类型币种的杠杆倍数限制
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="leverage-mainstream">主流币最大杠杆</Label>
                  <Input
                    id="leverage-mainstream"
                    type="number"
                    placeholder="50"
                    defaultValue="50"
                  />
                  <p className="text-xs text-muted-foreground">
                    BTC/ETH 等主流币种
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="leverage-altcoin">山寨币最大杠杆</Label>
                  <Input
                    id="leverage-altcoin"
                    type="number"
                    placeholder="20"
                    defaultValue="20"
                  />
                  <p className="text-xs text-muted-foreground">
                    其他小市值币种
                  </p>
                </div>
              </div>

              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  高杠杆会放大收益也会放大风险，请谨慎使用
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>
        </TabsContent>

        {/* AI 模型设置 */}
        <TabsContent value="ai" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>模型选择</CardTitle>
              <CardDescription>
                选择用于决策的 AI 模型
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ai-provider">AI 提供商</Label>
                <Select defaultValue="deepseek">
                  <SelectTrigger id="ai-provider">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="deepseek">DeepSeek</SelectItem>
                    <SelectItem value="qwen">通义千问</SelectItem>
                    <SelectItem value="openai">OpenAI</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="model-name">模型名称</Label>
                <Input
                  id="model-name"
                  placeholder="deepseek-chat"
                  defaultValue="deepseek-chat"
                  disabled
                />
                <p className="text-xs text-muted-foreground">
                  根据提供商自动选择
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="temperature">温度 (Temperature)</Label>
                <Input
                  id="temperature"
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  placeholder="0.7"
                  defaultValue="0.7"
                />
                <p className="text-xs text-muted-foreground">
                  控制输出的随机性，0-2 之间，越高越随机
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="max-tokens">最大 Token 数</Label>
                <Input
                  id="max-tokens"
                  type="number"
                  placeholder="4000"
                  defaultValue="4000"
                />
                <p className="text-xs text-muted-foreground">
                  单次请求的最大 token 数量
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>决策配置</CardTitle>
              <CardDescription>
                AI 决策行为设置
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>战略决策</Label>
                  <p className="text-xs text-muted-foreground">
                    启用市场环境分析和战略调整
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>战术决策</Label>
                  <p className="text-xs text-muted-foreground">
                    启用具体交易信号生成
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="space-y-2">
                <Label htmlFor="min-confidence">最小置信度 (%)</Label>
                <Input
                  id="min-confidence"
                  type="number"
                  placeholder="60"
                  defaultValue="60"
                />
                <p className="text-xs text-muted-foreground">
                  只执行置信度高于此值的决策
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* 交易设置 */}
        <TabsContent value="trading" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>交易开关</CardTitle>
              <CardDescription>
                控制自动交易功能
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label className="text-base">自动交易</Label>
                  <p className="text-xs text-muted-foreground">
                    允许 AI 自动执行交易决策
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <Alert className="bg-yellow-50 dark:bg-yellow-950 border-yellow-200 dark:border-yellow-800">
                <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
                <AlertDescription className="text-yellow-800 dark:text-yellow-200">
                  关闭自动交易后，系统仍会生成决策但不会执行
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>交易模式</CardTitle>
              <CardDescription>
                选择交易策略风格
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="trading-mode">模式选择</Label>
                <Select defaultValue="balanced">
                  <SelectTrigger id="trading-mode">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="aggressive">激进模式</SelectItem>
                    <SelectItem value="balanced">平衡模式</SelectItem>
                    <SelectItem value="cautious">保守模式</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  影响仓位大小、止损止盈等参数
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="decision-interval">决策间隔 (分钟)</Label>
                <Input
                  id="decision-interval"
                  type="number"
                  placeholder="10"
                  defaultValue="10"
                />
                <p className="text-xs text-muted-foreground">
                  AI 执行决策的时间间隔
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>通知设置</CardTitle>
              <CardDescription>
                配置系统通知
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>交易通知</Label>
                  <p className="text-xs text-muted-foreground">
                    开仓/平仓时发送通知
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>风险警告</Label>
                  <p className="text-xs text-muted-foreground">
                    触发风险限制时发送警告
                  </p>
                </div>
                <Switch defaultChecked />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* 保存按钮 */}
      <div className="flex justify-end gap-4">
        <Button variant="outline">重置默认</Button>
        <Button>保存设置</Button>
      </div>
    </div>
  )
}
