# -*- coding: utf-8 -*-
"""
百度用例 - 百度搜索引擎自动化交互测试
"""
import re
import pytest
from playwright.sync_api import Page, expect


def test_baidu_title(page: Page):
    """百度首页标题测试 - 验证页面 Title 正确"""
    page.goto("https://www.baidu.com")
    expect(page).to_have_title("百度一下，你就知道")


def test_baidu_search_input(page: Page):
    """百度搜索框输入测试 - 验证搜索词输入与响应"""
    page.goto("https://www.baidu.com")
    kw = page.locator("#kw")
    kw.fill("Playwright UI 自动化测试")
    expect(kw).to_have_value("Playwright UI 自动化测试")
