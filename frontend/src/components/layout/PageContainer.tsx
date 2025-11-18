import { cn } from "@/lib/utils"

interface PageContainerProps {
  children: React.ReactNode
  className?: string
}

/**
 * 统一的页面容器组件
 * 提供一致的间距和动画效果
 *
 * @example
 * export default function MyPage() {
 *   return (
 *     <PageContainer>
 *       <h1>页面标题</h1>
 *       <div>页面内容</div>
 *     </PageContainer>
 *   )
 * }
 */
export function PageContainer({ children, className }: PageContainerProps) {
  return (
    <div
      className={cn(
        "space-y-6 animate-in fade-in duration-200",
        className
      )}
    >
      {children}
    </div>
  )
}
