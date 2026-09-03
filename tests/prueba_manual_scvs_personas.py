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

    # Cedula (10 digitos), no RUC - persona Natural
    cliente = Cliente(identificacion="1706794003", tipo_persona=TipoPersona.NATURAL, nombres_completos="CORREDOR CAMARGO SILVERIO")

    resultado = scraper.buscar_cliente(page, cliente)

    print(f"\nTotal como Presidente/RL (Z): {resultado['total_presidente_rl']}")
    print(f"Total como Accionista (AA): {resultado['total_accionista']}")
    print(f"\nParticipaciones en los slots ({len(resultado['participaciones'])}):\n")

    for p_soc in resultado["participaciones"]:
        print(f"  RUC: {p_soc.ruc_empresa}")
        print(f"  Nombre: {p_soc.nombre_empresa}")
        print(f"  Cargo: {p_soc.cargo}")
        print(f"  Capital Invertido: {p_soc.capital_invertido}")
        print(f"  Situación Legal: {p_soc.situacion_legal}")
        print(f"  Fecha de Constitución: {p_soc.fecha_constitucion}")
        print(f"  Actividad Económica: {p_soc.actividad_economica}")
        print(f"  Patrimonio (Último año): {p_soc.patrimonio_ultimo_anio}")
        print()

    input("Presiona ENTER para cerrar...")
    browser.close()