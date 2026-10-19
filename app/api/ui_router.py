"""UI 测试路由：用例列表 / 详情 / 编辑 / 删除 / 运行 / 任务历史"""
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.config import TASKS_FILE, UI_RESULTS_DIR
from app.core.audit import record_audit
from app.db.json_store import find_in_list, read_json
from app.models.schemas import RunUiRequest, TaskDetail, UpdateCaseMetaRequest
from app.services.case_meta_service import save_case_meta
from app.services.ui_service import (
    scan_ui_cases,
    start_ui_run,
    get_ui_case_detail,
    update_ui_case_file,
    delete_ui_case,
    create_ui_case,
    CreateUiCaseRequest,
)
import ast

router = APIRouter(prefix="/ui", tags=["UI Test"])


class UpdateCodeRequest(BaseModel):
    file: str
    code: str


class ValidateCodeRequest(BaseModel):
    code: str


@router.post("/cases/validate", summary="实时校验 Python UI 测试代码语法")
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


@router.get("/cases", summary="获取 UI 测试用例列表")
async def list_cases(_: dict = Depends(get_current_user)):
    return scan_ui_cases()


@router.get("/cases/detail", summary="获取 UI 用例文件或单函数详细代码")
async def case_detail(
    file: str = Query(..., description="用例相对路径"),
    function: Optional[str] = Query(None, description="测试函数名"),
    _: dict = Depends(get_current_user),
):
    return get_ui_case_detail(file, function)


@router.post("/cases", summary="新建或追加 UI 测试用例")
async def add_case(req: CreateUiCaseRequest, current_user: dict = Depends(get_current_user)):
    res = create_ui_case(req)
    record_audit(
        operator=current_user.get("username", "tester"),
        action="创建UI用例",
        module="UI测试",
        action_type="create",
        target=f"{req.file}::{req.function_name}",
        details=f"创建了 UI 测试用例 [{req.function_name}]",
    )
    return res


@router.put("/cases/code", summary="在线更新 UI 测试用例文件代码")
async def save_case_code(req: UpdateCodeRequest, current_user: dict = Depends(get_current_user)):
    res = update_ui_case_file(req.file, req.code)
    record_audit(
        operator=current_user.get("username", "tester"),
        action="更新UI用例代码",
        module="UI测试",
        action_type="update",
        target=req.file,
        details=f"在线修改并更新了 UI 测试用例文件 [{req.file}] 源码",
    )
    return res


@router.delete("/cases", summary="删除 UI 测试用例函数或测试文件")
async def remove_case(
    file: str = Query(...),
    function: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    res = delete_ui_case(file, function)
    record_audit(
        operator=current_user.get("username", "tester"),
        action="删除UI用例",
        module="UI测试",
        action_type="delete",
        target=f"{file}{':' + function if function else ''}",
        details=f"删除了 UI 测试用例" + (f"函数 [{function}] 来自文件 [{file}]" if function else f"文件 [{file}]"),
    )
    return res


@router.put("/cases/meta", summary="更新 UI 用例元数据（优先级、标签、负责人）")
async def update_ui_case_meta(
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
        operator=current_user.get("username", "tester"),
        action="更新UI用例元属性",
        module="UI测试",
        action_type="update",
        target=req.case_id,
        details=f"更新优先级为 {req.priority}，负责人为 {req.owner}，标签: {', '.join(req.tags)}",
    )
    return {"code": 200, "message": "UI 用例元数据更新成功", "data": req.dict()}


@router.post("/run", summary="运行选中的 UI 测试用例")
async def run_cases(req: RunUiRequest, current_user: dict = Depends(get_current_user)):
    if not req.cases:
        raise HTTPException(status_code=400, detail="请至少选择一个用例")
    task_id = start_ui_run(req, triggered_by=current_user["username"])
    return {"task_id": task_id, "message": "任务已启动"}


@router.get("/tasks", summary="UI 测试任务历史")
async def list_tasks(_: dict = Depends(get_current_user)):
    from app.services.runner import auto_heal_zombie_tasks
    auto_heal_zombie_tasks()
    all_tasks = read_json(TASKS_FILE, default=[])
    return [t for t in all_tasks if t.get("module") == "ui"]


@router.get("/tasks/{task_id}", summary="UI 测试任务详情")
async def get_task(task_id: str, _: dict = Depends(get_current_user)):
    from app.services.runner import auto_heal_zombie_tasks
    auto_heal_zombie_tasks()
    task = find_in_list(TASKS_FILE, "task_id", task_id)
    if not task or task.get("module") != "ui":
        raise HTTPException(status_code=404, detail="任务不存在")

    result_file = task.get("result_file")
    detail = dict(task)
    if result_file:
        result_data = read_json(Path(result_file), default={})
        detail["logs"] = result_data.get("logs", [])
        detail["summary"] = result_data.get("summary")

    return detail


@router.post("/tasks/{task_id}/stop", summary="手动停止或终止 UI 测试任务")
async def abort_task(task_id: str, _: dict = Depends(get_current_user)):
    from app.services.runner import stop_task
    task = find_in_list(TASKS_FILE, "task_id", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    stop_task(task_id)
    return {"code": 200, "message": f"任务 [{task_id}] 已发送终止信号"}
