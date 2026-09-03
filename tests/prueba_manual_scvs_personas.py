from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from src.scrapers.sitio_scvs_personas import ScraperSCVSPersonas
from src.core.models import Cliente, TipoPersona

URL_SCVS_PERSONAS = "https://appscvs1.supercias.gob.ec/consultaPersona/consulta_cia_param.zul"
URL_SRI_RUC = "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel="chrome")
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    Stealth().apply_stealth_sync(page)

    scraper = ScraperSCVSPersonas(context=context, url_base=URL_SCVS_PERSONAS, url_base_sri=URL_SRI_RUC)

    cliente = Cliente(identificacion="1801099787", tipo_persona=TipoPersona.NATURAL, nombres_completos="VASCONEZ CALLEJAS HERNAN FRANCISCO")

    resultado = scraper.buscar_cliente(page, cliente)

    print(f"\nTotal de participaciones societarias encontradas: {len(resultado)}\n")
    for p_soc in resultado:
        print(f"  RUC: {p_soc.ruc_empresa}")
        print(f"  Nombre: {p_soc.nombre_empresa}")
        print(f"  Actividad Económica: {p_soc.actividad_economica}")
        print()

    input("Presiona ENTER para cerrar...")
    browser.close()