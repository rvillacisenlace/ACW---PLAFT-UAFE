from playwright.sync_api import sync_playwright
from src.scrapers.sitio_sercop_proveedor import ScraperSERCOPProveedor
from src.core.models import Cliente, TipoPersona

URL_SERCOP_PROVEEDOR = "https://www.compraspublicas.gob.ec/ProcesoContratacion/compras/EP/BusquedaProveedorCpc.cpe#"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    scraper = ScraperSERCOPProveedor(context=context, url_base=URL_SERCOP_PROVEEDOR)
    cliente = Cliente(identificacion="0990014094001", tipo_persona=TipoPersona.JURIDICA, razon_social="INDUAUTO S.A.")

    resultado = scraper.buscar_cliente(page, cliente)
    print(f"\n¿Es proveedor?: {resultado['es_proveedor']}")
    print(f"Estado: {resultado['estado']}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()