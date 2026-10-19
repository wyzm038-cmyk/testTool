# -*- coding: utf-8 -*-
"""
金融研发部专属用例 (部门代码: fin)
说明: 仅金融研发部用户及平台超级管理员可见，其他部门用户无法查看或执行此用例
"""
import pytest
import requests

BASE_URL = "https://jsonplaceholder.typicode.com"


def test_payment_gateway_health():
    """【金融部】支付网关网关健康探测与握手"""
    resp = requests.get(f"{BASE_URL}/posts/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1


def test_query_settlement_account():
    """【金融部】商户清结算结算账户状态查询"""
    resp = requests.get(f"{BASE_URL}/users/1")
    assert resp.status_code == 200
    account = resp.json()
    assert "email" in account
    assert len(account["name"]) > 0
