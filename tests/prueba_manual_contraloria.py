from playwright.sync_api import sync_playwright
from src.scrapers.sitio_contraloria import ScraperContraloria
from src.core.models import Cliente, TipoPersona

URL_CONTRALORIA = "https://www.contraloria.gob.ec/Consultas/DeclaracionesJuradas"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    scraper = ScraperContraloria(context=context, url_base=URL_CONTRALORIA)
    cliente = Cliente(identificacion="0850513433", tipo_persona=TipoPersona.NATURAL, nombres_completos="Villacis Olivo Rommel Joerick")

    resultados = scraper.buscar_cliente(page, cliente)
    print(f"\nTotal de resultados: {len(resultados)}")
    for r in resultados:
        print(f"  {r}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()