# 测试平台后端

> FastAPI + Threading + WebSocket + k6 + Playwright + pytest

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装 Playwright 浏览器（首次需要）
playwright install chromium

# 3. 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) 查看 Swagger 文档。

**默认账号**：`admin` / `admin123`

---

## 目录结构

```
testTool/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── core/
│   │   ├── config.py        # 全局配置 & 路径
│   │   └── auth.py          # JWT 认证
│   ├── api/
│   │   ├── auth_router.py   # /auth/*
│   │   ├── ui_router.py     # /ui/*
│   │   ├── api_router.py    # /api-test/*
│   │   └── perf_router.py   # /perf/*
│   ├── services/
│   │   ├── runner.py        # 后台任务运行器（threading）
│   │   ├── ui_service.py    # Playwright 用例扫描 & 运行
│   │   ├── api_service.py   # pytest 用例扫描 & 运行
│   │   └── perf_service.py  # k6 用例扫描 & 运行
│   ├── db/
│   │   └── json_store.py    # 线程安全 JSON 读写
│   ├── models/
│   │   └── schemas.py       # Pydantic 数据模型
│   └── ws/
│       ├── manager.py       # WebSocket 连接管理器
│       └── ws_router.py     # ws://.../ws/tasks/{task_id}
│
├── storage/                 # JSON 数据库（自动创建）
│   ├── users.json
│   ├── tasks.json
│   ├── ui_results/
│   ├── api_results/
│   └── perf_results/
│
├── testcases/               # 放你的测试用例
│   ├── ui/                  # Playwright 脚本（test_*.py）
│   ├── api/                 # pytest 脚本（test_*.py）
│   └── perf/                # k6 脚本（*.js）
│
└── requirements.txt
```

---

## 接口速览

### 认证
| 接口 | 说明 |
|------|------|
| `POST /auth/login-json` | JSON 登录，返回 JWT |
| `GET  /auth/me` | 当前用户信息 |
| `GET  /auth/users` | 用户列表（admin） |
| `POST /auth/users` | 创建用户（admin） |

### UI 测试
| 接口 | 说明 |
|------|------|
| `GET  /ui/cases` | 扫描用例列表 |
| `POST /ui/run` | 运行用例，返回 `task_id` |
| `GET  /ui/tasks` | 任务历史 |
| `GET  /ui/tasks/{id}` | 任务详情+日志 |

### API 测试
| 接口 | 说明 |
|------|------|
| `GET  /api-test/cases` | 扫描用例列表 |
| `POST /api-test/run` | 运行用例 |
| `GET  /api-test/tasks/{id}` | 任务详情 |

### 性能测试 (k6)
| 接口 | 说明 |
|------|------|
| `GET  /perf/cases` | 扫描 JS 脚本列表 |
| `POST /perf/run` | 运行性能测试 |
| `GET  /perf/tasks/{id}` | 结果详情 |

### WebSocket
```
ws://localhost:8000/ws/tasks/{task_id}
```
连接后实时接收日志流，消息格式：
- `{"type": "log", "data": "某行日志"}` — 日志行
- `{"type": "done", "status": "success"}` — 任务结束

---

## 性能测试需要安装 k6

```powershell
# Windows (Chocolatey)
choco install k6

# 或下载二进制：https://k6.io/docs/get-started/installation/
```
