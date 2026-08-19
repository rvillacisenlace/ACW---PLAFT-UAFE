"""
tests/prueba_manual_antecedentes_penales.py
"""
from playwright.sync_api import sync_playwright
from src.scrapers.sitio_antecedentes_penales import ScraperAntecedentesPenales
from src.core.models import Cliente, TipoPersona

URL_ANTECEDENTES_PENALES = "https://certificados.ministeriodelinterior.gob.ec/gestorcertificados/antecedentes/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()

    scraper = ScraperAntecedentesPenales(context=context, url_base=URL_ANTECEDENTES_PENALES)
    cliente = Cliente(
        identificacion="1001322518",
        tipo_persona=TipoPersona.NATURAL,
        nombres_completos="Torres Gordillo Diego Patricio",
    )

    input("Presiona ENTER cuando estés listo para continuar y resolver el captcha si aparece...")
    resultado = scraper.buscar_cliente(page, cliente)

    print(f"\n{'='*60}")
    print(f"Nombre: {resultado.nombre}")
    print(f"Tipo de documento: {resultado.tipo_documento}")
    print(f"Número de documento: {resultado.numero_documento}")
    print(f"Posee antecedentes: {resultado.posee_antecedentes}")
    print(f"PDF: {resultado.ruta_pdf}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()