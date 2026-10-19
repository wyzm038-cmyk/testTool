"""性能测试路由（k6）：脚本列表 / 详情 / 增删改 / 运行 / 任务历史"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user
from app.core.config import TASKS_FILE
from app.db.json_store import find_in_list, read_json
from app.models.schemas import (
    RunPerfRequest,
    CreatePerfCaseRequest,
    UpdatePerfCaseRequest,
    UpdateCaseMetaRequest,
)
from app.services.case_meta_service import save_case_meta
from app.services.perf_service import (
    scan_perf_cases,
    start_perf_run,
    get_perf_case_detail,
    create_perf_case,
    update_perf_case,
    delete_perf_case,
)

router = APIRouter(prefix="/perf", tags=["Performance Test"])


@router.get("/cases", summary="获取性能测试脚本列表")
async def list_cases(_: dict = Depends(get_current_user)):
    return scan_perf_cases()


@router.put("/cases/meta", summary="更新性能压测脚本元数据（优先级、标签、负责人）")
async def update_perf_case_meta(
    req: UpdateCaseMetaRequest,
    _: dict = Depends(get_current_user),
):
    save_case_meta(
        case_id=req.case_id,
        priority=req.priority,
        tags=req.tags,
        owner=req.owner,
    )
    return {"code": 200, "message": "性能脚本元数据更新成功", "data": req.dict()}


@router.get("/cases/{file:path}", summary="获取单个性能测试脚本详情与代码")
async def get_case(file: str, _: dict = Depends(get_current_user)):
    return get_perf_case_detail(file)


@router.post("/cases", summary="新建性能测试脚本")
async def create_case(req: CreatePerfCaseRequest, _: dict = Depends(get_current_user)):
    return create_perf_case(req)


@router.put("/cases", summary="保存更新性能测试脚本代码")
async def update_case(req: UpdatePerfCaseRequest, _: dict = Depends(get_current_user)):
    return update_perf_case(req)


@router.delete("/cases/{file:path}", summary="删除性能测试脚本")
async def delete_case(file: str, _: dict = Depends(get_current_user)):
    return delete_perf_case(file)


@router.post("/run", summary="运行性能测试脚本")
async def run_perf(req: RunPerfRequest, current_user: dict = Depends(get_current_user)):
    try:
        task_id = start_perf_run(req, triggered_by=current_user["username"])
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"task_id": task_id, "message": "任务已启动"}


@router.get("/tasks", summary="性能测试任务历史")
async def list_tasks(_: dict = Depends(get_current_user)):
    from app.services.runner import auto_heal_zombie_tasks
    auto_heal_zombie_tasks()
    all_tasks = read_json(TASKS_FILE, default=[])
    return [t for t in all_tasks if t.get("module") == "perf"]


@router.get("/tasks/{task_id}", summary="性能测试任务详情")
async def get_task(task_id: str, _: dict = Depends(get_current_user)):
    from app.services.runner import auto_heal_zombie_tasks
    auto_heal_zombie_tasks()
    task = find_in_list(TASKS_FILE, "task_id", task_id)
    if not task or task.get("module") != "perf":
        raise HTTPException(status_code=404, detail="任务不存在")

    detail = dict(task)
    result_file = task.get("result_file")
    if result_file:
        result_data = read_json(Path(result_file), default={})
        detail["logs"] = result_data.get("logs", [])
        detail["summary"] = result_data.get("summary")

    return detail
