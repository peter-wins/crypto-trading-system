"use client"

import { Bell, Search } from "lucide-react"
import { ThemeToggle } from "@/components/theme-toggle"

export function Navbar() {
  return (
    <div className="flex h-full items-center justify-between flex-1">
      {/* 搜索栏 */}
      <div className="flex-1 max-w-md">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            placeholder="搜索币种、交易对..."
            className="w-full rounded-lg border bg-background py-2 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
      </div>

      {/* 右侧操作区 */}
      <div className="flex items-center gap-4">
        {/* 通知 */}
        <button className="relative rounded-lg p-2 hover:bg-accent">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-red-500"></span>
        </button>

        {/* 主题切换 */}
        <ThemeToggle />

        {/* 用户信息 */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-sm font-medium">AI Agent</p>
            <p className="text-xs text-muted-foreground">自主交易中</p>
          </div>
          <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-semibold">
            AI
          </div>
        </div>
      </div>
    </div>
  )
}
