"""
系统操作审计日志核心服务
负责对全平台重大写操作（新建、修改、删除、设为默认、一键清空等）进行合规审计留痕与检索。
"""
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from app.core.config import AUDIT_LOGS_FILE
from app.db.json_store import read_json, write_json


def record_audit(
    operator: str,
    action: str,
    module: str,
    action_type: str = "other",
    target: Optional[str] = None,
    details: Optional[str] = None,
) -> dict:
    """
    记录一条操作审计日志并持久化存储。
    
    :param operator: 操作人用户名
    :param action: 行为名称，如 '新建用户', '删除环境', '重置密码', '清空审计日志'
    :param module: 所属模块，如 '用户与权限', '组织架构', '运行环境', '接口测试', 'UI测试', '系统运维'
    :param action_type: 'create' | 'update' | 'delete' | 'clear' | 'execute' | 'other'
    :param target: 目标对象标识或名称，如 'tester_01', 'dev (开发联调环境)'
    :param details: 变动详细说明
    """
    logs = read_json(AUDIT_LOGS_FILE, default=[])

    log_entry = {
        "id": f"log_{uuid.uuid4().hex[:10]}",
        "operator": operator or "system",
        "action": action,
        "module": module,
        "action_type": action_type,
        "target": target or "",
        "details": details or "",
        "timestamp": datetime.now().isoformat(),
    }

    logs.insert(0, log_entry)

    # 保留最近 1000 条
    if len(logs) > 1000:
        logs = logs[:1000]

    write_json(AUDIT_LOGS_FILE, logs)
    return log_entry


def get_audit_logs(
    module: Optional[str] = None,
    action_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> Dict:
    """查询审计日志，支持按模块、操作类型、关键词筛选与统计汇总"""
    logs = read_json(AUDIT_LOGS_FILE, default=[])

    # 统计数据（基于全部历史日志）
    stats = {
        "total": len(logs),
        "create": sum(1 for l in logs if l.get("action_type") == "create"),
        "update": sum(1 for l in logs if l.get("action_type") == "update"),
        "delete": sum(1 for l in logs if l.get("action_type") == "delete"),
        "clear": sum(1 for l in logs if l.get("action_type") == "clear"),
    }

    filtered = logs
    if module and module != "all":
        filtered = [l for l in filtered if l.get("module") == module]

    if action_type and action_type != "all":
        filtered = [l for l in filtered if l.get("action_type") == action_type]

    if search:
        s = search.strip().lower()
        filtered = [
            l for l in filtered
            if s in l.get("operator", "").lower()
            or s in l.get("action", "").lower()
            or s in l.get("module", "").lower()
            or s in l.get("target", "").lower()
            or s in l.get("details", "").lower()
        ]

    return {
        "total": len(filtered),
        "logs": filtered[:limit],
        "stats": stats,
    }


def clear_audit_logs(operator: str) -> dict:
    """
    一键清空审计日志。
    企业安全合规要求：清空后仍保留本次【一键清空日志】的触发溯源记录，确保操作不可抵赖。
    """
    # 写入清空记录
    clear_record = {
        "id": f"log_{uuid.uuid4().hex[:10]}",
        "operator": operator,
        "action": "一键清空审计日志",
        "module": "系统运维",
        "action_type": "clear",
        "target": "全平台审计日志",
        "details": f"管理员 [{operator}] 执行了一键清空所有历史操作审计日志高危动作，旧记录已抹除重置",
        "timestamp": datetime.now().isoformat(),
    }

    # 抹除所有旧日志，仅保留本次清空操作记录
    write_json(AUDIT_LOGS_FILE, [clear_record])
    return clear_record
