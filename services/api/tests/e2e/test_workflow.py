"""Critical user workflow in a real browser (opt-in).

Needs the E2E harness and the web app running, then:

    $env:E2E_DATA_DIR = "<the harness --data directory>"
    pytest tests/e2e/test_workflow.py

Covers: register, verify email, create project, scan, open finding, AI analysis, connect GitHub,
link repository, generate fix, review diff, approve, create pull request.
"""

import json
import os
import re
import uuid
from pathlib import Path

import pytest

DATA_DIR = os.environ.get("E2E_DATA_DIR")
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:3000")

pytestmark = pytest.mark.skipif(not DATA_DIR, reason="E2E_DATA_DIR is not set (browser E2E)")


def _verification_link(data_dir: Path, email: str) -> str:
    for line in reversed((data_dir / "outbox.jsonl").read_text(encoding="utf-8").splitlines()):
        message = json.loads(line)
        if message["to"] == email and "Verify" in message["subject"]:
            return re.search(r"http\S+verify-email#token=\S+", message["text"]).group(0)
    raise AssertionError("No verification email")


async def test_scan_to_pull_request():
    from playwright.async_api import async_playwright, expect

    data_dir = Path(DATA_DIR or "")
    site_url = json.loads((data_dir / "harness.json").read_text())["site_url"]
    email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"
    timeout = 45_000
    expect.set_options(timeout=timeout)  # background jobs take a few seconds

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(base_url=BASE_URL)
        page.set_default_timeout(timeout)

        await page.goto("/register")
        await page.get_by_label("Name").fill("Workflow Test")
        await page.get_by_label("Work email").fill(email)
        await page.get_by_label("Password").fill("workflow passphrase 1")
        await page.get_by_role("button", name="Create account").click()
        await page.wait_for_url("**/dashboard")
        await expect(
            page.get_by_text("Verify your email address to start scanning")
        ).to_be_visible()

        await page.goto(_verification_link(data_dir, email))
        await expect(page.get_by_text("Email verified")).to_be_visible()

        await page.goto("/projects/new")
        await page.get_by_label("Project name").fill("Workflow shop")
        await page.get_by_label("Website URL").fill(f"{site_url}/no-title")
        await page.get_by_role("button", name="Create project").click()
        await page.wait_for_url(re.compile(r"/projects/[0-9a-f-]{36}$"))
        project_url = page.url

        await page.get_by_role("button", name="Run scan").click()
        await page.get_by_role("link", name="Open report").click(timeout=90_000)
        await page.get_by_text("Page title is missing or empty").click()
        await page.wait_for_url("**/findings/**")
        finding_url = page.url

        await page.get_by_role("button", name="Analyze with AI").click()
        await expect(page.get_by_text("Likely root cause")).to_be_visible()

        await page.goto("/github")
        await page.get_by_role("button", name="Connect GitHub").click()
        await page.wait_for_url("**/github")
        await expect(page.get_by_text("@octo")).to_be_visible()

        await page.goto(project_url)
        await page.get_by_role("tab", name="Repository").click()
        await page.get_by_label("Repository").select_option("octo/site")
        await page.get_by_role("button", name="Save repository").click()
        await expect(page.get_by_text("Connected to octo/site")).to_be_visible()

        await page.goto(finding_url)
        await page.get_by_role("button", name="Generate AI fix").click()
        await page.get_by_role("button", name="Generate", exact=True).click()
        await page.get_by_role("button", name="Review the new fix").click()
        await page.wait_for_url("**/fixes/**")
        await expect(page.get_by_text("<title>Example site</title>").first).to_be_visible()
        await expect(page.get_by_text("Validation passed")).to_be_visible()

        await page.get_by_role("button", name="Approve").click()
        await page.get_by_role("button", name="Create pull request").click()
        await expect(page.get_by_text("fixify/fix-")).to_be_visible()
        await expect(page.get_by_text("Applied", exact=True)).to_be_visible()
        await expect(page.get_by_role("link", name="Open on GitHub")).to_be_visible()

        await browser.close()
