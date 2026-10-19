import ast
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.audit import record_audit
from app.core.auth import get_current_user, is_super_admin
from app.core.config import TASKS_FILE
from app.db.json_store import find_in_list, read_json
from app.models.schemas import (
    ApiCaseDetail,
    CreateApiCaseRequest,
    RunApiRequest,
    UpdateApiCaseCodeRequest,
    UpdateCaseMetaRequest,
)
from app.services.case_meta_service import save_case_meta
from app.services.api_service import (
    create_api_case,
    delete_api_case,
    get_case_detail,
    scan_api_cases,
    start_api_run,
    update_case_file,
)

router = APIRouter(prefix="/api-test", tags=["API Test"])


class ValidateCodeRequest(BaseModel):
    code: str


@router.post("/cases/validate", summary="实时校验 Python 代码语法")
async def validate_python_code(req: ValidateCodeRequest):
    code = req.code
    if not code.strip():
        return {"valid": True, "message": "代码为空"}
    try:
        ast.parse(code)
        return {"valid": True, "message": "Python 语法校验通过"}
    except SyntaxError as e:
        return {
            "valid": False,
            "lineno": e.lineno,
            "offset": e.offset,
            "text": e.text.strip() if e.text else "",
            "message": f"第 {e.lineno} 行语法错误: {e.msg}",
        }
    except Exception as e:
        return {
            "valid": False,
            "lineno": None,
            "offset": None,
            "text": "",
            "message": str(e),
        }


@router.get("/cases", summary="获取 API 测试用例列表")
async def list_cases(
    dept: Optional[str] = Query(None, description="按部门代码筛选（仅超级管理员有效）"),
    current_user: dict = Depends(get_current_user),
):
    return scan_api_cases(current_user=current_user, filter_dept=dept)


@router.get("/cases/detail", response_model=ApiCaseDetail, summary="查看 API 测试用例详情或代码")
async def read_case_detail(
    file: str = Query(..., description="用例文件名，如 fin/test_payment_api.py"),
    function: Optional[str] = Query(None, description="测试函数名，如 test_payment_gateway_health"),
    current_user: dict = Depends(get_current_user),
):
    return get_case_detail(file, function, current_user=current_user)


@router.post("/cases", summary="新建 API 测试用例")
async def create_case(
    req: CreateApiCaseRequest,
    current_user: dict = Depends(get_current_user),
):
    res = create_api_case(req, current_user=current_user)
    record_audit(
        operator=current_user.get("username", "tester"),
        action="新建接口用例",
        module="接口测试",
        action_type="create",
        target=f"{req.file}:{req.function_name or ''}",
        details=f"在用例集 [{req.file}] 中创建用例 [{req.title or req.function_name}]",
    )
    return res


@router.put("/cases/code", summary="保存/更新用例文件代码")
async def update_code(
    req: UpdateApiCaseCodeRequest,
    current_user: dict = Depends(get_current_user),
):
    res = update_case_file(req.file, req.code, current_user=current_user)
    record_audit(
        operator=current_user.get("username", "tester"),
        action="修改用例代码",
        module="接口测试",
        action_type="update",
        target=req.file,
        details=f"保存更新了接口测试用例文件 [{req.file}] 源代码",
    )
    return res


@router.delete("/cases", summary="删除用例文件或指定测试函数")
async def remove_case(
    file: str = Query(...),
    function: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    res = delete_api_case(file, function, current_user=current_user)
    record_audit(
        operator=current_user.get("username", "tester"),
        action="删除接口用例",
        module="接口测试",
        action_type="delete",
        target=f"{file}{':' + function if function else ''}",
        details=f"删除了接口用例" + (f"函数 [{function}] 来自文件 [{file}]" if function else f"文件 [{file}]"),
    )
    return res


@router.put("/cases/meta", summary="更新 API 用例元数据（优先级、标签、负责人）")
async def update_api_case_meta(
    req: UpdateCaseMetaRequest,
    current_user: dict = Depends(get_current_user),
):
    save_case_meta(
        case_id=req.case_id,
        priority=req.priority,
        tags=req.tags,
        owner=req.owner,
    )
    record_audit(
        operator=current_user.get("username", "anonymous"),
        action="更新用例元属性",
        module="接口测试",
        action_type="update",
        target=req.case_id,
        details=f"更新优先级为 {req.priority}，负责人为 {req.owner}，标签: {', '.join(req.tags)}",
    )
    return {"code": 200, "message": "用例元数据更新成功", "data": req.dict()}


@router.post("/run", summary="运行选中的 API 测试用例")
async def run_cases(req: RunApiRequest, current_user: dict = Depends(get_current_user)):
    if not req.cases:
        raise HTTPException(status_code=400, detail="请至少选择一个用例")
    task_id = start_api_run(req, current_user=current_user)
    return {"task_id": task_id, "message": "任务已启动"}


@router.get("/tasks", summary="API 测试任务历史")
async def list_tasks(current_user: dict = Depends(get_current_user)):
    from app.services.runner import auto_heal_zombie_tasks
    auto_heal_zombie_tasks()
    all_tasks = read_json(TASKS_FILE, default=[])
    api_tasks = [t for t in all_tasks if t.get("module") == "api"]

    # 部门任务数据隔离
    if is_super_admin(current_user):
        return api_tasks

    user_dept_id = current_user.get("dept_id")
    return [
        t for t in api_tasks
        if t.get("extra_info", {}).get("dept_id") == user_dept_id
        or t.get("triggered_by") == current_user.get("username")
    ]


@router.get("/tasks/{task_id}", summary="API 测试任务详情")
async def get_task(task_id: str, current_user: dict = Depends(get_current_user)):
    from app.services.runner import auto_heal_zombie_tasks
    auto_heal_zombie_tasks()
    task = find_in_list(TASKS_FILE, "task_id", task_id)
    if not task or task.get("module") != "api":
        raise HTTPException(status_code=404, detail="任务不存在")

    # 跨部门任务详情访问控制
    if not is_super_admin(current_user):
        task_dept = task.get("extra_info", {}).get("dept_id")
        user_dept_id = current_user.get("dept_id")
        if task_dept and task_dept != user_dept_id and task.get("triggered_by") != current_user.get("username"):
            raise HTTPException(
                status_code=403,
                detail=f"数据权限隔离：您无权查看其他部门的任务详情！",
            )

    detail = dict(task)
    result_file = task.get("result_file")
    if result_file:
        result_data = read_json(Path(result_file), default={})
        detail["logs"] = result_data.get("logs", [])
        detail["summary"] = result_data.get("summary")

    return detail


@router.post("/tasks/{task_id}/stop", summary="手动停止或终止 API 测试任务")
async def abort_task(task_id: str, current_user: dict = Depends(get_current_user)):
    from app.services.runner import stop_task
    task = find_in_list(TASKS_FILE, "task_id", task_id)
    if task and not is_super_admin(current_user):
        task_dept = task.get("extra_info", {}).get("dept_id")
        if task_dept and task_dept != current_user.get("dept_id") and task.get("triggered_by") != current_user.get("username"):
            raise HTTPException(status_code=403, detail="无权终止其他部门的任务")

    stop_task(task_id)
    return {
        "code": 200,
        "msg": "任务已成功终止并标记为 failed",
        "data": {"task_id": task_id},
    }
