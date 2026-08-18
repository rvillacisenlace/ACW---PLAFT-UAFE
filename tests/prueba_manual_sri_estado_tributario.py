from playwright.sync_api import sync_playwright
from src.scrapers.sitio_sri_estado_tributario import ScraperSRIEstadoTributario
from src.core.models import Cliente, TipoPersona

URL_SRI_ESTADO_TRIBUTARIO = "https://srienlinea.sri.gob.ec/sri-en-linea/SriDeclaracionesWeb/EstadoTributario/Consultas/consultaEstadoTributario"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context()
    page = context.new_page()

    scraper = ScraperSRIEstadoTributario(context=context, url_base=URL_SRI_ESTADO_TRIBUTARIO)
    cliente = Cliente(identificacion="0850513433", tipo_persona=TipoPersona.NATURAL, nombres_completos="Villacis Olivo Rommel Joerick")

    resultado = scraper.consultar_estado_tributario(page, cliente)
    print(f"\nResultado: {resultado.resultado}")
    print(f"Obligaciones pendientes: {resultado.obligaciones_pendientes}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()