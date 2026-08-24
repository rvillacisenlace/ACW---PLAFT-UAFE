from playwright.sync_api import sync_playwright
from src.scrapers.sitio_sri_deudas import ScraperSRIDeudas
from src.core.models import Cliente, TipoPersona

URL_SRI_DEUDAS = "https://srienlinea.sri.gob.ec/sri-en-linea/SriPagosWeb/ConsultaDeudasFirmesImpugnadas/Consultas/consultaDeudasFirmesImpugnadas"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context()
    page = context.new_page()

    scraper = ScraperSRIDeudas(context=context, url_base=URL_SRI_DEUDAS)
    cliente = Cliente(identificacion="1714337738", tipo_persona=TipoPersona.NATURAL, nombres_completos="ANDRADE ZARATE JUAN ANDRES")

    resultado = scraper.consultar_deudas(page, cliente)
    print(f"\n¿Tiene deuda firme?: {resultado.tiene_deuda_firme}")
    print(f"Valor: {resultado.valor_deuda_firme}")
    print(f"Mensaje: {resultado.mensaje}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()