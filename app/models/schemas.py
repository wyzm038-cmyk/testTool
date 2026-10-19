from typing import Optional, List, Dict, Any
from pydantic import BaseModel


# ── 角色权限常量 ──────────────────────────────────────────────────────────────

class UserRole:
    SUPER_ADMIN = "super_admin"  # 平台超级管理员（跨所有部门）
    DEPT_ADMIN = "dept_admin"    # 部门主管（本部门最高管理权限）
    TESTER = "tester"            # 测试工程师（本部门读写运行）
    VIEWER = "viewer"            # 访客观察员（本部门只读）


# ── 部门组织架构 ──────────────────────────────────────────────────────────────

class Department(BaseModel):
    id: str                      # 如 dept_qa, dept_fin
    name: str                    # 如 质量保障部, 金融研发部
    code: str                    # 如 qa, fin, mall
    description: Optional[str] = None
    created_at: str


class CreateDepartmentRequest(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


class UpdateDepartmentRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# ── 环境配置与系统审计 ────────────────────────────────────────────────────────

class Environment(BaseModel):
    id: str                                  # 如 env_dev, env_test, env_staging, env_prod
    name: str                                # 如 开发联调环境 (DEV)
    code: str                                # 如 dev, test, staging, prod
    base_url: str                            # 如 https://dev-api.company.local
    description: Optional[str] = None
    headers: Optional[Dict[str, str]] = {}   # 默认网关请求头
    variables: Optional[Dict[str, str]] = {} # 环境变量字典
    is_default: bool = False                 # 是否平台默认激活环境
    created_at: str
    updated_at: Optional[str] = None


class CreateEnvironmentRequest(BaseModel):
    name: str
    code: str
    base_url: str
    description: Optional[str] = None
    headers: Optional[Dict[str, str]] = {}
    variables: Optional[Dict[str, str]] = {}
    is_default: bool = False


class UpdateEnvironmentRequest(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    description: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    variables: Optional[Dict[str, str]] = None
    is_default: Optional[bool] = None


class AuditLog(BaseModel):
    id: str
    operator: str
    action: str                                   # 如 "新建用户", "删除测试环境", "修改部门", "一键清空日志"
    module: str                                   # "用户与权限" | "组织架构" | "运行环境" | "测试用例" | "系统运维"
    action_type: str = "other"                    # "create" | "update" | "delete" | "clear" | "execute" | "other"
    target: Optional[str] = None                  # 目标对象标识/名称
    details: Optional[str] = None
    timestamp: str




# ── 认证与用户 ────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    id: str
    username: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    dept_id: Optional[str] = None
    dept_name: Optional[str] = None
    dept_code: Optional[str] = None
    role: str                    # super_admin | dept_admin | tester | viewer (兼容旧 admin)
    created_at: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    dept_id: Optional[str] = "dept_qa"
    role: str = UserRole.TESTER  # super_admin | dept_admin | tester | viewer


class UpdateUserRequest(BaseModel):
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    dept_id: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None



# ── 通用任务 ──────────────────────────────────────────────────────────────────

class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TaskBrief(BaseModel):
    task_id: str
    module: str                  # ui | api | perf
    cases: List[str]
    status: str
    started_at: str
    finished_at: Optional[str] = None
    triggered_by: str
    dept_id: Optional[str] = None
    dept_name: Optional[str] = None


class TaskDetail(TaskBrief):
    logs: List[str] = []
    summary: Optional[dict] = None


# ── 用例标签、优先级与负责人元数据 ──────────────────────────────────────────

class CaseMetaItem(BaseModel):
    priority: str = "P1"                   # P0, P1, P2, P3
    tags: List[str] = []                   # 标签列表，如 ["冒烟", "核心业务"]
    owner: str = "tester"                  # 负责人，如 "admin", "tester"


class UpdateCaseMetaRequest(BaseModel):
    case_id: str                           # 如 "baidu/test_baidu.py::test_search_title"
    priority: str = "P1"                   # P0, P1, P2, P3
    tags: List[str] = []
    owner: str = "tester"


# ── UI 测试 ──────────────────────────────────────────────────────────────────

class UiCase(BaseModel):
    file: str                              # 相对于 testcases/ui/ 的路径
    functions: List[str]                   # 解析出的测试函数名
    name: Optional[str] = None             # 友好模块或文件夹名称（如 "百度用例"、"QA Playground 靶场"）
    folder: Optional[str] = None           # 所属文件夹名（如 "baidu"）
    description: Optional[str] = None
    priority: Optional[str] = "P1"         # 默认最高优先级 (P0-P3)
    tags: Optional[List[str]] = []         # 标签集合
    owner: Optional[str] = "tester"        # 负责人
    cases_meta: Optional[Dict[str, Any]] = {} # 各单函数的具体元数据映射
    dept_code: Optional[str] = None
    dept_name: Optional[str] = None


class RunUiRequest(BaseModel):
    cases: List[str]                       # ["test_login.py::test_case1", ...]
    headed: bool = False                   # 是否有头模式


# ── API 测试 ─────────────────────────────────────────────────────────────────

class ApiCase(BaseModel):
    file: str
    functions: List[str]
    name: Optional[str] = None
    folder: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = "P1"
    tags: Optional[List[str]] = []
    owner: Optional[str] = "tester"
    cases_meta: Optional[Dict[str, Any]] = {}
    dept_code: Optional[str] = None
    dept_name: Optional[str] = None


class ApiCaseDetail(BaseModel):
    file: str
    function: Optional[str] = None
    docstring: Optional[str] = None
    code: str
    full_code: Optional[str] = None
    lineno: Optional[int] = None
    end_lineno: Optional[int] = None
    functions: Optional[List[dict]] = None
    priority: Optional[str] = "P1"
    tags: Optional[List[str]] = []
    owner: Optional[str] = "tester"
    dept_code: Optional[str] = None
    dept_name: Optional[str] = None


class CreateApiCaseRequest(BaseModel):
    file: str
    function_name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = "P1"
    tags: Optional[List[str]] = []
    owner: Optional[str] = "tester"
    code: Optional[str] = None
    method: Optional[str] = "GET"
    url: Optional[str] = None
    headers: Optional[dict] = None
    body: Optional[dict] = None
    expected_status: Optional[int] = 200
    assertions: Optional[List[str]] = None
    dept_code: Optional[str] = None        # 所属部门代码


class UpdateApiCaseCodeRequest(BaseModel):
    file: str
    code: str


class RunApiRequest(BaseModel):
    cases: List[str]                       # ["test_user_api.py::test_get_user", ...]
    env: Optional[str] = None              # 运行环境标识（可选）


# ── 性能测试 (k6) ─────────────────────────────────────────────────────────────

class PerfCase(BaseModel):
    file: str                              # 相对于 testcases/perf/ 的路径
    name: Optional[str] = None             # 友好模块/文件夹名称（如 "API 网关接口压测", "百度搜索吞吐压测"）
    folder: Optional[str] = None           # 所属文件夹名（如 "api_gateway", "baidu"）
    description: Optional[str] = None
    priority: Optional[str] = "P1"         # 优先级 P0-P3
    tags: Optional[List[str]] = []         # 标签
    owner: Optional[str] = "tester"        # 负责人
    target_url: Optional[str] = None
    default_vus: Optional[int] = 10
    default_duration: Optional[str] = "30s"
    dept_code: Optional[str] = None
    dept_name: Optional[str] = None


class PerfCaseDetail(BaseModel):
    file: str
    name: Optional[str] = None
    folder: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = "P1"
    tags: Optional[List[str]] = []
    owner: Optional[str] = "tester"
    code: str
    target_url: Optional[str] = None
    default_vus: Optional[int] = 10
    default_duration: Optional[str] = "30s"


class CreatePerfCaseRequest(BaseModel):
    file: str
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = "P1"
    tags: Optional[List[str]] = []
    owner: Optional[str] = "tester"
    code: Optional[str] = None
    target_url: Optional[str] = None
    vus: Optional[int] = 10
    duration: Optional[str] = "30s"


class UpdatePerfCaseRequest(BaseModel):
    file: str
    code: str
    description: Optional[str] = None


class RunPerfRequest(BaseModel):
    script: str                  # 脚本文件名，如 "script.js"
    vus: int = 10                # 虚拟用户数
    duration: str = "30s"        # 运行时长
    env: Optional[dict] = None   # 传给 k6 的环境变量
