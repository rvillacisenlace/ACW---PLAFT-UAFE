from playwright.sync_api import sync_playwright
from src.scrapers.sitio_salud import ScraperSalud
from src.core.models import Cliente, TipoPersona

URL_SALUD = "https://coberturasalud.msp.gob.ec/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300, channel="chrome")
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    scraper = ScraperSalud(context=context, url_base=URL_SALUD)
    cliente = Cliente(identificacion="0850513433", tipo_persona=TipoPersona.NATURAL, nombres_completos="Villacis Olivo Rommel Joerick")

    resultado = scraper.buscar_cliente(page, cliente)

    print(f"\nPDF: {resultado.ruta_pdf}")
    print(f"Situación Laboral: {resultado.situacion_laboral}")
    print(f"Tipo de Afiliación: {resultado.tipo_afiliacion}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()