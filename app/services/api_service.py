"""
API 测试服务：基于 pytest
  - 扫描 testcases/api/ 目录
  - 构建 pytest 命令运行选中用例
"""
import ast
import json
import re
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import HTTPException

from app.core.auth import (
    check_case_department_access,
    get_departments,
    is_super_admin,
)
from app.core.config import API_CASES_DIR, API_RESULTS_DIR
from app.models.schemas import (
    ApiCase,
    ApiCaseDetail,
    CreateApiCaseRequest,
    RunApiRequest,
)
from app.services.runner import run_task
from app.services.case_meta_service import get_case_meta, save_case_meta


def _resolve_safe_file(file: str) -> Path:
    """安全解析并校验测试文件路径"""
    cleaned = file.strip().replace("\\", "/").lstrip("/")
    target = (API_CASES_DIR / cleaned).resolve()
    try:
        target.relative_to(API_CASES_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="非法的文件路径")
    return target


API_FOLDER_NAME_MAP = {
    "fin": "金融支付模块",
    "mall": "商城业务模块",
    "qa": "QA 回归测试",
    "public": "公共测试模块",
    "common": "通用公共用例",
}


def _extract_module_info(py_file: Path, rel: str) -> dict:
    parts = rel.split("/")
    folder = parts[0] if len(parts) > 1 else ""

    name = API_FOLDER_NAME_MAP.get(folder)
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
            name = API_FOLDER_NAME_MAP.get(folder, folder.replace("_", " ").title() + " 模块")
        else:
            stem = py_file.stem.replace("test_", "").replace("_", " ").title()
            name = f"{stem} 模块"

    return {"name": name, "folder": folder or py_file.stem, "description": desc}


def scan_api_cases(
    current_user: Optional[dict] = None,
    filter_dept: Optional[str] = None,
) -> List[ApiCase]:
    """
    扫描 testcases/api/ 下所有 test_*.py 文件，并应用中型企业【部门数据隔离】规则：
    - super_admin：可查看全公司所有部门的用例，支持通过 filter_dept 筛选
    - 普通部门成员（dept_admin / tester / viewer）：只返回本人所属部门目录及公共公共用例，绝对不可见其他部门用例！
    """
    dept_map = {d["code"].lower(): d["name"] for d in get_departments()}
    user_dept_code = None
    user_is_super = False

    if current_user:
        user_is_super = is_super_admin(current_user)
        user_dept_code = (current_user.get("dept_code") or "qa").lower()

    cases = []
    for py_file in sorted(API_CASES_DIR.rglob("test_*.py")):
        rel = py_file.relative_to(API_CASES_DIR).as_posix()
        parts = rel.split("/")
        
        # 判定所属部门
        if len(parts) > 1:
            file_dept_code = parts[0].lower()
        else:
            file_dept_code = "qa"  # 根目录默认归属于质量部

        # 部门数据权限过滤
        if current_user and not user_is_super:
            # 普通用户：必须属于本人部门或 public 公共目录
            if file_dept_code != user_dept_code and file_dept_code not in ["public", "common"]:
                continue
        elif user_is_super and filter_dept:
            # 超级管理员按部门筛选
            if file_dept_code != filter_dept.lower():
                continue

        funcs = _extract_test_functions(py_file)
        info = _extract_module_info(py_file, rel)

        cases_meta = {}
        for fn in funcs:
            fn_key = f"{rel}::{fn}"
            cases_meta[fn] = get_case_meta(fn_key, {"dept_code": file_dept_code})

        file_meta = get_case_meta(rel, {"dept_code": file_dept_code})
        cases.append(
            ApiCase(
                file=rel,
                functions=funcs,
                name=info["name"],
                folder=info["folder"],
                description=info["description"],
                priority=file_meta.get("priority", "P1"),
                tags=file_meta.get("tags", []),
                owner=file_meta.get("owner", "tester"),
                cases_meta=cases_meta,
                dept_code=file_dept_code,
                dept_name=dept_map.get(file_dept_code, file_dept_code.upper()),
            )
        )
    return cases


def _extract_test_functions(path: Path) -> List[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
    except Exception:
        return []


def get_case_detail(
    file: str,
    function_name: Optional[str] = None,
    current_user: Optional[dict] = None,
) -> ApiCaseDetail:
    """获取用例文件或单测试函数的详细代码和信息（严格校验部门访问权限）"""
    if current_user:
        check_case_department_access(current_user, file)

    path = _resolve_safe_file(file)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"用例文件不存在: {file}")

    content = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件代码解析错误: {str(e)}")

    lines = content.splitlines(keepends=True)

    # 提取文件内全部函数信息
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
            raise HTTPException(status_code=404, detail=f"在文件 {file} 中未找到测试函数: {function_name}")
        doc = ast.get_docstring(target_node) or ""
        start = target_node.lineno - 1
        end = getattr(target_node, "end_lineno", target_node.lineno)
        func_code = "".join(lines[start:end])
        case_meta = get_case_meta(f"{file}::{function_name}")
        return ApiCaseDetail(
            file=file,
            function=function_name,
            docstring=doc,
            code=func_code,
            full_code=content,
            lineno=target_node.lineno,
            end_lineno=end,
            functions=funcs_info,
            priority=case_meta.get("priority", "P1"),
            tags=case_meta.get("tags", []),
            owner=case_meta.get("owner", "tester"),
        )
    else:
        first_doc = ast.get_docstring(tree) or ""
        file_meta = get_case_meta(file)
        return ApiCaseDetail(
            file=file,
            function=None,
            docstring=first_doc,
            code=content,
            full_code=content,
            functions=funcs_info,
            priority=file_meta.get("priority", "P1"),
            tags=file_meta.get("tags", []),
            owner=file_meta.get("owner", "tester"),
        )


def _normalize_filename(raw_file: str) -> str:
    cleaned = raw_file.strip().replace("\\", "/")
    if not cleaned:
        cleaned = "test_api_cases.py"
    if not cleaned.endswith(".py"):
        cleaned += ".py"
    name = Path(cleaned).name
    if not name.startswith("test_"):
        cleaned = str(Path(cleaned).parent / f"test_{name}").replace("\\", "/")
    return cleaned


def _normalize_function_name(raw_name: Optional[str]) -> str:
    if not raw_name or not raw_name.strip():
        raw_name = "test_api_request"
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name.strip())
    if not cleaned.startswith("test_"):
        cleaned = f"test_{cleaned}"
    return cleaned


def create_api_case(req: CreateApiCaseRequest, current_user: Optional[dict] = None) -> dict:
    """创建或追加 API 测试用例（强制部门物理隔离）"""
    raw_file = req.file.strip().replace("\\", "/").lstrip("/")
    
    # 部门归属路径隔离
    if current_user and not is_super_admin(current_user):
        user_dept_code = (current_user.get("dept_code") or "qa").lower()
        parts = raw_file.split("/")
        if len(parts) > 1:
            file_dept = parts[0].lower()
            if file_dept != user_dept_code:
                raise HTTPException(
                    status_code=403,
                    detail=f"权限不足：您属于 [{current_user.get('dept_name')}]，禁止向其他部门 [{file_dept}] 目录创建用例！",
                )
        else:
            raw_file = f"{user_dept_code}/{raw_file}"
    elif current_user and is_super_admin(current_user) and req.dept_code:
        dept_prefix = req.dept_code.strip().lower()
        if not raw_file.startswith(f"{dept_prefix}/"):
            raw_file = f"{dept_prefix}/{raw_file}"

    normalized_file = _normalize_filename(raw_file)
    path = _resolve_safe_file(normalized_file)
    func_name = _normalize_function_name(req.function_name)

    # 准备将要写入的代码块
    if req.code and req.code.strip():
        # 用户自定义了代码
        code_block = req.code.strip()
    else:
        # 表单模式生成标准的 pytest + requests 代码
        method = (req.method or "GET").upper()
        url = req.url or "https://jsonplaceholder.typicode.com/posts"
        desc = req.description or f"{method} {url} 接口测试"
        headers_str = json.dumps(req.headers or {}, ensure_ascii=False, indent=4)
        body_str = json.dumps(req.body or {}, ensure_ascii=False, indent=4)
        expected_status = req.expected_status or 200

        lines = [
            f"def {func_name}():",
            f'    """{desc}"""',
            f'    url = "{url}"',
        ]
        if req.headers:
            lines.append(f"    headers = {headers_str}")
        else:
            lines.append("    headers = None")

        if method in ["POST", "PUT", "PATCH"]:
            if req.body:
                lines.append(f"    payload = {body_str}")
                lines.append(f"    resp = requests.{method.lower()}(url, json=payload, headers=headers)")
            else:
                lines.append(f"    resp = requests.{method.lower()}(url, headers=headers)")
        else:
            lines.append(f"    resp = requests.{method.lower()}(url, headers=headers)")

        lines.append(f"    assert resp.status_code == {expected_status}, f\"期望状态码 {expected_status}，实际返回 {{resp.status_code}}\"")

        # 增加通用断言
        if req.assertions:
            for ass in req.assertions:
                if ass.strip():
                    lines.append(f"    {ass.strip()}")
        else:
            lines.append("    data = resp.json()")
            lines.append("    assert data is not None")

        code_block = "\n".join(lines)

    # 验证 code_block 的 Python 语法
    try:
        ast.parse(code_block)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"生成的 Python 代码语法错误: {str(e)}")

    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        # 新文件
        file_content = f"# -*- coding: utf-8 -*-\nimport pytest\nimport requests\n\n\n{code_block}\n"
    else:
        # 已有文件：检查函数名是否重复
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

    # 全文件语法校验
    try:
        ast.parse(file_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"保存后文件语法校验失败: {str(e)}")

    path.write_text(file_content, encoding="utf-8")

    return {
        "code": 200,
        "success": True,
        "message": f"测试用例 [{func_name}] 创建成功",
        "data": {
            "file": normalized_file,
            "function": func_name,
            "case_id": f"{normalized_file}::{func_name}",
        },
        "file": normalized_file,
        "function": func_name,
        "case_id": f"{normalized_file}::{func_name}",
    }


def update_case_file(file: str, code: str, current_user: Optional[dict] = None) -> dict:
    """更新/保存用例文件内容（权限隔离保护）"""
    if current_user:
        check_case_department_access(current_user, file)

    path = _resolve_safe_file(file)
    try:
        ast.parse(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"代码语法校验失败，无法保存: {str(e)}")

    path.write_text(code, encoding="utf-8")
    return {
        "code": 200,
        "success": True,
        "message": f"用例文件 [{file}] 保存成功",
        "data": {"file": file},
        "file": file,
    }


def delete_api_case(
    file: str,
    function_name: Optional[str] = None,
    current_user: Optional[dict] = None,
) -> dict:
    """删除测试文件或测试函数（权限隔离保护）"""
    if current_user:
        check_case_department_access(current_user, file)

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

    # 删除指定函数
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

    # 校验修改后的语法
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


def start_api_run(req: RunApiRequest, current_user: dict) -> str:
    """
    启动 API 测试，返回 task_id（具备部门数据隔离检查）。
    cases 格式：["fin/test_payment_api.py::test_payment_gateway_health", ...]
    """
    # 越界防范校验
    for case_item in req.cases:
        case_file = case_item.split("::")[0]
        check_case_department_access(current_user, case_file)

    cmd = [
        sys.executable, "-m", "pytest",
        "-v",
        "--tb=short",
        "--no-header",
    ]

    env_vars = {}
    if req.env:
        env_vars["TEST_ENV"] = req.env

    for case in req.cases:
        cmd.append(str(API_CASES_DIR / case))

    import os

    return run_task(
        module="api",
        cases=req.cases,
        cmd=cmd,
        results_dir=API_RESULTS_DIR,
        triggered_by=current_user["username"],
        cwd=API_CASES_DIR.parent.parent,
        extra_info={
            "env": req.env if req.env else None,
            "dept_id": current_user.get("dept_id"),
            "dept_name": current_user.get("dept_name"),
            "dept_code": current_user.get("dept_code"),
        },
    )
