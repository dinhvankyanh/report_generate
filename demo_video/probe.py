"""Probe the live AgentBase endpoint end-to-end and download the two output files.

Confirms: page loads, "Data Sample" flips prereqs to Ready, "Generate report"
returns download links, and both report (.docx) + tracker (.xlsx) download.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

URL = "https://endpoint-9423e96a-a3b5-4940-84f0-110b8aff6299.agentbase-runtime.aiplatform.vngcloud.vn/"
HERE = Path(__file__).parent
DL = HERE / "downloads"
DL.mkdir(parents=True, exist_ok=True)
CMD = "report for June 2026"

def log(*a):
    print(*a, flush=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 720}, accept_downloads=True)
    page = ctx.new_page()

    log("goto", URL)
    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.screenshot(path=str(HERE / "assets" / "probe_01_loaded.png"))

    log("click Data Sample")
    page.click('button:has-text("Data Sample")')
    page.wait_for_selector('#prereqs >> text=Ready', timeout=60000)
    log("prereqs:", page.inner_text('#prereqs').replace("\n", " | "))
    page.screenshot(path=str(HERE / "assets" / "probe_02_ready.png"))

    log("fill command + generate (waiting up to 5 min)")
    page.fill('#msg', CMD)
    page.click('#btn')
    # The result download link appears only after the synchronous /invocations call.
    page.wait_for_selector('a.dl[href="/download?type=report"]', timeout=300000)
    out_html = page.inner_text('#out')
    log("OUT:", out_html.replace("\n", " | "))
    page.screenshot(path=str(HERE / "assets" / "probe_03_result.png"), full_page=True)

    for kind, sel in (("report", 'a.dl[href="/download?type=report"]'),
                      ("tracker", 'a.dl[href="/download?type=tracker"]')):
        with page.expect_download(timeout=60000) as dl_info:
            page.click(sel)
        dl = dl_info.value
        dest = DL / dl.suggested_filename
        dl.save_as(str(dest))
        log(f"downloaded {kind}: {dest.name} ({dest.stat().st_size} bytes)")

    ctx.close()
    browser.close()
    log("DONE")
