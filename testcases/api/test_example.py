# API 测试示例
# 演示如何用 pytest + requests 编写接口用例

import pytest
import requests

BASE_URL = "https://jsonplaceholder.typicode.com"


def test_get_posts():
    """获取帖子列表 - 状态码 200，返回非空数组"""
    resp = requests.get(f"{BASE_URL}/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_post_by_id():
    """根据 ID 获取单条帖子"""
    resp = requests.get(f"{BASE_URL}/posts/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert "title" in data


def test_create_post():
    """创建帖子 - 返回 201"""
    payload = {"title": "测试标题", "body": "测试内容", "userId": 1}
    resp = requests.post(f"{BASE_URL}/posts", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试标题"


def test_get_nonexistent_post():
    """获取不存在的帖子 - 期望 404"""
    resp = requests.get(f"{BASE_URL}/posts/99999")
    assert resp.status_code == 404


def test_api_request():
    """验证接口正常响应"""
    url = "https://jsonplaceholder.typicode.com/posts/1"
    headers = {
    "Content-Type": "application/json"
}
    resp = requests.get(url, headers=headers)
    assert resp.status_code == 200, f"期望状态码 200，实际返回 {resp.status_code}"
    data = resp.json()
    assert data is not None


def test_api_request33():
    """验证接口正常响应"""
    url = "https://jsonplaceholder.typicode.com/posts/1"
    headers = {
    "Content-Type": "application/json"
}
    resp = requests.get(url, headers=headers)
    assert resp.status_code == 200, f"期望状态码 200，实际返回 {resp.status_code}"
    data = resp.json()
    assert data is not None


def test_api_request2():
    """验证接口正常响应"""
    url = "https://jsonplaceholder.typicode.com/posts/1"
    headers = {
    "Content-Type": "application/json"
}
    payload = {
    "title": "新建测试",
    "body": "测试内容",
    "userId": 1
}
    resp = requests.post(url, json=payload, headers=headers)
    assert resp.status_code == 201, f"期望状态码 201，实际返回 {resp.status_code}"
    data = resp.json()
    assert data is not None
