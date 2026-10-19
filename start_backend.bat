@echo off
chcp 65001 >nul
title 测试平台后端服务 (FastAPI)
cd /d D:\antigravity\go\testTool
echo ========================================================
echo   AutoTest Studio 测试平台后端服务
echo   访问文档: http://127.0.0.1:8000/docs
echo ========================================================
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
if %errorlevel% neq 0 (
    echo [错误] 后端启动异常，请检查 Python 环境及依赖
    pause
)
