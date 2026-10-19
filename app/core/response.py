"""
统一企业级 API 响应结构与全局异常拦截
标准三要素:
1. code: 状态码 (例如 200, 400, 405, 500)
2. data: 代码返回值 (成功时为数据载荷，失败时为 null)
3. msg:  中文提示信息 (面向前端直接展示给用户看，同时保留 message 兼容)
"""
import json
from typing import Any, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException


HTTP_STATUS_CN_MAP = {
    400: "请求参数有误或业务校验未通过",
    401: "身份凭据未提供或已过期，请重新登录",
    403: "权限不足，禁止访问该接口",
    404: "请求的 API 接口或用例文件不存在",
    405: "请求方法不允许 (405 Method Not Allowed)：后端未开放该接口的对应请求方式。若您刚更新了代码，请重启后端服务 (uvicorn)！",
    422: "数据字段校验失败，请检查输入参数是否完整",
    500: "服务器内部处理异常，请查看后端控制台日志",
}


def make_response(
    code: int = 200,
    msg: str = "操作成功",
    data: Any = None,
    http_status_code: Optional[int] = None,
) -> JSONResponse:
    """企业级统一三要素响应结构"""
    payload = {
        "code": code,
        "data": data,
        "msg": msg,
        "message": msg,  # 兼容习惯读取 message 的前端库
    }
    return JSONResponse(
        status_code=http_status_code or (code if 100 <= code <= 599 else 200),
        content=payload,
    )


class EnterpriseResponseMiddleware(BaseHTTPMiddleware):
    """
    企业级兜底中间件：
    如果出站响应中仍包含原生 FastAPI 的 {"detail": "..."}，强制自动重写为包含 code/data/msg 的正规中文响应
    """
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # 仅针对 JSON 响应且包含错误状态码进行拦截包装
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type and response.status_code >= 400:
            # 读取响应体
            body_chunks = [chunk async for chunk in response.body_iterator]
            body_bytes = b"".join(body_chunks)
            try:
                data = json.loads(body_bytes.decode("utf-8"))
                # 如果是原生只含有 detail 的极短响应
                if isinstance(data, dict) and "detail" in data and "code" not in data:
                    raw_detail = str(data.get("detail", ""))
                    # 匹配中文原因
                    cn_msg = HTTP_STATUS_CN_MAP.get(
                        response.status_code,
                        raw_detail if raw_detail and raw_detail not in ["Method Not Allowed", "Not Found"] else f"请求异常 ({response.status_code})"
                    )
                    if raw_detail in ["Method Not Allowed", "Not Found", "Unauthorized"]:
                        cn_msg = HTTP_STATUS_CN_MAP.get(response.status_code, cn_msg)
                    elif raw_detail:
                        cn_msg = raw_detail

                    new_payload = {
                        "code": response.status_code,
                        "data": None,
                        "msg": cn_msg,
                        "message": cn_msg,
                        "detail": raw_detail,
                    }
                    new_bytes = json.dumps(new_payload, ensure_ascii=False).encode("utf-8")
                    return Response(
                        content=new_bytes,
                        status_code=response.status_code,
                        media_type="application/json",
                        headers=dict(response.headers),
                    )
            except Exception:
                pass

            # 若未触发重写，还原 body_iterator
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response


def register_exception_handlers(app: FastAPI):
    """为 FastAPI 应用注册全局统一的企业级异常处理器"""
    # 注册兜底中间件
    app.add_middleware(EnterpriseResponseMiddleware)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        status_code = exc.status_code
        raw_detail = str(exc.detail) if exc.detail else ""

        default_cn = HTTP_STATUS_CN_MAP.get(status_code, f"请求异常 (状态码 {status_code})")

        if raw_detail in ["Method Not Allowed", "Not Found", "Unauthorized", "Forbidden", "Bad Request"]:
            user_msg = default_cn
        elif raw_detail:
            user_msg = raw_detail
        else:
            user_msg = default_cn

        return make_response(
            code=status_code,
            msg=user_msg,
            data=None,
            http_status_code=status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        err_details = []
        for err in exc.errors():
            loc = " -> ".join(str(item) for item in err.get("loc", []))
            msg = err.get("msg", "")
            err_details.append(f"字段 [{loc}]: {msg}")

        combined_msg = "；".join(err_details) if err_details else "请求参数验证未通过"
        return make_response(
            code=422,
            msg=f"参数校验错误: {combined_msg}",
            data=None,
            http_status_code=422,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        import traceback
        traceback.print_exc()
        return make_response(
            code=500,
            msg=f"服务器内部异常: {str(exc)}",
            data=None,
            http_status_code=500,
        )
