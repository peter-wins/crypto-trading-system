# 🐛 Bug修复: API导入错误

## 问题描述

**错误信息**: `ReferenceError: marketAPI is not defined`

**原因**: API模块导出顺序问题，在定义 `api` 对象时，`marketAPI` 等变量还未完成导入。

## ✅ 修复方案

### 修改文件: `frontend/src/lib/api/index.ts`

**之前的代码** (有问题):
```typescript
export { apiClient, APIError } from './client'
export { marketAPI } from './market'
export { portfolioAPI } from './portfolio'
export { decisionAPI } from './decision'

// 这里使用了还未完全导入的变量
export const api = {
  market: marketAPI,  // ❌ ReferenceError
  portfolio: portfolioAPI,
  decision: decisionAPI,
}
```

**修复后的代码**:
```typescript
export { apiClient, APIError } from './client'

// 先导入
import { marketAPI } from './market'
import { portfolioAPI } from './portfolio'
import { decisionAPI } from './decision'

// 再导出
export { marketAPI, portfolioAPI, decisionAPI }

// 最后创建组合对象
export const api = {
  market: marketAPI,  // ✅ 正常工作
  portfolio: portfolioAPI,
  decision: decisionAPI,
}
```

### 同时修复Hooks中的导入

**修改文件**: `frontend/src/lib/hooks/usePortfolio.ts`

**之前**:
```typescript
import { api } from "@/lib/api"

// 使用
api.portfolio.getPortfolio()
```

**修复后**:
```typescript
import { portfolioAPI } from "@/lib/api"

// 直接使用
portfolioAPI.getPortfolio()
```

**修改文件**: `frontend/src/lib/hooks/useDecisions.ts`

**之前**:
```typescript
import { api } from "@/lib/api"

// 使用
api.decision.getDecisionHistory()
```

**修复后**:
```typescript
import { decisionAPI } from "@/lib/api"

// 直接使用
decisionAPI.getDecisionHistory()
```

## 📝 修改的文件清单

1. ✅ `frontend/src/lib/api/index.ts` - 修复导出顺序
2. ✅ `frontend/src/lib/hooks/usePortfolio.ts` - 更新导入
3. ✅ `frontend/src/lib/hooks/useDecisions.ts` - 更新导入

## 🧪 验证修复

重新启动前端开发服务器:

```bash
cd frontend
npm run dev
```

访问 http://localhost:3000/overview

应该能正常看到页面，不再报错。

## 📖 技术说明

### 为什么会出现这个问题?

在JavaScript/TypeScript中，使用 `export { ... } from '...'` 语法时，导出和导入是同时发生的。当我们在定义 `api` 对象时引用这些变量，它们可能还没有完全初始化。

### 解决方案

1. **先导入**: 使用 `import` 语句明确导入所有依赖
2. **再导出**: 使用 `export` 语句导出这些模块
3. **最后使用**: 在导入完成后创建组合对象

这样可以确保所有依赖都已经完全加载。

## ✨ 额外优化

现在你有两种使用API的方式:

**方式1: 直接导入** (推荐，类型提示更好)
```typescript
import { portfolioAPI, decisionAPI } from "@/lib/api"

portfolioAPI.getPortfolio()
decisionAPI.getDecisionHistory()
```

**方式2: 使用组合对象**
```typescript
import { api } from "@/lib/api"

api.portfolio.getPortfolio()
api.decision.getDecisionHistory()
```

两种方式都可以正常工作，推荐使用方式1。

---

**问题已修复！** ✅
