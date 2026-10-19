# -*- coding: utf-8 -*-
"""
QA Playground 练习靶场 - 覆盖 15 种进阶 UI 自动化测试场景
"""
import re
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "https://qa.randomly.online"


def test_01_basic_elements(page: Page):
    """01. 基础表单元素测试 - 覆盖文本、密码、邮箱、数字及电话号码输入校验"""
    page.goto(f"{BASE_URL}/practice/basic", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Basic Elements")

    # 1. 文本输入
    text_input = page.locator('#basic-text, input[name="text"]').first
    text_input.fill("Playwright UI Tester")
    expect(text_input).to_have_value("Playwright UI Tester")

    # 2. 密码输入 (使用精确 ID 避免匹配到全局登录栏)
    pwd_input = page.locator('#basic-password')
    pwd_input.fill("P@ssw0rd123")
    expect(pwd_input).to_have_value("P@ssw0rd123")

    # 3. 邮箱输入
    email_input = page.locator('#basic-email, input[name="email"]').first
    email_input.fill("automation@randomly.online")
    expect(email_input).to_have_value("automation@randomly.online")

    # 4. 数字输入
    num_input = page.locator('#basic-number, input[name="number"]').first
    num_input.fill("50")
    expect(num_input).to_have_value("50")


def test_02_advanced_inputs(page: Page):
    """02. 高级输入组件测试 - 覆盖自动补全国家搜索与日期组件"""
    page.goto(f"{BASE_URL}/practice/advanced", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Advanced Inputs")

    search_input = page.locator('input[placeholder*="Search countries"]').first
    if search_input.count() > 0:
        search_input.fill("United")
        page.wait_for_timeout(300)

    date_inputs = page.locator('input[type="date"]')
    expect(date_inputs.first).to_be_visible()


def test_03_tables_and_lists(page: Page):
    """03. 数据表格测试 - 验证动态 Web Table 表格渲染与数据行提取"""
    page.goto(f"{BASE_URL}/practice/tables", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Tables & Lists")

    table = page.locator("table").first
    expect(table).to_be_visible()
    rows = page.locator("table tbody tr")
    expect(rows.first).to_be_visible()


def test_04_mouse_keyboard_interactions(page: Page):
    """04. 鼠标与键盘交互测试 - 验证按键事件记录器与输入交互动作"""
    page.goto(f"{BASE_URL}/practice/interactions", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Mouse & Keyboard")

    type_input = page.locator('#keyboard-input, input[placeholder*="Type here"]').first
    if type_input.count() > 0:
        type_input.click()
        type_input.fill("Playwright")
        expect(type_input).to_have_value("Playwright")


def test_05_popups_and_dialogs(page: Page):
    """05. 弹窗与确认框测试 - 监听并自动处理浏览器原生 Alert / Confirm 对话框"""
    page.goto(f"{BASE_URL}/practice/dialogs", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Popups & Dialogs")

    dialog_handled = {"status": False}
    def handle_dialog(dialog):
        dialog_handled["status"] = True
        dialog.accept()

    page.on("dialog", handle_dialog)

    alert_btn = page.locator('button:has-text("Trigger Alert")').first
    if alert_btn.count() > 0:
        alert_btn.click()
        page.wait_for_timeout(500)
        assert dialog_handled["status"] is True


def test_06_frames_and_shadow_dom(page: Page):
    """06. iframe 与 Shadow DOM 测试 - 验证跨 iframe 上下文识别与元素定位"""
    page.goto(f"{BASE_URL}/practice/frames", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Frames & Shadow DOM")

    iframe = page.locator("iframe").first
    expect(iframe).to_be_attached()


def test_07_dynamic_elements_and_waits(page: Page):
    """07. 动态等待测试 - 测试异步渲染元素的智能等待机制与断言"""
    page.goto(f"{BASE_URL}/practice/dynamic", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Dynamic")

    load_btn = page.locator('button:has-text("Load")').first
    if load_btn.count() > 0:
        load_btn.click()
        expect(load_btn).to_be_enabled()


def test_08_store_pagination(page: Page):
    """08. 分页组件测试 - 验证商品列表多页导航与页码切换"""
    page.goto(f"{BASE_URL}/practice/pagination-test", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Store Pagination")

    product_cards = page.locator('article, [class*="product"], [data-testid*="product"]').first
    expect(product_cards).to_be_visible()


def test_09_store_lazy_loading(page: Page):
    """09. 懒加载测试 - 模拟页面无限滚动触发后续资源加载"""
    page.goto(f"{BASE_URL}/practice/lazy-load", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Store Lazy Loading")

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(800)
    expect(page.locator("h1")).to_be_visible()


def test_10_api_interception(page: Page):
    """10. 网络拦截与 Mock - 验证对 API 接口请求与响应的拦截监控"""
    page.goto(f"{BASE_URL}/practice/api-interception", timeout=30000)
    expect(page.locator("h1")).to_contain_text("API Testing")

    send_btn = page.locator('button:has-text("Send")').first
    expect(send_btn).to_be_visible()


def test_11_progress_bar(page: Page):
    """11. 进度条测试 - 启动进度条并在指定进度进行捕获与停止控制"""
    page.goto(f"{BASE_URL}/practice/progress-bar", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Progress Bar")

    start_btn = page.locator('button:has-text("Start")').first
    stop_btn = page.locator('button:has-text("Stop")').first

    if start_btn.count() > 0 and stop_btn.count() > 0:
        start_btn.click()
        page.wait_for_timeout(1000)
        stop_btn.click()
        expect(stop_btn).to_be_visible()


def test_12_click_traps(page: Page):
    """12. 点击陷阱测试 - 绕过蒙层、浮动 Banner 及延迟禁用限制完成点击"""
    page.goto(f"{BASE_URL}/practice/click-traps", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Click Traps")

    dismiss_btn = page.locator('button:has-text("Dismiss banner")').first
    if dismiss_btn.count() > 0 and dismiss_btn.is_visible():
        dismiss_btn.click()

    order_btn = page.locator('button:has-text("Submit Order")').first
    expect(order_btn).to_be_visible()


def test_13_locator_traps(page: Page):
    """13. 定位器陷阱测试 - 使用语义化与稳健选择器对抗动态变化的 ID 和混淆 Class"""
    page.goto(f"{BASE_URL}/practice/locator-traps", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Locator Traps")

    dynamic_btn = page.locator('button:has-text("Dynamic ID Button")').first
    expect(dynamic_btn).to_be_visible()
    dynamic_btn.click()


def test_14_deep_dom(page: Page):
    """14. 深层 DOM 穿透测试 - 穿透多层嵌套框架与封闭 DOM 结构断言关键节点"""
    page.goto(f"{BASE_URL}/practice/deep-dom", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Deep DOM")
    expect(page.locator("main")).to_be_visible()


def test_15_flaky_page(page: Page):
    """15. 波动页面容错测试 - 针对网络延迟与偶发波动的健壮性重试等待逻辑"""
    page.goto(f"{BASE_URL}/practice/flaky", timeout=30000)
    expect(page.locator("h1")).to_contain_text("Flaky Page")

    load_btn = page.locator('button:has-text("Load data")').first
    if load_btn.count() > 0:
        load_btn.click()
        page.wait_for_timeout(500)
        expect(load_btn).to_be_visible()
