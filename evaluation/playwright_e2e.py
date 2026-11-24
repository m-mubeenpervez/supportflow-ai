"""Non-mutating browser smoke checks for the Dockerized SupportFlow UI.

These checks intentionally never register accounts, submit chat, approve tickets,
or send email because the Docker backend is attached to preserved recovery data.
Authenticated journeys belong in a disposable stack backed by supportflow_test_db.
"""

import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright


BASE_URL = os.getenv("SUPPORTFLOW_UI_URL", "http://localhost:15173")
API_URL = os.getenv("SUPPORTFLOW_API_URL", "http://localhost:18000")
ARTIFACTS = Path(__file__).with_name("playwright-artifacts")


async def check_viewport(browser, width, height):
    page = await browser.new_page(viewport={"width": width, "height": height})
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    response = await page.goto(BASE_URL, wait_until="networkidle")
    assert response and response.ok
    assert await page.title()
    assert await page.get_by_role("heading", name="Welcome back").is_visible()
    assert await page.get_by_label("Email address").is_visible()
    assert await page.get_by_label("Password", exact=True).is_visible()
    assert await page.locator("body").evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    await page.get_by_label("Email address").fill("browser-invalid@example.test")
    await page.get_by_label("Password", exact=True).fill("invalid-password")
    await page.get_by_role("button", name="Sign in").click()
    await page.wait_for_timeout(1200)
    alert = page.get_by_role("alert").first
    assert await alert.is_visible()
    assert (await alert.inner_text()).strip()
    await page.screenshot(path=str(ARTIFACTS / f"login-{width}.png"), full_page=True)
    assert not page_errors, f"page errors at {width}px: {page_errors}"
    await page.close()


async def check_registration_and_admin_errors(browser):
    page = await browser.new_page()
    await page.goto(BASE_URL, wait_until="networkidle")
    await page.get_by_role("button", name="Create account").click()
    assert await page.get_by_role("heading", name="Create your account").is_visible()
    await page.get_by_label("Full name").fill("Disposable Browser Check")
    await page.get_by_label("Email address").fill("browser-e2e@example.test")
    await page.get_by_label("Password", exact=True).fill("weak")
    await page.get_by_label("Confirm password", exact=True).fill("different")
    await page.get_by_role("button", name="Create account").click()
    assert await page.get_by_text("Passwords do not match").is_visible()

    await page.get_by_role("button", name="Sign in").click()
    await page.get_by_label("Email address").fill("admin-invalid@example.test")
    await page.get_by_label("Password", exact=True).fill("invalid-password")
    await page.get_by_role("button", name="Sign in").click()
    await page.wait_for_timeout(1200)
    alert = page.get_by_role("alert").first
    assert await alert.is_visible()
    assert (await alert.inner_text()).strip()
    await page.close()


async def check_backend_health(request):
    response = await request.get(f"{API_URL}/health")
    assert response.ok
    assert (await response.json())["status"] == "ok"


async def check_customer_bootstrap(browser):
    """Regression check: a 200 verified-status response must leave loading."""
    context = await browser.new_context()
    await context.add_init_script(
        "sessionStorage.setItem('supportflow_customer_session_v1', "
        "JSON.stringify({token:'bootstrap-test-token',createdAt:Date.now()}));"
    )
    page = await context.new_page()
    await page.route("**/auth/verification-status", lambda route: route.fulfill(
        status=200, content_type="application/json", body='{"email_verified":true}'
    ))
    await page.goto(BASE_URL, wait_until="networkidle")
    await page.wait_for_timeout(500)
    assert not await page.get_by_text("Checking your session...").is_visible()
    await context.close()


async def check_customer_history_navigation(browser):
    """Use mocked auth/data to verify Back/Forward sync without recovery DB writes."""
    context = await browser.new_context()
    await context.add_init_script(
        "sessionStorage.setItem('supportflow_customer_session_v1', "
        "JSON.stringify({token:'history-test-token',createdAt:Date.now()}));"
    )

    async def mock_api(route):
        url = route.request.url
        if url.endswith("/auth/verification-status"):
            body = '{"email_verified":true}'
        elif url.endswith("/customer/tickets"):
            body = '[{"id":42,"summary":"Mock conversation","status":"open"}]'
        elif "/customer/tickets/42/messages" in url:
            body = '{"ticket_id":42,"status":"open","messages":[]}'
        else:
            await route.continue_()
            return
        await route.fulfill(status=200, content_type="application/json", body=body)

    await context.route("**/auth/verification-status", mock_api)
    await context.route("**/customer/tickets**", mock_api)
    page = await context.new_page()
    await page.goto(f"{BASE_URL}/", wait_until="networkidle")
    await page.goto(f"{BASE_URL}/chat/42", wait_until="networkidle")
    await page.wait_for_timeout(300)
    assert page.url.endswith("/chat/42")
    assert await page.get_by_text("Ticket #42", exact=True).is_visible()
    for _ in range(10):
        await page.go_back()
        await page.wait_for_timeout(120)
        assert await page.evaluate("window.location.pathname") == "/"
        assert await page.get_by_text("New conversation", exact=True).is_visible()
        await page.go_forward()
        await page.wait_for_timeout(120)
        assert page.url.endswith("/chat/42")
        assert await page.get_by_text("Ticket #42", exact=True).is_visible()
    await context.close()


async def main():
    ARTIFACTS.mkdir(exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        await check_viewport(browser, 1440, 900)
        await check_viewport(browser, 390, 844)
        await check_registration_and_admin_errors(browser)
        await check_customer_bootstrap(browser)
        await check_customer_history_navigation(browser)
        await browser.close()
        request = await playwright.request.new_context()
        try:
            await check_backend_health(request)
        finally:
            await request.dispose()
    print("PLAYWRIGHT_NON_MUTATING_SMOKE=PASS")
    print("authenticated_customer_admin_journeys=SKIPPED_RECOVERY_DB_SAFETY")


if __name__ == "__main__":
    asyncio.run(main())
