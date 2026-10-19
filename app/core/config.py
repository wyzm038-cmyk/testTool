import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 存储目录
STORAGE_DIR = BASE_DIR / "storage"
USERS_FILE = STORAGE_DIR / "users.json"
DEPARTMENTS_FILE = STORAGE_DIR / "departments.json"
ENVIRONMENTS_FILE = STORAGE_DIR / "environments.json"
AUDIT_LOGS_FILE = STORAGE_DIR / "audit_logs.json"
TASKS_FILE = STORAGE_DIR / "tasks.json"
CASE_METADATA_FILE = STORAGE_DIR / "case_metadata.json"
UI_RESULTS_DIR = STORAGE_DIR / "ui_results"
API_RESULTS_DIR = STORAGE_DIR / "api_results"
PERF_RESULTS_DIR = STORAGE_DIR / "perf_results"

# 测试用例目录
TESTCASES_DIR = BASE_DIR / "testcases"
UI_CASES_DIR = TESTCASES_DIR / "ui"
API_CASES_DIR = TESTCASES_DIR / "api"
PERF_CASES_DIR = TESTCASES_DIR / "perf"

# JWT 配置
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-please-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 小时

# 初始化目录
for d in [
    STORAGE_DIR,
    UI_RESULTS_DIR,
    API_RESULTS_DIR,
    PERF_RESULTS_DIR,
    UI_CASES_DIR,
    API_CASES_DIR,
    PERF_CASES_DIR,
]:
    d.mkdir(parents=True, exist_ok=True)
