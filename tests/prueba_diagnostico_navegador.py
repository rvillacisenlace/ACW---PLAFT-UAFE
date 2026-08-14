from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel="chrome")
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.goto("https://coberturasalud.msp.gob.ec/", wait_until="domcontentloaded", timeout=90000)    
    input("¿Cargó? Presiona ENTER para cerrar...")
    browser.close()