"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useState } from "react"
import { ThemeProvider } from "@/components/theme-provider"

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 60 * 1000, // 5分钟 - 数据在此期间被认为是新鲜的
            cacheTime: 10 * 60 * 1000, // 10分钟 - 未使用的数据保留在缓存中的时间
            refetchOnWindowFocus: false,
            retry: 2, // 失败时重试2次
            retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000), // 指数退避
          },
        },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        disableTransitionOnChange
      >
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  )
}
