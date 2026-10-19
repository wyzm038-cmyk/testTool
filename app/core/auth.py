"""
企业级认证、组织架构部门与 RBAC 权限系统：
- 部门隔离：不同的部门下的用户看不到别的部门的用例
- 多级角色：super_admin（超级管理员）、dept_admin（部门主管）、tester（测试工程师）、viewer（只读观察员）
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    DEPARTMENTS_FILE,
    SECRET_KEY,
    USERS_FILE,
)
from app.db.json_store import read_json, write_json
from app.models.schemas import UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── 密码与 Token 工具 ─────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── 组织架构与部门工具 ────────────────────────────────────────────────────────

DEFAULT_DEPARTMENTS = [
    {
        "id": "dept_qa",
        "code": "qa",
        "name": "质量保障中心 (QA)",
        "description": "负责整机集成测试、核心回归与发布前质量门禁",
        "created_at": "2026-10-16T12:00:00",
    },
    {
        "id": "dept_fin",
        "code": "fin",
        "name": "核心金融研发部",
        "description": "负责清结算中台、支付网关、账户及风控系统",
        "created_at": "2026-10-16T12:00:00",
    },
    {
        "id": "dept_mall",
        "code": "mall",
        "name": "电商平台研发部",
        "description": "负责商品中台、购物车交易、促销及订单履约",
        "created_at": "2026-10-16T12:00:00",
    },
    {
        "id": "dept_ops",
        "code": "ops",
        "name": "基础设施运维部",
        "description": "负责微服务高可用、容器编排与集群观测监控",
        "created_at": "2026-10-16T12:00:00",
    },
]


def init_default_departments():
    """初始化预设部门组织架构"""
    depts = read_json(DEPARTMENTS_FILE, default=[])
    if not depts:
        write_json(DEPARTMENTS_FILE, DEFAULT_DEPARTMENTS)
        print("[AUTH] 默认组织架构部门初始化完成")


def get_departments() -> List[dict]:
    init_default_departments()
    return read_json(DEPARTMENTS_FILE, default=DEFAULT_DEPARTMENTS)


def get_department_by_id(dept_id: str) -> Optional[dict]:
    depts = get_departments()
    return next((d for d in depts if d["id"] == dept_id), None)


def get_department_by_code(code: str) -> Optional[dict]:
    depts = get_departments()
    return next((d for d in depts if d["code"].lower() == code.lower()), None)


def enrich_user_dept(user: dict) -> dict:
    """关联用户的部门信息"""
    dept_id = user.get("dept_id") or "dept_qa"
    dept = get_department_by_id(dept_id)
    enriched = dict(user)
    enriched["dept_id"] = dept_id
    if dept:
        enriched["dept_name"] = dept["name"]
        enriched["dept_code"] = dept["code"]
    else:
        enriched["dept_name"] = "质量保障中心 (QA)"
        enriched["dept_code"] = "qa"

    # 规范化 role：如果是旧的 admin 转为 super_admin
    role = enriched.get("role", UserRole.TESTER)
    if role == "admin":
        role = UserRole.SUPER_ADMIN
    enriched["role"] = role

    return enriched


# ── 用户工具 ──────────────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> Optional[dict]:
    users = read_json(USERS_FILE, default=[])
    raw_user = next((u for u in users if u["username"] == username), None)
    if raw_user:
        return enrich_user_dept(raw_user)
    return None


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return user


# ── FastAPI 依赖与权限控制 ───────────────────────────────────────────────────

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    username: str = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token 凭证无效")
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def is_super_admin(user: dict) -> bool:
    """是否平台超级管理员"""
    return user.get("role") in [UserRole.SUPER_ADMIN, "admin"]


def is_dept_admin(user: dict) -> bool:
    """是否部门主管或超级管理员"""
    return is_super_admin(user) or user.get("role") == UserRole.DEPT_ADMIN


def require_super_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """要求平台超级管理员权限"""
    if not is_super_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="权限不足：该操作仅允许平台超级管理员 (super_admin) 执行",
        )
    return current_user


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """要求系统管理或部门主管权限（兼容旧 require_admin）"""
    if not is_dept_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="权限不足：需要管理员或部门主管权限",
        )
    return current_user


def check_case_department_access(current_user: dict, case_file: str) -> bool:
    """
    检查当前用户是否有权访问指定用例文件：
    - super_admin：可访问所有部门用例
    - 普通用户：只能访问所属部门路径或公共用例，禁止跨部门访问
    """
    if is_super_admin(current_user):
        return True

    user_dept_code = (current_user.get("dept_code") or "qa").lower()
    cleaned_file = case_file.replace("\\", "/").strip().lower()

    # 提取文件所在的一级目录代码
    parts = cleaned_file.split("/")
    if len(parts) > 1:
        file_dept_code = parts[0]
        # 公共用例所有部门可见
        if file_dept_code in ["public", "common"]:
            return True
        # 必须匹配本人部门代码
        if file_dept_code != user_dept_code:
            raise HTTPException(
                status_code=403,
                detail=f"数据权限隔离：您当前属于 [{current_user.get('dept_name')}]，无权访问其他部门 [{file_dept_code}] 的测试用例！",
            )
    else:
        # 根目录文件（如 test_example.py），默认归属于质量保障部 qa
        if user_dept_code != "qa":
            raise HTTPException(
                status_code=403,
                detail=f"数据权限隔离：该用例属于质量保障中心 (QA)，您所属部门为 [{current_user.get('dept_name')}]，禁止跨部门查看！",
            )

    return True


# ── 初始化组织架构与多部门用户 ────────────────────────────────────────────────

def init_default_admin():
    """首次启动时自动创建组织部门及多部门标准账号体系"""
    init_default_departments()

    users = read_json(USERS_FILE, default=[])

    # 预设标准中型企业用户矩阵
    default_users_matrix = [
        {
            "id": "u001",
            "username": "admin",
            "nickname": "系统总管理员",
            "password_hash": hash_password("admin123"),
            "role": UserRole.SUPER_ADMIN,
            "dept_id": "dept_qa",
            "created_at": datetime.now().isoformat(),
        },
        {
            "id": "u002",
            "username": "fin_lead",
            "nickname": "王主管 (金融研发)",
            "password_hash": hash_password("fin123"),
            "role": UserRole.DEPT_ADMIN,
            "dept_id": "dept_fin",
            "created_at": datetime.now().isoformat(),
        },
        {
            "id": "u003",
            "username": "mall_tester",
            "nickname": "李工 (电商测试)",
            "password_hash": hash_password("mall123"),
            "role": UserRole.TESTER,
            "dept_id": "dept_mall",
            "created_at": datetime.now().isoformat(),
        },
        {
            "id": "u004",
            "username": "qa_viewer",
            "nickname": "张工 (质量部观察员)",
            "password_hash": hash_password("qa123"),
            "role": UserRole.VIEWER,
            "dept_id": "dept_qa",
            "created_at": datetime.now().isoformat(),
        },
    ]

    changed = False
    existing_usernames = {u["username"] for u in users}

    # 更新或补充预设用户
    for u in default_users_matrix:
        if u["username"] not in existing_usernames:
            users.append(u)
            changed = True
        else:
            # 同步更新现有 admin 的 dept_id 和 role 结构
            for ex in users:
                if ex["username"] == u["username"]:
                    if "dept_id" not in ex:
                        ex["dept_id"] = u["dept_id"]
                        changed = True
                    if ex.get("role") == "admin":
                        ex["role"] = UserRole.SUPER_ADMIN
                        changed = True
                    if "nickname" not in ex:
                        ex["nickname"] = u["nickname"]
                        changed = True

    if changed or not users:
        write_json(USERS_FILE, users)
        print("[AUTH] 中型软件公司组织架构与多部门用户已就绪:")
        print("  - 超级管理员: admin / admin123 (跨部门所有权限)")
        print("  - 金融部主管: fin_lead / fin123 (专属金融部门)")
        print("  - 电商测试员: mall_tester / mall123 (专属电商部门)")
        print("  - 质量观察员: qa_viewer / qa123 (专属质量部门，只读)")
