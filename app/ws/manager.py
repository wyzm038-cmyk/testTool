"""
WebSocket 连接管理器：
  - 维护 task_id → List[WebSocket] 的订阅关系
  - broadcast_sync 在普通线程中安全地向协程发送消息
"""
import asyncio
import json
import threading
from collections import defaultdict
from typing import Dict, List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # task_id -> list of (loop, websocket)
        self._subs: Dict[str, List[tuple]] = defaultdict(list)
        self._lock = threading.Lock()

    async def connect(self, task_id: str, ws: WebSocket):
        await ws.accept()
        loop = asyncio.get_event_loop()
        with self._lock:
            self._subs[task_id].append((loop, ws))

    def disconnect(self, task_id: str, ws: WebSocket):
        with self._lock:
            self._subs[task_id] = [
                (lp, w) for lp, w in self._subs[task_id] if w is not ws
            ]

    async def send(self, ws: WebSocket, data: dict):
        try:
            await ws.send_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            pass

    def broadcast_sync(self, task_id: str, data: dict):
        """
        从普通线程（非 async 上下文）安全地广播消息。
        使用 asyncio.run_coroutine_threadsafe 将消息投递到对应事件循环。
        """
        with self._lock:
            targets = list(self._subs.get(task_id, []))
        for loop, ws in targets:
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.send(ws, data), loop)

    async def broadcast(self, task_id: str, data: dict):
        """在 async 上下文中广播"""
        with self._lock:
            targets = list(self._subs.get(task_id, []))
        for _, ws in targets:
            await self.send(ws, data)


ws_manager = ConnectionManager()
