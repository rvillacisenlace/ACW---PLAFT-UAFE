from playwright.sync_api import sync_playwright
from src.scrapers.sitio_sercop_certificados import ScraperSERCOPCertificados
from src.core.models import Cliente, TipoPersona

URL_SERCOP_CERTIFICADOS = "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/FO/formularioCertificados.cpe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    scraper = ScraperSERCOPCertificados(context=context, url_base=URL_SERCOP_CERTIFICADOS)
    cliente = Cliente(identificacion="0990014094001", tipo_persona=TipoPersona.JURIDICA, razon_social="INDUAUTO S.A.")

    # RUC del representante legal (Xavier Molestina) - cédula derivada a
    # RUC (+001), ya que el campo #rucRepre exige 13 dígitos.
    ruc_representante = "1714341672001"

    resultado = scraper.buscar_cliente(page, cliente, ruc_representante_legal=ruc_representante)
    print(f"\nContratos pendientes: {resultado['contratos_pendientes']['resultado']}")
    print(f"  PDF: {resultado['contratos_pendientes'].get('ruta_pdf', '')}")
    print(f"Incumplimientos: {resultado['incumplimientos']['resultado']}")
    print(f"  PDF: {resultado['incumplimientos'].get('ruta_pdf', '')}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()