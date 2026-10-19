"""
性能测试服务：基于 k6
  - 扫描 testcases/perf/ 下所有 *.js 脚本文件
  - 支持模块分类与友好名称识别（如 百度压测、API网关压测、电商高并发链路压测）
  - 提供脚本查看源码、在线编辑、安全删除、新建脚本
  - 构建 k6 run 命令并通过 runner 执行
"""
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import HTTPException

from app.core.config import PERF_CASES_DIR, PERF_RESULTS_DIR
from app.models.schemas import (
    PerfCase,
    PerfCaseDetail,
    CreatePerfCaseRequest,
    UpdatePerfCaseRequest,
    RunPerfRequest,
)
from app.services.runner import run_task
from app.services.case_meta_service import get_case_meta, save_case_meta

PERF_FOLDER_NAME_MAP = {
    "baidu": "百度检索性能压测",
    "api_gateway": "API 网关吞吐压测",
    "ecommerce": "电商高并发链路压测",
    "mall": "商城业务高并发压测",
    "fin": "金融交易性能压测",
    "benchmark": "系统基准性能测试",
    "qa": "QA 自动化性能回归",
}


def _resolve_safe_file(rel_path: str) -> Path:
    clean = rel_path.strip().replace("\\", "/").lstrip("/")
    target = (PERF_CASES_DIR / clean).resolve()
    base = PERF_CASES_DIR.resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法的文件路径，禁止目录穿越")
    return target


def _extract_perf_module_info(js_file: Path, rel: str) -> Dict[str, Any]:
    parts = rel.split("/")
    folder = parts[0] if len(parts) > 1 else ""

    name = PERF_FOLDER_NAME_MAP.get(folder)
    desc = ""
    target_url = None
    default_vus = 10
    default_duration = "30s"

    try:
        content = js_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        # 提取第一行与第二行注释
        desc_lines = []
        for line in lines[:5]:
            trimmed = line.strip()
            if trimmed.startswith("//"):
                desc_lines.append(trimmed.lstrip("/ ").strip())
            elif trimmed.startswith("/*") or trimmed.startswith("*"):
                desc_lines.append(trimmed.lstrip("/* ").rstrip("*/").strip())
        if desc_lines:
            desc = "；".join([l for l in desc_lines if l])
            if not name and desc_lines[0]:
                name = desc_lines[0]

        # 尝试提取目标 URL
        url_match = re.search(r'http\.(?:get|post|put)\(\s*["\']([^"\']+)["\']', content)
        if url_match:
            target_url = url_match.group(1)

        # 尝试提取默认 vus / duration
        vus_match = re.search(r'vus\s*:\s*(\d+)', content)
        if vus_match:
            default_vus = int(vus_match.group(1))
        duration_match = re.search(r'duration\s*:\s*["\']([^"\']+)["\']', content)
        if duration_match:
            default_duration = duration_match.group(1)
    except Exception:
        pass

    if not name:
        if folder:
            name = PERF_FOLDER_NAME_MAP.get(folder, folder.replace("_", " ").title() + " 压测")
        else:
            stem = js_file.stem.replace("test_", "").replace("_", " ").title()
            name = f"{stem} 压测脚本"

    return {
        "name": name,
        "folder": folder or js_file.stem,
        "description": desc,
        "target_url": target_url,
        "default_vus": default_vus,
        "default_duration": default_duration,
    }


def scan_perf_cases() -> List[PerfCase]:
    """扫描 testcases/perf/ 下所有 .js 脚本文件，解析友好模块名称与描述"""
    cases = []
    if not PERF_CASES_DIR.exists():
        PERF_CASES_DIR.mkdir(parents=True, exist_ok=True)

    for js_file in sorted(PERF_CASES_DIR.rglob("*.js")):
        rel = js_file.relative_to(PERF_CASES_DIR).as_posix()
        info = _extract_perf_module_info(js_file, rel)
        meta = get_case_meta(rel, {"module": "perf"})
        cases.append(
            PerfCase(
                file=rel,
                name=info["name"],
                folder=info["folder"],
                description=info["description"],
                priority=meta.get("priority", "P1"),
                tags=meta.get("tags", []),
                owner=meta.get("owner", "tester"),
                target_url=info["target_url"],
                default_vus=info["default_vus"],
                default_duration=info["default_duration"],
            )
        )
    return cases


def get_perf_case_detail(file: str) -> PerfCaseDetail:
    """获取单个压测脚本的详情与完整源码"""
    path = _resolve_safe_file(file)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"压测脚本不存在: {file}")

    content = path.read_text(encoding="utf-8")
    info = _extract_perf_module_info(path, file)
    meta = get_case_meta(file, {"module": "perf"})

    return PerfCaseDetail(
        file=file,
        name=info["name"],
        folder=info["folder"],
        description=info["description"],
        priority=meta.get("priority", "P1"),
        tags=meta.get("tags", []),
        owner=meta.get("owner", "tester"),
        code=content,
        target_url=info["target_url"],
        default_vus=info["default_vus"],
        default_duration=info["default_duration"],
    )


def create_perf_case(req: CreatePerfCaseRequest) -> dict:
    """创建新的 k6 性能测试脚本"""
    rel_path = req.file.strip().replace("\\", "/").lstrip("/")
    if not rel_path.endswith(".js"):
        rel_path += ".js"

    target_path = _resolve_safe_file(rel_path)
    if target_path.exists():
        raise HTTPException(status_code=400, detail=f"脚本文件已存在: {rel_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)

    code = req.code
    if not code:
        url = req.target_url or "https://jsonplaceholder.typicode.com/posts"
        desc = req.description or "接口并发基准测试"
        code = f"""// {desc}
// 自动生成的 k6 高性能负载压测脚本

import http from "k6/http";
import {{ check, sleep }} from "k6";
import {{ Rate }} from "k6/metrics";

const errorRate = new Rate("errors");

export const options = {{
  vus: {req.vus or 10},
  duration: "{req.duration or '30s'}",
  thresholds: {{
    http_req_duration: ["p(95)<800"], // 95% 请求在 800ms 内完成
    errors: ["rate<0.05"],             // 错误率低于 5%
  }},
}};

export default function () {{
  const res = http.get("{url}");

  const success = check(res, {{
    "status is 200": (r) => r.status === 200,
    "response time < 1000ms": (r) => r.timings.duration < 1000,
  }});

  errorRate.add(!success);
  sleep(1);
}}
"""
    target_path.write_text(code, encoding="utf-8")
    save_case_meta(
        case_id=rel_path,
        priority=req.priority or "P1",
        tags=req.tags if req.tags is not None else ["高并发压测"],
        owner=req.owner or "tester"
    )
    return {"message": "创建压测脚本成功", "file": rel_path}


def update_perf_case(req: UpdatePerfCaseRequest) -> dict:
    """在线保存/更新性能压测脚本源码"""
    path = _resolve_safe_file(req.file)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"压测脚本不存在: {req.file}")

    path.write_text(req.code, encoding="utf-8")
    return {"message": "保存脚本成功", "file": req.file}


def delete_perf_case(file: str) -> dict:
    """删除性能测试脚本文件"""
    path = _resolve_safe_file(file)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"压测脚本不存在: {file}")

    path.unlink()
    # 如果父目录为空，则清理父目录
    try:
        parent = path.parent
        if parent != PERF_CASES_DIR and not any(parent.iterdir()):
            parent.rmdir()
    except Exception:
        pass

    return {"message": f"成功删除脚本 {file}"}


def _find_k6() -> str:
    """查找 k6 可执行文件，多路径智能探测"""
    k6 = shutil.which("k6")
    if k6:
        return k6

    candidates = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "k6" / "k6.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "k6" / "k6.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "k6" / "k6.exe",
        Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "k6.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    raise FileNotFoundError(
        "未找到 k6 可执行文件，系统正在安装或请访问 https://k6.io/docs/get-started/installation/ 安装 k6。"
    )


def start_perf_run(req: RunPerfRequest, triggered_by: str) -> str:
    """
    启动 k6 性能测试，返回 task_id。
    """
    k6_bin = _find_k6()
    script_path = PERF_CASES_DIR / req.script

    if not script_path.exists():
        raise FileNotFoundError(f"脚本不存在: {req.script}")

    cmd = [
        k6_bin, "run",
        "--vus", str(req.vus),
        "--duration", req.duration,
        "--no-color",
        str(script_path),
    ]

    # 注入环境变量 (-e KEY=VALUE)
    if req.env:
        for k, v in req.env.items():
            cmd.extend(["-e", f"{k}={v}"])

    extra_info = {
        "script": req.script,
        "vus": req.vus,
        "duration": req.duration,
    }

    return run_task(
        module="perf",
        cases=[req.script],
        cmd=cmd,
        results_dir=PERF_RESULTS_DIR,
        triggered_by=triggered_by,
        cwd=PERF_CASES_DIR,
        extra_info=extra_info,
    )
