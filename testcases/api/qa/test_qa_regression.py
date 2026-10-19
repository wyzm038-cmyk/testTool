# -*- coding: utf-8 -*-
"""
质量保障中心专属用例 (部门代码: qa)
说明: 仅质量保障中心用户及平台超级管理员可见
"""
import pytest
import requests

BASE_URL = "https://jsonplaceholder.typicode.com"


def test_qa_core_health_ping():
    """【质量部】全链路网关与基础服务连通性探活"""
    resp = requests.get(f"{BASE_URL}/todos/1")
    assert resp.status_code == 200
    todo = resp.json()
    assert todo["id"] == 1


def test_qa_regression_benchmark():
    """【质量部】回归基线接口吞吐与字段完备性验证"""
    resp = requests.get(f"{BASE_URL}/albums/1")
    assert resp.status_code == 200
    assert "title" in resp.json()
