"""
统一任务运行器：
  - 用 threading.Thread 在后台执行子进程
  - 实时捕获 stdout/stderr 并追加到结果文件
  - 通过 WebSocket 管理器广播日志
  - 具备智能看门狗：活跃任务注册表、超时智能终止、服务重启孤儿任务自动自愈
"""
import os
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import TASKS_FILE
from app.db.json_store import append_to_list, update_in_list, read_json, write_json
from app.models.schemas import TaskStatus
from app.ws.manager import ws_manager  # WebSocket 广播

# 单任务最大超时时间（秒），默认 5 分钟
DEFAULT_TASK_TIMEOUT = 300

# 内存活跃任务注册表: task_id -> {"proc": proc, "started_at": datetime, "thread": thread, "result_file": result_file}
_ACTIVE_TASKS: Dict[str, dict] = {}
_ACTIVE_LOCK = threading.Lock()


def _new_task_id() -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"t-{ts}-{short}"


def _result_path(module: str, task_id: str, results_dir: Path) -> Path:
    return results_dir / f"{task_id}.json"


def auto_heal_zombie_tasks() -> List[str]:
    """
    智能巡检与自愈修复僵尸 running 任务：
    1. 若 tasks.json 中的任务状态为 'running'，但不在当前系统活跃运行表 _ACTIVE_TASKS 中（说明因服务重启或进程断开已丢失），立即自愈为 'failed'。
    2. 若任务运行时间已超过设定阈值（DEFAULT_TASK_TIMEOUT），立即强制终止并判定为 'failed'。
    """
    healed_ids = []
    all_tasks = read_json(TASKS_FILE, default=[])
    if not all_tasks:
        return healed_ids

    now = datetime.now()
    changed = False

    with _ACTIVE_LOCK:
        for t in all_tasks:
            if t.get("status") == TaskStatus.RUNNING:
                task_id = t.get("task_id")
                is_active = task_id in _ACTIVE_TASKS
                
                # 检查是否超时
                is_timeout = False
                started_at_str = t.get("started_at")
                if started_at_str:
                    try:
                        started_dt = datetime.fromisoformat(started_at_str)
                        if (now - started_dt).total_seconds() > DEFAULT_TASK_TIMEOUT:
                            is_timeout = True
                    except Exception:
                        pass

                # 判定条件：不在内存活跃运行列表中，或者已严重超时
                if not is_active or is_timeout:
                    fail_reason = (
                        "[智能自愈] 检测到任务执行超时（超过 300s），系统已自动终止并标记为 failed"
                        if is_timeout
                        else "[智能自愈] 检测到任务未在活跃进程中运行（服务曾重启或进程异常中断），系统已智能将其标记为 failed"
                    )

                    # 如果活跃表中存在超时的进程，强行 kill
                    if is_active:
                        proc = _ACTIVE_TASKS[task_id].get("proc")
                        if proc and proc.poll() is None:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                        _ACTIVE_TASKS.pop(task_id, None)

                    finished_at = now.isoformat()
                    t["status"] = TaskStatus.FAILED
                    t["finished_at"] = finished_at
                    changed = True
                    healed_ids.append(task_id)

                    # 更新结果文件
                    res_file = t.get("result_file")
                    if res_file and Path(res_file).exists():
                        try:
                            res_data = read_json(Path(res_file), default={})
                            res_data["status"] = TaskStatus.FAILED
                            res_data["finished_at"] = finished_at
                            logs = res_data.get("logs", [])
                            logs.append(fail_reason)
                            res_data["logs"] = logs
                            write_json(Path(res_file), res_data)
                        except Exception:
                            pass

                    # 广播通知 WebSocket 客户端
                    ws_manager.broadcast_sync(
                        task_id,
                        {"type": "log", "data": fail_reason},
                    )
                    ws_manager.broadcast_sync(
                        task_id,
                        {"type": "done", "status": TaskStatus.FAILED, "return_code": -1},
                    )

    if changed:
        write_json(TASKS_FILE, all_tasks)

    return healed_ids


def stop_task(task_id: str) -> bool:
    """手动停止/强制终止指定运行中的任务"""
    with _ACTIVE_LOCK:
        if task_id in _ACTIVE_TASKS:
            proc = _ACTIVE_TASKS[task_id].get("proc")
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            _ACTIVE_TASKS.pop(task_id, None)

    # 将任务状态标记为 failed
    finished_at = datetime.now().isoformat()
    stop_msg = "[用户操作] 任务已被手动强制终止并标记为 failed"
    update_in_list(
        TASKS_FILE,
        key="task_id",
        value=task_id,
        updates={"status": TaskStatus.FAILED, "finished_at": finished_at},
    )

    all_tasks = read_json(TASKS_FILE, default=[])
    target_task = next((t for t in all_tasks if t.get("task_id") == task_id), None)
    if target_task and target_task.get("result_file"):
        res_path = Path(target_task["result_file"])
        if res_path.exists():
            res_data = read_json(res_path, default={})
            res_data["status"] = TaskStatus.FAILED
            res_data["finished_at"] = finished_at
            logs = res_data.get("logs", [])
            logs.append(stop_msg)
            res_data["logs"] = logs
            write_json(res_path, res_data)

    ws_manager.broadcast_sync(task_id, {"type": "log", "data": stop_msg})
    ws_manager.broadcast_sync(task_id, {"type": "done", "status": TaskStatus.FAILED, "return_code": -1})
    return True


def _stream_process(
    proc: subprocess.Popen,
    task_id: str,
    result_file: Path,
    log_buffer: list,
):
    """读取进程输出，实时写入 log_buffer 并通过 WebSocket 广播"""
    try:
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            log_buffer.append(line)
            # 广播给所有订阅该 task_id 的 WebSocket 客户端
            ws_manager.broadcast_sync(task_id, {"type": "log", "data": line})

        proc.wait(timeout=DEFAULT_TASK_TIMEOUT)
        return_code = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        return_code = -1
        timeout_msg = f"[超时错误] 任务运行超过 {DEFAULT_TASK_TIMEOUT} 秒，已自动终止并判定为 failed"
        log_buffer.append(timeout_msg)
        ws_manager.broadcast_sync(task_id, {"type": "log", "data": timeout_msg})
    except Exception as e:
        return_code = -1
        err_line = f"[进程读取异常] {str(e)}"
        log_buffer.append(err_line)

    status = TaskStatus.SUCCESS if return_code == 0 else TaskStatus.FAILED
    finished_at = datetime.now().isoformat()

    # 从活跃任务列表中移除
    with _ACTIVE_LOCK:
        _ACTIVE_TASKS.pop(task_id, None)

    # 更新结果文件
    result_data = read_json(result_file, default={})
    result_data.update(
        {
            "status": status,
            "finished_at": finished_at,
            "return_code": return_code,
            "logs": log_buffer,
        }
    )
    write_json(result_file, result_data)

    # 更新 tasks.json
    update_in_list(
        TASKS_FILE,
        key="task_id",
        value=task_id,
        updates={"status": status, "finished_at": finished_at},
    )

    # 通知 WebSocket 客户端任务结束
    ws_manager.broadcast_sync(
        task_id,
        {"type": "done", "status": status, "return_code": return_code},
    )


def run_task(
    module: str,
    cases: List[str],
    cmd: List[str],
    results_dir: Path,
    triggered_by: str,
    cwd: Optional[Path] = None,
    extra_info: Optional[dict] = None,
) -> str:
    """创建并启动后台任务，返回 task_id"""
    task_id = _new_task_id()
    started_at = datetime.now().isoformat()
    result_file = _result_path(module, task_id, results_dir)

    task_record = {
        "task_id": task_id,
        "module": module,
        "cases": cases,
        "status": TaskStatus.RUNNING,
        "started_at": started_at,
        "finished_at": None,
        "result_file": str(result_file),
        "triggered_by": triggered_by,
        **(extra_info or {}),
    }

    # 初始结果文件
    write_json(result_file, {**task_record, "logs": []})
    # 写入任务列表
    append_to_list(TASKS_FILE, task_record)

    log_buffer: list = []

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(cwd or results_dir.parent),
            )
            with _ACTIVE_LOCK:
                _ACTIVE_TASKS[task_id] = {
                    "proc": proc,
                    "started_at": datetime.now(),
                    "result_file": result_file,
                }
            _stream_process(proc, task_id, result_file, log_buffer)
        except Exception as e:
            with _ACTIVE_LOCK:
                _ACTIVE_TASKS.pop(task_id, None)
            err_msg = f"[启动异常] 无法启动测试进程: {e}"
            log_buffer.append(err_msg)
            ws_manager.broadcast_sync(task_id, {"type": "log", "data": err_msg})
            ws_manager.broadcast_sync(task_id, {"type": "done", "status": TaskStatus.FAILED})
            write_json(
                result_file,
                {**task_record, "status": TaskStatus.FAILED, "logs": log_buffer},
            )
            update_in_list(
                TASKS_FILE,
                key="task_id",
                value=task_id,
                updates={
                    "status": TaskStatus.FAILED,
                    "finished_at": datetime.now().isoformat(),
                },
            )

    thread = threading.Thread(target=_run, name=f"task-{task_id}", daemon=True)
    thread.start()

    return task_id
