#!/usr/bin/env python
"""
RAAA Application Launcher - 应用启动器

启动 FastAPI 后端服务器。

开发模式：
    1. 运行此脚本启动后端: python run.py
    2. 另开终端启动前端: cd frontend && npm run dev
    3. 访问 http://localhost:5173 (前端开发服务器)

生产模式：
    1. 构建前端: cd frontend && npm run build
    2. 运行此脚本: python run.py
    3. 访问 http://localhost:8000 (后端同时提供静态文件)

API 文档：
    http://localhost:8000/docs (Swagger UI)
    http://localhost:8000/redoc (ReDoc)
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

if __name__ == "__main__":
    print("🚀 Starting RAAA API Server...")
    print("📝 API docs available at: http://localhost:8000/docs")
    print("🌐 Frontend (dev): http://localhost:5173")
    print("🌐 Frontend (prod): http://localhost:8000")
    print("-" * 50)
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["api", "src"]
    )
