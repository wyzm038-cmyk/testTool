# -*- coding: utf-8 -*-
"""
电商研发部专属用例 (部门代码: mall)
说明: 仅电商平台研发部用户及平台超级管理员可见，其他部门用户无法查看或执行此用例
"""
import pytest
import requests

BASE_URL = "https://jsonplaceholder.typicode.com"


def test_mall_product_detail():
    """【电商部】商品中心-单品SPU/SKU详情查询"""
    resp = requests.get(f"{BASE_URL}/posts/2")
    assert resp.status_code == 200
    product = resp.json()
    assert product["id"] == 2
    assert "title" in product


def test_create_mall_order():
    """【电商部】订单中心-提交购物车并生成预支付订单"""
    order_payload = {"title": "iPhone 16 Pro 订单", "body": "收货地址: 研发中心 5 楼", "userId": 88}
    resp = requests.post(f"{BASE_URL}/posts", json=order_payload)
    assert resp.status_code == 201
    created_order = resp.json()
    assert created_order["title"] == "iPhone 16 Pro 订单"
