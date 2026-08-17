from playwright.sync_api import sync_playwright
from src.scrapers.sitio_sri import ScraperSRI
from src.core.models import Cliente, TipoPersona

URL_SRI_RUC = "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context()
    page = context.new_page()

    scraper = ScraperSRI(context=context, url_base=URL_SRI_RUC)
    cliente = Cliente(identificacion="0990014094001", tipo_persona=TipoPersona.JURIDICA, razon_social="INDUAUTO S.A.")
    datos = scraper.consultar_ruc(page, cliente)
    print("Datos extraídos:")
    for clave, valor in datos.items():
        print(f"  {clave}: {valor}")

    print(f"  representante_legal_nombre: {datos['representante_legal_nombre']}")
    print(f"  representante_legal_identificacion: {datos['representante_legal_identificacion']}")
    print(f"  contribuyente_fantasma: {datos['contribuyente_fantasma']}")
    print(f"  contribuyente_transacciones_inexistentes: {datos['contribuyente_transacciones_inexistentes']}")

    input("Presiona ENTER para cerrar...")
    browser.close()