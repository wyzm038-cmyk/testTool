"""
UI 测试服务：基于 Playwright + pytest
  - 扫描 testcases/ui/ 目录，解析测试函数
  - 获取用例详情与源码、在线编辑、安全删除
  - 构建 pytest 命令运行选中用例
"""
import ast
import sys
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from pydantic import BaseModel

from app.core.config import UI_CASES_DIR, UI_RESULTS_DIR
from app.models.schemas import UiCase, RunUiRequest
from app.services.runner import run_task
from app.services.case_meta_service import get_case_meta, save_case_meta


class CreateUiCaseRequest(BaseModel):
    file: str
    function_name: str
    description: Optional[str] = "UI 自动化测试用例"
    priority: Optional[str] = "P1"
    tags: Optional[List[str]] = []
    owner: Optional[str] = "tester"
    code: Optional[str] = None
    target_url: Optional[str] = "https://www.example.com"


def _resolve_safe_file(rel_path: str) -> Path:
    clean = rel_path.strip().replace("\\", "/").lstrip("/")
    target = (UI_CASES_DIR / clean).resolve()
    base = UI_CASES_DIR.resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法的文件路径，禁止目录穿越")
    return target


def _normalize_filename(name: str) -> str:
    name = name.strip().replace("\\", "/").lstrip("/")
    if not name.endswith(".py"):
        name += ".py"
    if not Path(name).name.startswith("test_"):
        parts = name.split("/")
        parts[-1] = f"test_{parts[-1]}"
        name = "/".join(parts)
    return name


def _normalize_function_name(name: str) -> str:
    name = re.sub(r"[^\w]+", "_", name.strip()).strip("_")
    if not name.startswith("test_"):
        name = f"test_{name}"
FOLDER_NAME_MAP = {
    "baidu": "百度用例",
    "qa_playground": "QA Playground 实战靶场",
    "mall": "商城电商用例",
    "fin": "金融支付用例",
    "qa": "QA 质量回归",
}


def _extract_module_info(py_file: Path, rel: str) -> Dict[str, str]:
    parts = rel.split("/")
    folder = parts[0] if len(parts) > 1 else ""
    
    name = FOLDER_NAME_MAP.get(folder)
    desc = ""
    try:
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content)
        doc = ast.get_docstring(tree)
        if doc:
            first_line = doc.strip().splitlines()[0].strip()
            if not name and first_line:
                name = first_line
            desc = doc.strip()
    except Exception:
        pass

    if not name:
        if folder:
            name = FOLDER_NAME_MAP.get(folder, folder.replace("_", " ").title() + " 用例")
        else:
            stem = py_file.stem.replace("test_", "").replace("_", " ").title()
            name = f"{stem} 用例"

    return {"name": name, "folder": folder or py_file.stem, "description": desc}


def scan_ui_cases() -> List[UiCase]:
    """扫描 testcases/ui/ 下所有 test_*.py 文件，解析测试函数名与友好模块分类"""
    cases = []
    if not UI_CASES_DIR.exists():
        UI_CASES_DIR.mkdir(parents=True, exist_ok=True)

    for py_file in sorted(UI_CASES_DIR.rglob("test_*.py")):
        rel = py_file.relative_to(UI_CASES_DIR).as_posix()
        funcs = _extract_test_functions(py_file)
        info = _extract_module_info(py_file, rel)

        cases_meta = {}
        for fn in funcs:
            fn_key = f"{rel}::{fn}"
            cases_meta[fn] = get_case_meta(fn_key, {"module": "ui"})

        file_meta = get_case_meta(rel, {"module": "ui"})
        cases.append(UiCase(
            file=rel,
            functions=funcs,
            name=info["name"],
            folder=info["folder"],
            description=info["description"],
            priority=file_meta.get("priority", "P1"),
            tags=file_meta.get("tags", []),
            owner=file_meta.get("owner", "tester"),
            cases_meta=cases_meta,
        ))
    return cases


def _extract_test_functions(path: Path) -> List[str]:
    """使用 AST 静态解析，提取顶层 test_ 函数名"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
    except Exception:
        return []


def get_ui_case_detail(file: str, function_name: Optional[str] = None) -> Dict[str, Any]:
    """获取 UI 测试文件或单测试函数的详细代码和信息"""
    path = _resolve_safe_file(file)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"用例文件不存在: {file}")

    content = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件代码解析错误: {str(e)}")

    lines = content.splitlines(keepends=True)

    funcs_info = []
    target_node = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            doc = ast.get_docstring(node) or ""
            funcs_info.append({
                "name": node.name,
                "docstring": doc,
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno)
            })
            if function_name and node.name == function_name:
                target_node = node

    if function_name:
        if not target_node:
            raise HTTPException(status_code=404, detail=f"未在文件 {file} 中找到测试函数: {function_name}")
        start = target_node.lineno - 1
        end = getattr(target_node, "end_lineno", target_node.lineno)
        func_code = "".join(lines[start:end])
        case_meta = get_case_meta(f"{file}::{function_name}", {"module": "ui"})
        return {
            "file": file,
            "function": function_name,
            "docstring": ast.get_docstring(target_node) or "",
            "code": func_code,
            "full_code": content,
            "lineno": target_node.lineno,
            "end_lineno": getattr(target_node, "end_lineno", target_node.lineno),
            "functions": funcs_info,
            "priority": case_meta.get("priority", "P1"),
            "tags": case_meta.get("tags", []),
            "owner": case_meta.get("owner", "tester"),
        }

    file_meta = get_case_meta(file, {"module": "ui"})
    return {
        "file": file,
        "function": None,
        "docstring": ast.get_docstring(tree) or "",
        "code": content,
        "full_code": content,
        "lineno": 1,
        "end_lineno": len(lines),
        "functions": funcs_info,
        "priority": file_meta.get("priority", "P1"),
        "tags": file_meta.get("tags", []),
        "owner": file_meta.get("owner", "tester"),
    }


def update_ui_case_file(file: str, code: str) -> dict:
    """更新/保存 UI 用例文件内容"""
    path = _resolve_safe_file(file)
    try:
        ast.parse(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"代码语法校验失败，无法保存: {str(e)}")

    path.write_text(code, encoding="utf-8")
    return {
        "code": 200,
        "success": True,
        "message": f"UI 用例文件 [{file}] 保存成功",
        "data": {"file": file},
        "file": file,
    }


def delete_ui_case(file: str, function_name: Optional[str] = None) -> dict:
    """删除 UI 测试文件或单测试函数"""
    path = _resolve_safe_file(file)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if not function_name:
        path.unlink()
        return {
            "code": 200,
            "success": True,
            "message": f"测试文件 [{file}] 已成功删除",
            "data": {"file": file},
        }

    content = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析文件错误: {str(e)}")

    target_node = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            target_node = node
            break

    if not target_node:
        raise HTTPException(status_code=404, detail=f"未找到函数 {function_name}")

    lines = content.splitlines(keepends=True)
    start = target_node.lineno - 1
    end = getattr(target_node, "end_lineno", target_node.lineno)
    new_lines = lines[:start] + lines[end:]
    new_content = "".join(new_lines)

    try:
        ast.parse(new_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"删除后语法校验失败: {str(e)}")

    path.write_text(new_content, encoding="utf-8")
    return {
        "code": 200,
        "success": True,
        "message": f"测试函数 [{function_name}] 已成功从文件 [{file}] 中删除",
        "data": {"file": file, "function": function_name},
    }


def create_ui_case(req: CreateUiCaseRequest) -> dict:
    """创建或追加 Playwright UI 测试用例"""
    normalized_file = _normalize_filename(req.file)
    path = _resolve_safe_file(normalized_file)
    func_name = _normalize_function_name(req.function_name)

    if req.code and req.code.strip():
        code_block = req.code.strip()
    else:
        desc = req.description or "UI 界面自动化测试用例"
        target_url = req.target_url or "https://www.example.com"
        lines = [
            f"def {func_name}(page: Page):",
            f'    """{desc}"""',
            f'    page.goto("{target_url}")',
            '    # 在此编写 Playwright 页面定位与断言逻辑',
            '    expect(page).to_have_title(re.compile(r".*"))',
        ]
        code_block = "\n".join(lines)

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        file_content = (
            "# -*- coding: utf-8 -*-\n"
            "import re\n"
            "import pytest\n"
            "from playwright.sync_api import Page, expect\n\n\n"
            f"{code_block}\n"
        )
    else:
        current_content = path.read_text(encoding="utf-8")
        try:
            curr_tree = ast.parse(current_content)
            existing_funcs = [
                node.name
                for node in ast.walk(curr_tree)
                if isinstance(node, ast.FunctionDef)
            ]
            if func_name in existing_funcs:
                raise HTTPException(status_code=400, detail=f"文件 {normalized_file} 中已存在名为 {func_name} 的函数，请更换函数名")
        except SyntaxError:
            pass

        file_content = current_content.rstrip() + f"\n\n\n{code_block}\n"

    try:
        ast.parse(file_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"保存后文件语法校验失败: {str(e)}")

    path.write_text(file_content, encoding="utf-8")
    case_key = f"{normalized_file}::{func_name}"
    save_case_meta(
        case_id=case_key,
        priority=req.priority or "P1",
        tags=req.tags if req.tags is not None else ["UI自动化"],
        owner=req.owner or "tester"
    )
    return {
        "code": 200,
        "success": True,
        "message": f"UI 测试用例 [{func_name}] 创建成功",
        "data": {
            "file": normalized_file,
            "function": func_name,
            "case_id": case_key,
        },
        "file": normalized_file,
        "function": func_name,
        "case_id": case_key,
    }


def start_ui_run(req: RunUiRequest, triggered_by: str) -> str:
    """
    启动 Playwright UI 测试，返回 task_id。
    cases 格式：["test_example.py::test_baidu_search", ...]
    """
    cmd = [
        sys.executable, "-m", "pytest",
        "-v",
        "--tb=short",
        "--no-header",
    ]

    if req.headed:
        cmd.append("--headed")

    for case in req.cases:
        cmd.append(str(UI_CASES_DIR / case))

    return run_task(
        module="ui",
        cases=req.cases,
        cmd=cmd,
        results_dir=UI_RESULTS_DIR,
        triggered_by=triggered_by,
        cwd=UI_CASES_DIR.parent.parent,
    )
