"""
安全审计日志路由：/audit/*
提供关键系统操作日志查询、分类检索及管理员一键安全清空能力。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user, is_super_admin, require_admin
from app.core.audit import clear_audit_logs, get_audit_logs

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/logs", summary="获取系统操作审计日志（仅管理员）")
async def list_audit_logs(
    module: Optional[str] = Query(None, description="按模块过滤"),
    action_type: Optional[str] = Query(None, description="按操作类型过滤: create|update|delete|clear"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(200, ge=1, le=500),
    current_user: dict = Depends(require_admin),
):
    """查询平台操作审计日志，包含按模块、行为、关键词组合检索"""
    return get_audit_logs(
        module=module,
        action_type=action_type,
        search=search,
        limit=limit,
    )


@router.post("/clear", summary="一键清空审计日志（仅限管理员）")
async def clear_logs(
    current_user: dict = Depends(get_current_user),
):
    """
    一键清空审计日志。
    只有系统管理员（super_admin / admin）角色才有权执行！
    其他角色调用将直接返回 403 Forbidden。
    """
    user_role = current_user.get("role")
    if user_role not in ["super_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足：只有管理员（Admin）角色才可以执行一键清空审计日志操作！",
        )

    operator = current_user.get("username", "admin")
    record = clear_audit_logs(operator=operator)
    return {
        "code": 200,
        "msg": "系统审计日志已成功清空并重置留痕",
        "data": record,
    }
