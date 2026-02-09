# RAAA Frontend Architecture

## Overview

RAAA (Requirements Analysis Agent Assistant) 的前端是一个现代化的单页应用（SPA），采用 React 18 + TypeScript + Vite 技术栈构建。前端设计灵感来源于 Grok 官网，采用深黑色主题配合星空动画背景，呈现高端、大气、简约的视觉效果。

## Technology Stack

| 技术 | 版本 | 用途 |
|------|------|------|
| **React** | 18.2.0 | UI 框架 |
| **TypeScript** | 5.3.3 | 类型安全 |
| **Vite** | 5.1.0 | 构建工具和开发服务器 |
| **TailwindCSS** | 3.4.1 | 原子化 CSS 框架 |
| **Zustand** | 4.5.0 | 轻量级状态管理 |
| **Axios** | 1.6.7 | HTTP 客户端 |
| **React Markdown** | 9.0.1 | Markdown 渲染 |
| **Mermaid** | 10.8.0 | 图表渲染 |
| **Lucide React** | 0.323.0 | 图标库 |

## Project Structure

```
frontend/
├── public/                    # 静态资源
│   └── RAAAICON.png          # 应用图标
├── src/
│   ├── api/                   # API 服务层
│   │   └── index.ts          # 所有 API 调用封装
│   ├── components/            # React 组件
│   │   ├── Layout.tsx        # 主布局组件
│   │   ├── Sidebar.tsx       # 侧边栏组件
│   │   ├── ChatArea.tsx      # 聊天区域组件
│   │   ├── ChatMessage.tsx   # 消息气泡组件
│   │   ├── MermaidDiagram.tsx # Mermaid 图表组件
│   │   └── StarryBackground.tsx # 星空背景动画
│   ├── store/                 # 状态管理
│   │   └── appStore.ts       # Zustand 全局状态
│   ├── App.tsx               # 应用根组件
│   ├── main.tsx              # 入口文件
│   └── index.css             # 全局样式
├── index.html                 # HTML 模板
├── vite.config.ts            # Vite 配置
├── tailwind.config.js        # TailwindCSS 配置
├── tsconfig.json             # TypeScript 配置
└── package.json              # 依赖管理
```

## Architecture Design

### 1. Component Architecture

前端采用组件化架构，组件层次如下：

```
App
└── Layout
    ├── StarryBackground (Canvas 动画背景)
    ├── Sidebar (功能控制面板)
    └── ChatArea (主聊天区域)
        ├── Welcome Screen (欢迎页面)
        └── Chat Messages
            ├── ChatMessage (消息气泡)
            └── MermaidDiagram (图表渲染)
```

### 2. State Management (Zustand)

使用 Zustand 进行全局状态管理，相比 Redux 更加轻量和简洁。

**核心状态结构：**

```typescript
interface AppState {
  // Session 管理
  sessionId: string | null
  
  // 聊天状态
  messages: Message[]
  isLoading: boolean
  streamingContent: string
  
  // 角色选择
  selectedRole: string
  availableRoles: string[]
  
  // 文档索引
  indexedFiles: string[]
  isIndexing: boolean
  indexingStatus: string | null
  indexStats: IndexStats | null
  
  // 记忆统计
  memoryStats: MemoryStats | null
  
  // SRS 生成
  generatedSrs: string | null
  isGeneratingSrs: boolean
  
  // 深度研究
  researchTask: ResearchTask | null
}
```

**状态持久化：**

使用 Zustand 的 `persist` 中间件将关键状态（sessionId、selectedRole）持久化到 localStorage：

```typescript
export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // ... state and actions
    }),
    {
      name: 'raaa-storage',
      partialize: (state) => ({ 
        sessionId: state.sessionId,
        selectedRole: state.selectedRole,
      }),
    }
  )
)
```

### 3. API Layer

API 层封装了所有与后端的通信，使用 Axios 作为 HTTP 客户端。

**Session ID 自动注入：**

```typescript
api.interceptors.request.use((config) => {
  const sessionId = localStorage.getItem('raaa-session-id')
  if (sessionId) {
    config.headers['X-Session-ID'] = sessionId
  }
  return config
})
```

**API 模块划分：**

| 模块 | 功能 |
|------|------|
| Chat API | 消息发送、流式响应、历史记录 |
| Documents API | 文档上传、索引、知识图谱构建 |
| SRS API | 需求规格说明书生成和下载 |
| Research API | 深度研究任务管理 |
| Stats API | 统计信息、会话管理 |

**流式响应处理 (SSE)：**

```typescript
export async function sendMessageStream(
  message: string,
  role: string | null,
  sessionId: string | null,
  onChunk: (chunk: string) => void,
  onComplete: (data: { mermaid?: string; pdf?: string; docx?: string }) => void,
  onError: (error: string) => void
) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(sessionId ? { 'X-Session-ID': sessionId } : {}),
    },
    body: JSON.stringify({ message, role }),
  })

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()
  
  // 解析 SSE 事件流
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    
    const text = decoder.decode(value)
    // 处理 event: 和 data: 行
    // ...
  }
}
```

## Component Details

### 1. Layout Component

主布局组件，负责整体页面结构和 Sidebar 折叠状态管理。

```typescript
export default function Layout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <div className="flex h-screen bg-black relative overflow-hidden">
      <StarryBackground />
      <Sidebar 
        isCollapsed={sidebarCollapsed} 
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} 
      />
      <main className="flex-1 flex flex-col overflow-hidden relative z-10">
        <ChatArea />
      </main>
    </div>
  )
}
```

**设计要点：**
- 使用 Flexbox 布局
- StarryBackground 作为底层背景（z-index: 0）
- Sidebar 和 ChatArea 在背景之上（z-index: 10-20）

### 2. Sidebar Component

侧边栏组件，提供所有功能控制入口。

**功能模块：**

| 模块 | 功能 |
|------|------|
| Role Selection | 角色切换（需求分析师、架构师等） |
| Documents | 文档上传、索引、知识图谱管理 |
| SRS Generation | 需求规格说明书生成 |
| Memory & Chat | 记忆和聊天历史管理 |
| Tips | 使用提示 |

**折叠状态：**

```typescript
if (isCollapsed) {
  return (
    <aside className="w-12 h-full bg-[#0a0a0a] border-r border-white/10 ...">
      <button onClick={onToggle}>»</button>
    </aside>
  )
}

return (
  <aside className="w-64 h-full bg-[#0a0a0a] border-r border-white/10 ...">
    {/* 完整内容 */}
  </aside>
)
```

### 3. ChatArea Component

聊天区域组件，包含欢迎页面和消息列表。

**欢迎页面：**
- 显示 RAAA Logo（RAAAICON.png）
- 简介文字
- 联系邮箱

**消息列表：**
- 用户消息和助手消息区分显示
- 支持 Markdown 渲染
- 支持 Mermaid 图表渲染
- 支持流式响应显示
- 支持研究报告下载（PDF/Word）

**输入区域：**
- 自适应高度的 textarea
- Enter 发送，Shift+Enter 换行
- 发送按钮带加载状态

### 4. ChatMessage Component

消息气泡组件，支持 Markdown 渲染。

**特性：**
- 用户消息右对齐，助手消息左对齐
- 使用 react-markdown 渲染 Markdown
- 支持 GFM（GitHub Flavored Markdown）
- 代码块语法高亮
- 流式响应时显示光标动画

```typescript
<ReactMarkdown
  remarkPlugins={[remarkGfm]}
  components={{
    code({ inline, className, children, ...props }) {
      // 自定义代码块渲染
      // 跳过 mermaid 代码块（由 MermaidDiagram 组件处理）
    },
    a({ href, children, ...props }) {
      // 链接在新标签页打开
    },
  }}
>
  {message.content}
</ReactMarkdown>
```

### 5. MermaidDiagram Component

Mermaid 图表渲染组件。

**配置：**

```typescript
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
  fontFamily: 'inherit',
  themeVariables: {
    primaryColor: '#1e293b',
    primaryTextColor: '#fff',
    primaryBorderColor: '#334155',
    lineColor: '#64748b',
    secondaryColor: '#0f172a',
    tertiaryColor: '#1e293b',
  },
})
```

**渲染流程：**
1. 清理代码（移除 markdown 代码块标记）
2. 调用 mermaid.render() 生成 SVG
3. 使用 dangerouslySetInnerHTML 插入 SVG
4. 错误时显示错误信息和原始代码

### 6. StarryBackground Component

Canvas 星空背景动画组件。

**动画元素：**

| 元素 | 数量 | 特性 |
|------|------|------|
| 星星 | 200 | 闪烁、缓慢移动、边缘环绕 |
| 流星 | 最多 5 个 | 随机生成、渐变尾迹、发光头部 |

**实现原理：**

```typescript
useEffect(() => {
  const canvas = canvasRef.current
  const ctx = canvas.getContext('2d')
  
  // 创建星星数组
  const stars: Star[] = []
  for (let i = 0; i < 200; i++) {
    stars.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      size: Math.random() * 1.5 + 0.5,
      opacity: Math.random() * 0.5 + 0.3,
      twinkleSpeed: Math.random() * 0.02 + 0.01,
      speedX: (Math.random() - 0.5) * 0.15,
      speedY: (Math.random() - 0.5) * 0.15,
    })
  }
  
  // 动画循环
  const animate = () => {
    // 半透明填充实现拖尾效果
    ctx.fillStyle = 'rgba(0, 0, 0, 0.15)'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    
    // 绘制星星
    stars.forEach(star => {
      // 更新位置、闪烁、绘制
    })
    
    // 绘制流星
    shootingStars.forEach(star => {
      // 渐变尾迹、发光头部
    })
    
    requestAnimationFrame(animate)
  }
  
  animate()
}, [])
```

## Styling System

### TailwindCSS Configuration

**自定义颜色：**

```javascript
colors: {
  primary: {
    50: '#f8fafc',
    // ... 完整色阶
    900: '#0f172a',
  },
  dark: {
    50: '#18181b',
    // ... 深黑色色阶
    900: '#000000',
  },
}
```

**自定义动画：**

```javascript
animation: {
  'twinkle': 'twinkle 3s ease-in-out infinite',
  'shooting-star': 'shooting-star 3s ease-in-out infinite',
  'float': 'float 6s ease-in-out infinite',
}
```

### Global CSS

**主要样式：**

| 样式类 | 用途 |
|--------|------|
| `.markdown-content` | Markdown 内容样式 |
| `.sidebar-transition` | Sidebar 过渡动画 |
| `.glow-input` | 输入框发光效果 |
| `.glass` | 毛玻璃效果 |
| `.animate-fade-in` | 淡入动画 |
| `.animate-subtle-pulse` | Logo 脉冲动画 |
| `.loading-dot` | 加载点动画 |

## Build & Development

### Development Mode

```bash
cd frontend
npm install
npm run dev
```

开发服务器启动在 http://localhost:5173，自动代理 `/api` 请求到后端 http://localhost:8000。

### Production Build

```bash
npm run build
```

构建输出到 `dist/` 目录，可由 FastAPI 后端静态文件服务提供。

### Vite Configuration

```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
```

## Design Philosophy

### 1. 高端大气简约

- **深黑色主题**：使用纯黑 `#000000` 和深灰 `#0a0a0a` 作为主色调
- **星空动画**：Canvas 实现的动态星空背景，增加科技感
- **简洁布局**：左侧功能面板 + 右侧聊天区域的经典布局
- **无图标设计**：Sidebar 仅使用文字，避免视觉干扰

### 2. 用户体验优化

- **流式响应**：实时显示 AI 回复，提升交互感
- **自动滚动**：新消息自动滚动到视图
- **状态反馈**：加载状态、错误提示、操作结果即时反馈
- **响应式设计**：适配不同屏幕尺寸

### 3. 性能优化

- **Canvas 动画**：使用 requestAnimationFrame 实现流畅动画
- **状态持久化**：关键状态持久化到 localStorage
- **懒加载**：Mermaid 图表按需渲染
- **代码分割**：Vite 自动代码分割

## Integration with Backend

前端通过 RESTful API 和 SSE（Server-Sent Events）与 FastAPI 后端通信。

**API 端点：**

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/chat/send` | POST | 发送消息 |
| `/api/chat/stream` | POST | 流式消息 |
| `/api/documents/upload` | POST | 上传文档 |
| `/api/documents/graph/build` | POST | 构建知识图谱 |
| `/api/srs/generate` | POST | 生成 SRS |
| `/api/research/start` | POST | 启动深度研究 |
| `/api/stats/memory` | GET | 获取记忆统计 |

**Session 管理：**

每个用户会话通过 `X-Session-ID` 请求头标识，支持多用户并发使用。

## Summary

RAAA 前端采用现代化的 React 技术栈，结合 TailwindCSS 的原子化样式和 Zustand 的轻量级状态管理，实现了一个高性能、易维护的单页应用。星空动画背景和深黑色主题的设计，为用户提供了沉浸式的使用体验。通过 SSE 实现的流式响应，让 AI 对话更加自然流畅。整体架构清晰，组件职责明确，便于后续功能扩展和维护。
