# AI Crypto Trading System - Frontend

AI加密货币交易系统的Web前端界面。

## 🚀 技术栈

- **框架**: Next.js 14 (App Router)
- **语言**: TypeScript
- **样式**: Tailwind CSS + shadcn/ui
- **状态管理**: Zustand + TanStack Query
- **图表**: TradingView Lightweight Charts + Recharts
- **实时通信**: WebSocket (Socket.io)
- **类型验证**: Zod

## 📁 项目结构

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── (dashboard)/       # 仪表盘布局组
│   │   │   ├── overview/      # 总览页
│   │   │   ├── trading/       # 交易页面
│   │   │   ├── positions/     # 持仓管理
│   │   │   ├── performance/   # 绩效分析
│   │   │   ├── history/       # 历史记录
│   │   │   └── settings/      # 系统设置
│   │   ├── layout.tsx         # 根布局
│   │   ├── providers.tsx      # 全局Provider
│   │   └── globals.css        # 全局样式
│   │
│   ├── components/            # UI组件
│   │   ├── ui/               # shadcn基础组件
│   │   ├── charts/           # 图表组件
│   │   ├── trading/          # 交易相关组件
│   │   ├── ai/               # AI决策展示组件
│   │   └── layout/           # 布局组件
│   │
│   ├── lib/                  # 工具库
│   │   ├── api/             # API客户端
│   │   │   ├── client.ts    # 基础客户端
│   │   │   ├── market.ts    # 市场数据API
│   │   │   ├── portfolio.ts # 投资组合API
│   │   │   └── decision.ts  # 决策API
│   │   ├── hooks/           # 自定义Hooks
│   │   ├── utils.ts         # 工具函数
│   │   └── constants.ts     # 常量定义
│   │
│   ├── stores/              # Zustand状态管理
│   │
│   └── types/               # TypeScript类型定义
│       ├── market.ts        # 市场数据类型
│       ├── trading.ts       # 交易相关类型
│       ├── portfolio.ts     # 投资组合类型
│       └── decision.ts      # 决策相关类型
│
├── public/                  # 静态资源
├── package.json
├── tsconfig.json
├── tailwind.config.ts
└── next.config.js
```

## 🛠️ 开发环境设置

### 1. 环境要求

- Node.js 20+
- npm 或 pnpm

### 2. 安装依赖

```bash
cd frontend
npm install
```

### 3. 环境变量配置

复制环境变量示例文件:

```bash
cp .env.local.example .env.local
```

编辑 `.env.local`:

```env
# API配置
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# 其他配置
NEXT_PUBLIC_APP_NAME="AI Crypto Trading System"
```

### 4. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000

## 🐳 使用Docker

### 开发环境

```bash
# 从项目根目录启动完整服务栈
cd ..
docker-compose up -d

# 只启动前端
docker-compose up frontend
```

前端将在 http://localhost:3000 运行

### 生产构建

```bash
npm run build
npm start
```

## 📦 可用脚本

```bash
# 开发模式
npm run dev

# 生产构建
npm run build

# 启动生产服务器
npm start

# 代码检查
npm run lint

# 类型检查
npm run type-check
```

## 🎨 页面功能

### 1. 总览仪表盘 (`/overview`)

- 投资组合总览
- 持仓列表
- 最近决策日志
- 市场行情概览
- 系统运行状态

### 2. 交易页面 (`/trading`)

- K线图表(TradingView)
- 订单簿深度图
- 当前交易信号
- AI决策推理展示

### 3. 持仓管理 (`/positions`)

- 持仓列表
- 持仓分布图
- 单个持仓详情
- 交易历史

### 4. 绩效分析 (`/performance`)

- 净值曲线
- 关键指标(夏普比率、最大回撤等)
- 交易统计分析
- AI反思记录

### 5. 历史记录 (`/history`)

- 决策历史时间线
- 交易记录
- 系统日志

### 6. 系统设置 (`/settings`)

- 风险参数配置
- 策略参数调整
- 系统开关控制

## 🔌 API集成

### API客户端使用

```typescript
import { api } from '@/lib/api'

// 获取投资组合
const portfolio = await api.portfolio.getPortfolio()

// 获取市场数据
const ticker = await api.market.getTicker('BTC/USDT')

// 获取决策历史
const decisions = await api.decision.getDecisionHistory(50)
```

### React Query使用

```typescript
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

function PortfolioComponent() {
  const { data, isLoading } = useQuery({
    queryKey: ['portfolio'],
    queryFn: () => api.portfolio.getPortfolio(),
    refetchInterval: 5000, // 每5秒刷新
  })

  if (isLoading) return <div>加载中...</div>

  return <div>总价值: ${data?.total_value}</div>
}
```

### WebSocket连接

```typescript
import { useEffect, useState } from 'react'

function useMarketWebSocket(symbol: string) {
  const [data, setData] = useState(null)

  useEffect(() => {
    const ws = new WebSocket(`${process.env.NEXT_PUBLIC_WS_URL}/ws/market/${symbol}`)

    ws.onmessage = (event) => {
      setData(JSON.parse(event.data))
    }

    return () => ws.close()
  }, [symbol])

  return data
}
```

## 🎯 开发计划

### Phase 1: 基础功能 ✅

- [x] 项目初始化
- [x] 基础布局和路由
- [x] API客户端
- [x] 类型定义

### Phase 2: 核心页面(进行中)

- [ ] 总览仪表盘组件
- [ ] 交易页面和图表
- [ ] 持仓管理界面
- [ ] 绩效分析页面

### Phase 3: 实时数据

- [ ] WebSocket集成
- [ ] 实时数据更新
- [ ] 图表实时刷新

### Phase 4: AI可视化

- [ ] 决策历史展示
- [ ] 推理过程可视化
- [ ] 记忆检索展示

### Phase 5: 优化与测试

- [ ] 性能优化
- [ ] 单元测试
- [ ] E2E测试
- [ ] 响应式设计

## 🤝 贡献指南

1. 组件开发遵循shadcn/ui规范
2. 所有API调用使用TanStack Query
3. 类型定义使用Zod进行验证
4. 样式使用Tailwind CSS类
5. 提交前运行类型检查: `npm run type-check`

## 📚 相关文档

- [Next.js文档](https://nextjs.org/docs)
- [shadcn/ui组件库](https://ui.shadcn.com)
- [TanStack Query](https://tanstack.com/query)
- [TradingView Charts](https://www.tradingview.com/lightweight-charts/)

## 🐛 问题反馈

如遇到问题,请在项目根目录的 GitHub Issues 中反馈。

---

**开发愉快!** 🚀
