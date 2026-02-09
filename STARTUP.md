# RAAA 启动指南

## 快速开始

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 安装前端依赖

```bash
cd frontend
npm install
```

### 3. 启动应用

#### 开发模式（推荐）

需要两个终端：

**终端 1 - 启动后端 API：**
```bash
python run.py
```

**终端 2 - 启动前端开发服务器：**
```bash
cd frontend
npm run dev
```

然后访问：http://localhost:5173

#### 生产模式

先构建前端：
```bash
cd frontend
npm run build
```

然后启动后端（会自动托管前端静态文件）：
```bash
python run.py
```

访问：http://localhost:8000

---

## API 文档

启动后端后，访问 http://localhost:8000/docs 查看 Swagger API 文档。

## 主要 API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/chat/send` | POST | 发送消息 |
| `/api/chat/stream` | POST | 流式响应 |
| `/api/documents/upload` | POST | 上传文档 |
| `/api/srs/generate` | POST | 生成 SRS |
| `/api/research/start` | POST | 启动深度调研 |
| `/api/stats/index` | GET | 获取索引统计 |
| `/api/stats/memory` | GET | 获取记忆统计 |

## 环境变量

确保 `.env` 文件包含必要的配置：

```
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## 从 Streamlit 迁移说明

原来的 `streamlit run app.py` 命令已被替换为新的启动方式。

功能对照：
- 原 Streamlit 界面 → 新 React 界面
- 原 `st.session_state` → FastAPI Session 管理
- 原 `st.chat_input` → React ChatInput 组件
- 原 `st.sidebar` → React Sidebar 组件

所有后端逻辑（`src/` 目录）保持不变。
