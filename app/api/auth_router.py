from typing import List, Optional
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.auth import (
    authenticate_user,
    create_access_token,
    enrich_user_dept,
    get_current_user,
    get_department_by_id,
    hash_password,
    is_super_admin,
    require_admin,
    require_super_admin,
)
from app.core.config import USERS_FILE
from app.core.audit import record_audit
from app.db.json_store import find_in_list, read_json, write_json
from app.models.schemas import (
    CreateUserRequest,
    LoginRequest,
    TokenResponse,
    UpdateProfileRequest,
    UpdateUserRequest,
    UserInfo,
    UserRole,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    支持标准 OAuth2 表单登录（username + password）。
    前端也可以发 JSON，见 /auth/login-json。
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user["username"]})
    return TokenResponse(access_token=token)


@router.post("/login-json", response_model=TokenResponse, summary="JSON 方式登录")
async def login_json(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token({"sub": user["username"]})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserInfo, summary="获取当前用户信息")
async def me(current_user: dict = Depends(get_current_user)):
    user_info = {k: current_user.get(k) for k in UserInfo.model_fields if k in current_user}
    return UserInfo(**user_info)


@router.put("/profile", response_model=UserInfo, summary="更新当前登录用户个人资料与头像")
async def update_profile(
    req: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
):
    users = read_json(USERS_FILE, default=[])
    username = current_user["username"]
    target = next((u for u in users if u["username"] == username), None)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    changes = []
    if req.nickname is not None and req.nickname.strip() != target.get("nickname"):
        target["nickname"] = req.nickname.strip()
        changes.append(f"昵称更改为 '{req.nickname.strip()}'")

    if req.avatar is not None and req.avatar != target.get("avatar"):
        target["avatar"] = req.avatar
        changes.append("更换了个人头像")

    if req.new_password:
        if not req.old_password:
            raise HTTPException(status_code=400, detail="修改密码需验证当前原密码")
        if not verify_password(req.old_password, target["password_hash"]):
            raise HTTPException(status_code=400, detail="原密码错误，修改密码失败")
        if len(req.new_password) < 6:
            raise HTTPException(status_code=400, detail="新密码长度不可少于 6 位")
        target["password_hash"] = hash_password(req.new_password)
        changes.append("修改了登录密码")

    write_json(USERS_FILE, users)

    if changes:
        record_audit(
            operator=username,
            action="修改个人资料/头像",
            module="用户与权限",
            action_type="update",
            target=username,
            details=f"用户 [@{username}] 更新了个人配置: " + "; ".join(changes),
        )

    enriched = enrich_user_dept(target)
    user_info = {k: enriched.get(k) for k in UserInfo.model_fields if k in enriched}
    return UserInfo(**user_info)


@router.get("/users", summary="获取用户列表（带部门和角色）")
async def list_users(
    dept_id: Optional[str] = Query(None, description="按部门 ID 筛选"),
    current_user: dict = Depends(require_admin),
):
    users = read_json(USERS_FILE, default=[])
    enriched_users = [enrich_user_dept(u) for u in users]

    # 普通部门管理员只能查看自己部门的用户，超管可查看所有或筛选
    if not is_super_admin(current_user):
        user_dept = current_user.get("dept_id")
        return [u for u in enriched_users if u.get("dept_id") == user_dept]

    if dept_id:
        return [u for u in enriched_users if u.get("dept_id") == dept_id]

    return enriched_users


@router.post("/users", summary="创建用户（部门主管或超管）")
async def create_user(
    req: CreateUserRequest,
    current_user: dict = Depends(require_admin),
):
    users = read_json(USERS_FILE, default=[])
    if any(u["username"] == req.username for u in users):
        raise HTTPException(status_code=400, detail=f"用户名 [{req.username}] 已存在")

    dept = get_department_by_id(req.dept_id or "dept_qa")
    if not dept:
        raise HTTPException(status_code=400, detail=f"指定的部门 [{req.dept_id}] 不存在")

    # 权限校验：部门主管不能越权为其他部门创建用户，也不能创建 super_admin
    if not is_super_admin(current_user):
        if req.dept_id != current_user.get("dept_id"):
            raise HTTPException(status_code=403, detail="部门主管只能在本部门下创建用户")
        if req.role in [UserRole.SUPER_ADMIN, "admin"]:
            raise HTTPException(status_code=403, detail="无权创建超级管理员账号")

    new_user = {
        "id": f"u{uuid.uuid4().hex[:6]}",
        "username": req.username,
        "nickname": req.nickname or req.username,
        "password_hash": hash_password(req.password),
        "dept_id": req.dept_id or "dept_qa",
        "role": req.role or UserRole.TESTER,
        "created_at": datetime.now().isoformat(),
    }
    users.append(new_user)
    write_json(USERS_FILE, users)

    record_audit(
        operator=current_user.get("username", "admin"),
        action="新建用户账号",
        module="用户与权限",
        action_type="create",
        target=req.username,
        details=f"新建账号 [{req.username}] (昵称: {new_user['nickname']}, 角色: {new_user['role']}, 归属部门: {new_user['dept_id']})",
    )

    return {
        "code": 200,
        "msg": f"用户 [{req.username}] 创建成功",
        "data": enrich_user_dept(new_user),
    }


@router.put("/users/{username}", summary="更新用户信息")
async def update_user(
    username: str,
    req: UpdateUserRequest,
    current_user: dict = Depends(require_admin),
):
    users = read_json(USERS_FILE, default=[])
    target = next((u for u in users if u["username"] == username), None)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 部门主管只能修改本部门用户，且不能修改超管
    if not is_super_admin(current_user):
        if target.get("dept_id") != current_user.get("dept_id"):
            raise HTTPException(status_code=403, detail="无权修改其他部门的用户")
        if target.get("role") in [UserRole.SUPER_ADMIN, "admin"]:
            raise HTTPException(status_code=403, detail="无权修改超级管理员")
        if req.dept_id and req.dept_id != current_user.get("dept_id"):
            raise HTTPException(status_code=403, detail="无权将用户转移至其他部门")

    changes = []
    if req.nickname is not None and req.nickname != target.get("nickname"):
        changes.append(f"昵称由 '{target.get('nickname')}' 改为 '{req.nickname}'")
        target["nickname"] = req.nickname
    if req.dept_id is not None and req.dept_id != target.get("dept_id"):
        changes.append(f"部门由 '{target.get('dept_id')}' 调至 '{req.dept_id}'")
        target["dept_id"] = req.dept_id
    if req.role is not None and req.role != target.get("role"):
        changes.append(f"角色由 '{target.get('role')}' 调整为 '{req.role}'")
        target["role"] = req.role
    if req.password:
        changes.append("重置了登录密码")
        target["password_hash"] = hash_password(req.password)

    write_json(USERS_FILE, users)

    record_audit(
        operator=current_user.get("username", "admin"),
        action="修改用户资料/角色",
        module="用户与权限",
        action_type="update",
        target=username,
        details=f"修改了用户 [{username}]: " + ("; ".join(changes) if changes else "属性更新"),
    )

    return {
        "code": 200,
        "msg": f"用户 [{username}] 信息已更新",
        "data": enrich_user_dept(target),
    }


@router.delete("/users/{username}", summary="删除用户")
async def delete_user(username: str, current_user: dict = Depends(require_admin)):
    if username == "admin":
        raise HTTPException(status_code=400, detail="不能删除默认超级管理员")
    if username == current_user["username"]:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")

    users = read_json(USERS_FILE, default=[])
    target = next((u for u in users if u["username"] == username), None)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 部门主管权限控制
    if not is_super_admin(current_user):
        if target.get("dept_id") != current_user.get("dept_id"):
            raise HTTPException(status_code=403, detail="无权删除其他部门的用户")

    new_users = [u for u in users if u["username"] != username]
    write_json(USERS_FILE, new_users)

    record_audit(
        operator=current_user.get("username", "admin"),
        action="删除用户账号",
        module="用户与权限",
        action_type="delete",
        target=username,
        details=f"永久删除了用户账号 [{username}] (角色: {target.get('role')}, 部门: {target.get('dept_id')})",
    )

    return {"code": 200, "msg": f"用户 [{username}] 已删除"}
