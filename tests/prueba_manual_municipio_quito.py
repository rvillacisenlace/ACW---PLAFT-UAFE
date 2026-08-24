from playwright.sync_api import sync_playwright
from src.scrapers.sitio_municipio_quito import ScraperMunicipioQuito
from src.core.models import Cliente, TipoPersona

URL_MUNICIPIO_QUITO = "https://pago.quito.gob.ec/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    scraper = ScraperMunicipioQuito(context=context, url_base=URL_MUNICIPIO_QUITO)
    cliente = Cliente(identificacion="1715065445", tipo_persona=TipoPersona.NATURAL, nombres_completos="SEVILLA SANTANDER CARLOS ANDRES")

    resultado = scraper.buscar_cliente(page, cliente)
    print(f"\n¿Registrado?: {resultado.registrado}")
    print(f"¿Tiene deuda?: {resultado.tiene_deuda}")
    print(f"Valor total: {resultado.valor_total}")
    print(f"Mensaje: {resultado.mensaje}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()