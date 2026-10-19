"""
环境配置与系统设置路由：/env/*
"""
from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.audit import get_audit_logs, record_audit
from app.core.auth import get_current_user, require_super_admin
from app.core.config import AUDIT_LOGS_FILE, ENVIRONMENTS_FILE
from app.db.json_store import append_to_list, find_in_list, read_json, update_in_list, write_json
from app.models.schemas import (
    AuditLog,
    CreateEnvironmentRequest,
    Environment,
    UpdateEnvironmentRequest,
)

router = APIRouter(prefix="/env", tags=["Environment"])

DEFAULT_ENVIRONMENTS = [
    {
        "id": "env_dev",
        "name": "开发联调环境 (DEV)",
        "code": "dev",
        "base_url": "https://dev-gateway.internal.net",
        "description": "研发日常特性联调与单元/集成测试环境",
        "headers": {
            "Content-Type": "application/json",
            "X-Env": "dev",
            "Authorization": "Bearer dev_jwt_token_sample",
        },
        "variables": {
            "GATEWAY_PORT": "8080",
            "TIMEOUT_MS": "3000",
            "MOCK_ENABLED": "true",
        },
        "is_default": False,
        "created_at": "2026-10-16T12:00:00",
    },
    {
        "id": "env_test",
        "name": "集成测试环境 (TEST)",
        "code": "test",
        "base_url": "https://test-gateway.internal.net",
        "description": "质量保障中心全链路集成回归环境（默认基准）",
        "headers": {
            "Content-Type": "application/json",
            "X-Env": "test",
            "Authorization": "Bearer qa_test_token_standard",
        },
        "variables": {
            "GATEWAY_PORT": "8000",
            "TIMEOUT_MS": "5000",
            "MOCK_ENABLED": "false",
        },
        "is_default": True,
        "created_at": "2026-10-16T12:00:00",
    },
    {
        "id": "env_staging",
        "name": "预发布灰度环境 (STAGING)",
        "code": "staging",
        "base_url": "https://staging-api.internal.net",
        "description": "仿真生产数据与发布前准入最终演练环境",
        "headers": {
            "Content-Type": "application/json",
            "X-Env": "staging",
            "X-Canary": "always",
        },
        "variables": {
            "TIMEOUT_MS": "8000",
            "CACHE_TTL": "60",
        },
        "is_default": False,
        "created_at": "2026-10-16T12:00:00",
    },
    {
        "id": "env_prod",
        "name": "生产巡检环境 (PROD)",
        "code": "prod",
        "base_url": "https://api.company.com",
        "description": "生产拨测、健康探针与只读监控巡检环境（只读鉴权）",
        "headers": {
            "Content-Type": "application/json",
            "X-Env": "prod",
            "X-Health-Check": "true",
        },
        "variables": {
            "READ_ONLY": "true",
            "TIMEOUT_MS": "2000",
        },
        "is_default": False,
        "created_at": "2026-10-16T12:00:00",
    },
]


def init_default_environments():
    envs = read_json(ENVIRONMENTS_FILE, default=[])
    if not envs:
        write_json(ENVIRONMENTS_FILE, DEFAULT_ENVIRONMENTS)


def get_environments() -> List[dict]:
    init_default_environments()
    return read_json(ENVIRONMENTS_FILE, default=DEFAULT_ENVIRONMENTS)


@router.get("/list", summary="获取所有测试运行环境列表")
async def list_environments(_: dict = Depends(get_current_user)):
    return get_environments()


@router.post("", summary="创建新测试环境（仅管理员）")
async def create_environment(
    req: CreateEnvironmentRequest,
    current_user: dict = Depends(require_super_admin),
):
    envs = get_environments()
    code = req.code.strip().lower()
    if any(e["code"].lower() == code for e in envs):
        raise HTTPException(status_code=400, detail=f"环境标识代码 [{code}] 已存在")

    if req.is_default:
        for e in envs:
            e["is_default"] = False

    new_env = {
        "id": f"env_{code}",
        "name": req.name.strip(),
        "code": code,
        "base_url": req.base_url.strip(),
        "description": req.description or "",
        "headers": req.headers or {},
        "variables": req.variables or {},
        "is_default": req.is_default,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    envs.append(new_env)
    write_json(ENVIRONMENTS_FILE, envs)

    record_audit(
        operator=current_user["username"],
        action="创建测试环境",
        module="运行环境",
        action_type="create",
        target=f"{req.name} ({code})",
        details=f"新建环境 [{req.name}] (BaseUrl: {req.base_url})",
    )

    return {
        "code": 200,
        "msg": f"测试环境 [{req.name}] 创建成功",
        "data": new_env,
    }


@router.put("/{env_id}", summary="修改测试环境配置（仅管理员）")
async def update_environment(
    env_id: str,
    req: UpdateEnvironmentRequest,
    current_user: dict = Depends(require_super_admin),
):
    envs = get_environments()
    target = next((e for e in envs if e["id"] == env_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="环境配置不存在")

    if req.is_default:
        for e in envs:
            e["is_default"] = False
        target["is_default"] = True
    elif req.is_default is False:
        target["is_default"] = False

    if req.name:
        target["name"] = req.name.strip()
    if req.base_url:
        target["base_url"] = req.base_url.strip()
    if req.description is not None:
        target["description"] = req.description
    if req.headers is not None:
        target["headers"] = req.headers
    if req.variables is not None:
        target["variables"] = req.variables
    target["updated_at"] = datetime.now().isoformat()

    write_json(ENVIRONMENTS_FILE, envs)

    record_audit(
        operator=current_user["username"],
        action="修改测试环境",
        module="运行环境",
        action_type="update",
        target=target['name'],
        details=f"更新了环境 [{target['name']}] 配置参数 (网关: {target['base_url']})",
    )

    return {
        "code": 200,
        "msg": "环境配置更新成功",
        "data": target,
    }


@router.delete("/{env_id}", summary="删除测试环境（仅管理员）")
async def delete_environment(
    env_id: str,
    current_user: dict = Depends(require_super_admin),
):
    envs = get_environments()
    target = next((e for e in envs if e["id"] == env_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="环境不存在")

    if target.get("is_default"):
        raise HTTPException(status_code=400, detail="当前环境为默认基准环境，禁止直接删除")

    new_envs = [e for e in envs if e["id"] != env_id]
    write_json(ENVIRONMENTS_FILE, new_envs)

    record_audit(
        operator=current_user["username"],
        action="删除测试环境",
        module="运行环境",
        action_type="delete",
        target=target['name'],
        details=f"删除了环境 [{target['name']}] ({target['code']})",
    )

    return {
        "code": 200,
        "msg": f"环境 [{target['name']}] 已成功删除",
        "data": {"env_id": env_id},
    }


@router.post("/{env_id}/set-default", summary="设为默认基准环境（仅管理员）")
async def set_default_environment(
    env_id: str,
    current_user: dict = Depends(require_super_admin),
):
    envs = get_environments()
    target = next((e for e in envs if e["id"] == env_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="环境不存在")

    for e in envs:
        e["is_default"] = (e["id"] == env_id)

    write_json(ENVIRONMENTS_FILE, envs)

    record_audit(
        operator=current_user["username"],
        action="设为默认环境",
        module="运行环境",
        action_type="update",
        target=target['name'],
        details=f"将环境 [{target['name']}] 设置为全平台默认基准环境",
    )

    return {
        "code": 200,
        "msg": f"已将 [{target['name']}] 设为默认激活环境",
        "data": target,
    }


@router.get("/audit-logs", summary="获取系统操作审计日志（仅管理员）")
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    _: dict = Depends(require_super_admin),
):
    result = get_audit_logs(limit=limit)
    return result.get("logs", [])
