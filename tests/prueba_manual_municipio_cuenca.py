from playwright.sync_api import sync_playwright
from src.scrapers.sitio_municipio_cuenca import ScraperMunicipioCuenca
from src.core.models import Cliente, TipoPersona

URL_MUNICIPIO_CUENCA = "https://enlinea.cuenca.gob.ec/#/impuestos"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    scraper = ScraperMunicipioCuenca(context=context, url_base=URL_MUNICIPIO_CUENCA)
    cliente = Cliente(identificacion="0102610094", tipo_persona=TipoPersona.NATURAL, nombres_completos="Enderica Izquierdo Vladimir Fernando")

    resultado = scraper.buscar_cliente(page, cliente)
    print(f"\n¿Registrado?: {resultado.registrado}")
    print(f"¿Tiene deuda?: {resultado.tiene_deuda}")
    print(f"Valor total: {resultado.valor_total}")
    print(f"Mensaje: {resultado.mensaje}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()