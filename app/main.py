"""
FastAPI 应用入口
启动: uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import init_default_admin
from app.core.response import register_exception_handlers
from app.api.auth_router import router as auth_router
from app.api.dept_router import router as dept_router
from app.api.env_router import router as env_router
from app.api.audit_router import router as audit_router
from app.api.ui_router import router as ui_router
from app.api.api_router import router as api_router
from app.api.perf_router import router as perf_router
from app.ws.ws_router import router as ws_router

app = FastAPI(
    title="测试平台 API",
    description="UI / API / 性能 三合一测试平台后端",
    version="1.0.0",
)

# 注册统一企业级异常处理器（404, 405, 422, 500 等均转为正规中文错误响应）
register_exception_handlers(app)

# ── CORS（前端开发时允许所有来源，生产环境请收紧）─────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由注册 ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(dept_router)
app.include_router(env_router)
app.include_router(audit_router)
app.include_router(ui_router)
app.include_router(api_router)
app.include_router(perf_router)
app.include_router(ws_router)  # WebSocket 路由（无前缀）


@app.on_event("startup")
async def startup():
    from app.services.runner import auto_heal_zombie_tasks
    init_default_admin()
    healed = auto_heal_zombie_tasks()
    if healed:
        print(f"[WATCHDOG] 启动智能巡检：已自动修正 {len(healed)} 个历史挂起任务为 failed: {healed}")
    print("[APP] 测试平台后端已启动")
    print("[APP] Swagger 文档: http://127.0.0.1:8000/docs")


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "测试平台 API",
        "version": "1.0.0",
        "docs": "/docs",
        "modules": ["ui", "api-test", "perf"],
    }


@app.get("/health", tags=["Root"])
async def health():
    return {"status": "ok"}
