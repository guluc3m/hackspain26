"""Capturas de la UI (modo sintético) para revisión visual."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "_ui_shots"
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 900})
    page.goto("http://127.0.0.1:4173/")
    page.wait_for_selector("table")
    page.screenshot(path=str(OUT / "dashboard.png"), full_page=True)

    page.click("text=Invoices")
    page.wait_for_selector("table")
    page.screenshot(path=str(OUT / "invoices.png"), full_page=True)

    page.click("text=Logs")
    page.wait_for_selector(".evento")
    page.screenshot(path=str(OUT / "logs.png"), full_page=True)

    # drawer de revisión desde el finder (evento con invoice_id)
    page.click("button:has-text('ver')")
    page.wait_for_selector(".drawer")
    page.screenshot(path=str(OUT / "drawer.png"), full_page=True)
    b.close()

print("capturas en", OUT)
