"""
FastAPI Main Application - RAAA 主应用

提供 REST API 接口和静态 React 前端服务。

功能：
    - API 路由：对话、文档、SRS、调研、统计
    - CORS 中间件：支持前端开发服务器跨域
    - 静态文件服务：生产模式下提供构建后的前端文件
    - SPA 路由：支持 React Router 的客户端路由
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from src.config import APP_TITLE
from api.routes import (
    chat_router,
    documents_router,
    srs_router,
    research_router,
    stats_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    print(f"🚀 Starting {APP_TITLE} API Server...")
    yield
    print(f"👋 Shutting down {APP_TITLE} API Server...")


app = FastAPI(
    title=APP_TITLE,
    description="REST API for Requirements Analysis Agent Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(documents_router, prefix="/api/documents", tags=["Documents"])
app.include_router(srs_router, prefix="/api/srs", tags=["SRS"])
app.include_router(research_router, prefix="/api/research", tags=["Research"])
app.include_router(stats_router, prefix="/api/stats", tags=["Stats"])


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": APP_TITLE}


# Serve static frontend files (after building React app)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
    
    # Catch-all route for SPA - must be last
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve React SPA for all non-API routes."""
        # Don't serve index.html for API routes
        if full_path.startswith("api/"):
            return {"error": "Not found"}, 404
        
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"error": "Frontend not built. Run 'npm run build' in frontend directory."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["api", "src"]
    )
