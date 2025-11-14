"use client"

import { useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { format, subDays } from "date-fns"

export type TimeRange = "today" | "7d" | "30d" | "90d" | "all" | "custom"

export interface TimeRangeValue {
  start_date?: string
  end_date?: string
}

interface TimeRangeSelectorProps {
  value: TimeRange
  onChange: (range: TimeRange, dates: TimeRangeValue) => void
}

export function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  const [customStartDate, setCustomStartDate] = useState<string>("")
  const [customEndDate, setCustomEndDate] = useState<string>("")

  const handlePresetChange = (range: TimeRange) => {
    if (range === "custom") {
      onChange(range, {})
      return
    }

    // 使用 UTC 日期而不是本地日期
    const now = new Date()
    const utcToday = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
    let dates: TimeRangeValue = {}

    if (range === "today") {
      dates = {
        start_date: format(utcToday, "yyyy-MM-dd"),
        end_date: format(utcToday, "yyyy-MM-dd"),
      }
    } else if (range === "7d") {
      dates = {
        start_date: format(subDays(utcToday, 7), "yyyy-MM-dd"),
        end_date: format(utcToday, "yyyy-MM-dd"),
      }
    } else if (range === "30d") {
      dates = {
        start_date: format(subDays(utcToday, 30), "yyyy-MM-dd"),
        end_date: format(utcToday, "yyyy-MM-dd"),
      }
    } else if (range === "90d") {
      dates = {
        start_date: format(subDays(utcToday, 90), "yyyy-MM-dd"),
        end_date: format(utcToday, "yyyy-MM-dd"),
      }
    } else if (range === "all") {
      // 使用一个很早的开始日期来获取所有数据
      dates = {
        start_date: "2020-01-01",
        end_date: format(utcToday, "yyyy-MM-dd"),
      }
    }

    onChange(range, dates)
  }

  const handleCustomDateChange = () => {
    if (customStartDate && customEndDate) {
      onChange("custom", {
        start_date: customStartDate,
        end_date: customEndDate,
      })
    }
  }

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-muted-foreground mr-2">时间范围:</span>

          <Button
            variant={value === "today" ? "default" : "outline"}
            size="sm"
            onClick={() => handlePresetChange("today")}
          >
            今日
          </Button>

          <Button
            variant={value === "7d" ? "default" : "outline"}
            size="sm"
            onClick={() => handlePresetChange("7d")}
          >
            7天
          </Button>

          <Button
            variant={value === "30d" ? "default" : "outline"}
            size="sm"
            onClick={() => handlePresetChange("30d")}
          >
            30天
          </Button>

          <Button
            variant={value === "90d" ? "default" : "outline"}
            size="sm"
            onClick={() => handlePresetChange("90d")}
          >
            90天
          </Button>

          <Button
            variant={value === "all" ? "default" : "outline"}
            size="sm"
            onClick={() => handlePresetChange("all")}
          >
            全部
          </Button>

          <div className="flex items-center gap-2">
            <Button
              variant={value === "custom" ? "default" : "outline"}
              size="sm"
              onClick={() => handlePresetChange("custom")}
            >
              自定义
            </Button>

            {value === "custom" && (
              <>
                <Input
                  type="date"
                  value={customStartDate}
                  onChange={(e) => setCustomStartDate(e.target.value)}
                  className="w-auto"
                />

                <span className="text-muted-foreground">-</span>

                <Input
                  type="date"
                  value={customEndDate}
                  onChange={(e) => setCustomEndDate(e.target.value)}
                  className="w-auto"
                />

                <Button
                  size="sm"
                  onClick={handleCustomDateChange}
                  disabled={!customStartDate || !customEndDate}
                >
                  应用
                </Button>
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
