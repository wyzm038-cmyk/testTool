"""
组织架构部门管理路由：/dept/*
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user, require_super_admin
from app.core.audit import record_audit
from app.core.config import DEPARTMENTS_FILE, USERS_FILE
from app.db.json_store import append_to_list, find_in_list, read_json, update_in_list, write_json
from app.models.schemas import (
    CreateDepartmentRequest,
    Department,
    UpdateDepartmentRequest,
)

router = APIRouter(prefix="/dept", tags=["Department"])


@router.get("/list", summary="获取所有部门列表")
async def list_departments(_: dict = Depends(get_current_user)):
    from app.core.auth import get_departments
    return get_departments()


@router.post("", summary="创建新部门（超级管理员）")
async def create_department(
    req: CreateDepartmentRequest,
    current_user: dict = Depends(require_super_admin),
):
    depts = read_json(DEPARTMENTS_FILE, default=[])
    code = req.code.strip().lower()
    if any(d["code"].lower() == code for d in depts):
        raise HTTPException(status_code=400, detail=f"部门代码 [{code}] 已存在，不可重复")
    if any(d["name"] == req.name.strip() for d in depts):
        raise HTTPException(status_code=400, detail=f"部门名称 [{req.name}] 已存在，不可重复")

    new_dept = {
        "id": f"dept_{code}",
        "code": code,
        "name": req.name.strip(),
        "description": req.description,
        "created_at": datetime.now().isoformat(),
    }
    depts.append(new_dept)
    write_json(DEPARTMENTS_FILE, depts)

    record_audit(
        operator=current_user.get("username", "admin"),
        action="新建业务部门",
        module="组织架构",
        action_type="create",
        target=req.name.strip(),
        details=f"新建部门 [{req.name.strip()}] (代码: {code}, 描述: {req.description or '无'})",
    )

    return {
        "code": 200,
        "msg": f"部门 [{req.name}] 创建成功",
        "data": new_dept,
    }


@router.put("/{dept_id}", summary="修改部门信息（超级管理员）")
async def update_department(
    dept_id: str,
    req: UpdateDepartmentRequest,
    current_user: dict = Depends(require_super_admin),
):
    depts = read_json(DEPARTMENTS_FILE, default=[])
    target = next((d for d in depts if d["id"] == dept_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="部门不存在")

    updates = {}
    if req.name:
        updates["name"] = req.name.strip()
    if req.description is not None:
        updates["description"] = req.description

    target.update(updates)
    write_json(DEPARTMENTS_FILE, depts)

    record_audit(
        operator=current_user.get("username", "admin"),
        action="修改部门信息",
        module="组织架构",
        action_type="update",
        target=target.get("name"),
        details=f"更新部门 [{target.get('name')}] ({dept_id}): " + (f"名称->'{req.name}'; " if req.name else "") + (f"描述->'{req.description}'" if req.description is not None else ""),
    )

    return {
        "code": 200,
        "msg": "部门信息更新成功",
        "data": target,
    }


@router.delete("/{dept_id}", summary="删除部门（超级管理员）")
async def delete_department(
    dept_id: str,
    current_user: dict = Depends(require_super_admin),
):
    if dept_id in ["dept_qa", "dept_fin", "dept_mall"]:
        raise HTTPException(status_code=400, detail="预设核心部门禁止删除")

    users = read_json(USERS_FILE, default=[])
    if any(u.get("dept_id") == dept_id for u in users):
        raise HTTPException(status_code=400, detail="该部门下仍有关联用户，请先迁移或删除用户后再删除部门")

    depts = read_json(DEPARTMENTS_FILE, default=[])
    new_depts = [d for d in depts if d["id"] != dept_id]
    if len(new_depts) == len(depts):
        raise HTTPException(status_code=404, detail="部门不存在")

    write_json(DEPARTMENTS_FILE, new_depts)

    record_audit(
        operator=current_user.get("username", "admin"),
        action="删除业务部门",
        module="组织架构",
        action_type="delete",
        target=dept_id,
        details=f"永久删除了部门 [{dept_id}]",
    )

    return {
        "code": 200,
        "msg": "部门已删除",
        "data": {"dept_id": dept_id},
    }
