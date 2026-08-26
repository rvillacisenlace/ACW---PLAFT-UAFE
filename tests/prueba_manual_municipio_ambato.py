from playwright.sync_api import sync_playwright
from src.scrapers.sitio_municipio_ambato import ScraperMunicipioAmbato
from src.core.models import Cliente, TipoPersona

URL_MUNICIPIO_AMBATO = "https://gadmaapps.ambato.gob.ec:9001/apex/f?p=102:9:2530006028746:::9::"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    scraper = ScraperMunicipioAmbato(context=context, url_base=URL_MUNICIPIO_AMBATO)
    cliente = Cliente(identificacion="1800027847001", tipo_persona=TipoPersona.NATURAL, nombres_completos="NARANJO LALAMA MARIANA DE JESUS")

    resultado = scraper.buscar_cliente(page, cliente)
    print(f"\n¿Registrado?: {resultado.registrado}")
    print(f"¿Tiene deuda?: {resultado.tiene_deuda}")
    print(f"Valor total: {resultado.valor_total}")
    print(f"Mensaje: {resultado.mensaje}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()