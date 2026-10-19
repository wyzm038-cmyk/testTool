"""
WebSocket 路由：ws://.../ws/tasks/{task_id}
客户端连接后实时接收任务日志，任务结束后收到 {"type":"done"} 消息。
"""
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.json_store import find_in_list, read_json
from app.core.config import TASKS_FILE
from app.ws.manager import ws_manager

router = APIRouter()


@router.websocket("/ws/tasks/{task_id}")
async def task_log_ws(task_id: str, ws: WebSocket):
    """
    订阅任务实时日志流。
    连接后立即推送历史日志（断线重连友好），后续实时推送新增日志。
    """
    task = find_in_list(TASKS_FILE, "task_id", task_id)
    if not task:
        await ws.accept()
        await ws.send_text(json.dumps({"type": "error", "data": "task not found"}))
        await ws.close()
        return

    await ws_manager.connect(task_id, ws)

    # 推送历史日志（应对页面刷新/断线重连）
    result_file = task.get("result_file")
    if result_file:
        from pathlib import Path
        data = read_json(Path(result_file), default={})
        for line in data.get("logs", []):
            await ws_manager.send(ws, {"type": "log", "data": line})

    # 如果任务已结束，直接发 done
    if task["status"] in ("success", "failed"):
        await ws_manager.send(
            ws,
            {"type": "done", "status": task["status"]},
        )
        await ws.close()
        return

    try:
        # 保持连接，等待客户端断开
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(task_id, ws)
