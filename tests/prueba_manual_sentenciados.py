from playwright.sync_api import sync_playwright
from src.scrapers.sitio_sentenciados import ScraperSentenciados
from src.core.models import Cliente, TipoPersona

URL_SENTENCIADOS = "https://consultas.funcionjudicial.gob.ec/informacionjudicialindividual/pages/index.jsf#!/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context()
    page = context.new_page()

    scraper = ScraperSentenciados(context=context, url_base=URL_SENTENCIADOS)
    cliente = Cliente(identificacion="0990014094001", tipo_persona=TipoPersona.JURIDICA, razon_social="INDUAUTO S.A.")

    sentenciados, total = scraper.buscar_cliente(page, cliente)

    print(f"\nTotal encontrado: {total}")
    for s in sentenciados:
        print(f"\n  Proceso: {s.numero_proceso}")
        print(f"  Fecha resolución: {s.fecha_resolucion}")
        print(f"  Infracción: {s.infraccion}")
        print(f"  PDF: {s.ruta_pdf}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()