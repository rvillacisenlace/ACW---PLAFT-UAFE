from playwright.sync_api import sync_playwright
from src.scrapers.sitio_contraloria import ScraperContraloria
from src.core.models import Cliente, TipoPersona

URL_CONTRALORIA = "https://www.contraloria.gob.ec/Consultas/DeclaracionesJuradas"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    scraper = ScraperContraloria(context=context, url_base=URL_CONTRALORIA)
    cliente = Cliente(identificacion="0911788289", tipo_persona=TipoPersona.NATURAL, nombres_completos="ALVAREZ HENRIQUES AQUILES DAVID")

    resultados = scraper.buscar_cliente(page, cliente)
    print(f"\nTotal de resultados: {len(resultados)}")
    for r in resultados:
        print(f"  {r}")

    resumen = scraper.resumir_declaraciones(resultados)
    print("\n--- Resumen ---")
    for llave, valor in resumen.items():
        print(f"{llave}: {valor}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()