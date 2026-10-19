import json
from pathlib import Path
from typing import Any
from filelock import FileLock


def _lock_path(file_path: Path) -> Path:
    return file_path.with_suffix(file_path.suffix + ".lock")


def read_json(file_path: Path, default: Any = None) -> Any:
    """线程安全地读取 JSON 文件，文件不存在时返回 default"""
    file_path = Path(file_path)
    if not file_path.exists():
        return default if default is not None else {}
    lock = FileLock(str(_lock_path(file_path)))
    with lock:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)


def write_json(file_path: Path, data: Any) -> None:
    """线程安全地写入 JSON 文件"""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(_lock_path(file_path)))
    with lock:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def append_to_list(file_path: Path, item: dict) -> None:
    """线程安全地向 JSON 数组追加一个元素"""
    file_path = Path(file_path)
    lock = FileLock(str(_lock_path(file_path)))
    with lock:
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
        data.append(item)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def update_in_list(file_path: Path, key: str, value: Any, updates: dict) -> bool:
    """
    在 JSON 数组中找到 item[key] == value 的元素并更新字段。
    返回是否找到并更新成功。
    """
    file_path = Path(file_path)
    lock = FileLock(str(_lock_path(file_path)))
    with lock:
        if not file_path.exists():
            return False
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        found = False
        for item in data:
            if item.get(key) == value:
                item.update(updates)
                found = True
                break
        if found:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        return found


def find_in_list(file_path: Path, key: str, value: Any) -> dict | None:
    """在 JSON 数组中查找 item[key] == value 的元素"""
    data = read_json(file_path, default=[])
    return next((item for item in data if item.get(key) == value), None)
