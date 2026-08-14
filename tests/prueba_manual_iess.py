from playwright.sync_api import sync_playwright
from src.scrapers.sitio_iess import ScraperIESS
from src.core.models import Cliente, TipoPersona

URL_IESS = "https://www.iess.gob.ec/empleador-web/pages/morapatronal/certificadoCumplimientoPublico.jsf"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True, accept_downloads=True)
    page = context.new_page()

    scraper = ScraperIESS(context=context, url_base=URL_IESS)
    cliente = Cliente(identificacion="1001322518", tipo_persona=TipoPersona.NATURAL, nombres_completos="Torres Gordillo Diego Patricio")

    resultado = scraper.buscar_cliente(page, cliente)

    print(f"\n¿Hay registro?: {resultado['hay_registro']}")
    print(f"PDF: {resultado['ruta_pdf']}")
    print(f"IESS: {resultado['iess']}")
    print(f"Deuda obligaciones: {resultado['deuda_obligaciones']}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()