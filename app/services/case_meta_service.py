"""
用例元数据管理服务：标签 (Tags)、优先级 (Priority: P0-P3)、负责人 (Owner)
  - 持久化至 storage/case_metadata.json
  - 具备智能默认推断机制（针对登录、支付、高并发等核心场景自动推断 P0/P1 和标签）
  - 支持单用例与批量查询、实时更新
"""
from typing import List, Dict, Any, Optional
from app.core.config import CASE_METADATA_FILE
from app.db.json_store import read_json, write_json


def _infer_default_meta(case_key: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """根据用例路径与名称智能推断合理的默认优先级、标签与负责人"""
    lower_key = case_key.lower()
    
    # 默认值
    priority = "P1"
    tags: List[str] = []
    owner = "tester"

    if context:
        if context.get("owner"):
            owner = context["owner"]
        if context.get("dept_code"):
            dept = context["dept_code"].lower()
            if dept in ["fin", "pay"]:
                owner = "finance_dev"
            elif dept == "mall":
                owner = "mall_dev"
            elif dept == "qa":
                owner = "qa_lead"

    # 1. 模块属性标签
    if "testcases/ui" in lower_key or lower_key.startswith("ui/") or "ui" in lower_key:
        tags.append("UI自动化")
    elif "testcases/api" in lower_key or lower_key.startswith("api/") or "api" in lower_key:
        tags.append("接口测试")
    elif "testcases/perf" in lower_key or lower_key.startswith("perf/") or ".js" in lower_key:
        tags.append("高并发压测")

    # 2. 核心级别与优先级判断
    if any(k in lower_key for k in ["login", "auth", "token", "payment", "pay", "checkout", "order_create"]):
        priority = "P0"
        tags.extend(["核心业务", "冒烟用例"])
        owner = "admin"
    elif any(k in lower_key for k in ["search", "query", "list", "detail", "status"]):
        priority = "P1"
        tags.append("回归用例")
    elif any(k in lower_key for k in ["challenge", "playground", "demo", "sample", "test_example"]):
        priority = "P2"
        tags.append("探索测试")
    else:
        priority = "P1"
        tags.append("功能测试")

    # 特殊网站分类补充
    if "baidu" in lower_key:
        tags.append("百度")
    elif "playground" in lower_key:
        tags.append("QA靶场")
    elif "mall" in lower_key:
        tags.append("商城系统")
    elif "fin" in lower_key:
        tags.append("金融系统")

    # 去重保留顺序
    unique_tags = list(dict.fromkeys(tags))
    return {
        "priority": priority,
        "tags": unique_tags,
        "owner": owner,
    }


def get_case_meta(case_key: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """获取指定用例的标签、优先级、负责人元数据"""
    data = read_json(CASE_METADATA_FILE, default={})
    if case_key in data:
        meta = data[case_key]
        return {
            "priority": meta.get("priority", "P1"),
            "tags": meta.get("tags", []),
            "owner": meta.get("owner", "tester"),
        }
    
    # 未单独设置过，生成智能推断默认值
    return _infer_default_meta(case_key, context)


def batch_get_cases_meta(case_keys: List[str], context: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """批量获取用例元数据字典"""
    stored_data = read_json(CASE_METADATA_FILE, default={})
    result = {}
    for key in case_keys:
        if key in stored_data:
            meta = stored_data[key]
            result[key] = {
                "priority": meta.get("priority", "P1"),
                "tags": meta.get("tags", []),
                "owner": meta.get("owner", "tester"),
            }
        else:
            result[key] = _infer_default_meta(key, context)
    return result


def save_case_meta(case_key: str, priority: str, tags: List[str], owner: str) -> Dict[str, Any]:
    """保存/更新单个测试用例的元数据"""
    clean_priority = priority.upper().strip()
    if clean_priority not in ["P0", "P1", "P2", "P3"]:
        clean_priority = "P1"

    clean_tags = [t.strip() for t in tags if t and t.strip()]
    clean_tags = list(dict.fromkeys(clean_tags))
    clean_owner = owner.strip() if owner and owner.strip() else "tester"

    data = read_json(CASE_METADATA_FILE, default={})
    meta_obj = {
        "priority": clean_priority,
        "tags": clean_tags,
        "owner": clean_owner,
    }
    data[case_key] = meta_obj
    write_json(CASE_METADATA_FILE, data)
    return meta_obj
