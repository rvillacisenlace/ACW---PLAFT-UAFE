from playwright.sync_api import sync_playwright
from src.scrapers.sitio_scvs_companias import ScraperSCVSCompanias
from src.core.models import Cliente, TipoPersona

URL_SCVS_COMPANIAS = "https://appscvsgen.supercias.gob.ec/consultaCompanias/societario/busquedaCompanias.jsf"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)   # <- AQUÍ, con el parámetro agregado
    page = context.new_page()

    scraper = ScraperSCVSCompanias(context=context, url_base=URL_SCVS_COMPANIAS)
    cliente = Cliente(identificacion="0990014094001", tipo_persona=TipoPersona.JURIDICA, razon_social="INDUAUTO S.A.")

    resultado = scraper.buscar_cliente(page, cliente)
    print(f"\nRUC: {resultado.ruc}")
    print(f"Expediente: {resultado.expediente}")
    print(f"Representante legal (SCVS, referencia): {resultado.representante_legal_scvs_referencia}")
    print(f"Capital social: {resultado.capital_social}")
    print(f"Situación legal: {resultado.situacion_legal}")
    print(f"Cumplimiento: {resultado.cumplimiento_obligaciones}")
    print(f"PDF: {resultado.ruta_pdf}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()