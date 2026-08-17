"""
tests/prueba_manual_cadena_representante.py
"""
from playwright.sync_api import sync_playwright
from src.scrapers.sitio_sri import ScraperSRI
from src.scrapers.cadena_representante import resolver_representante_legal
from src.core.models import Cliente, TipoPersona

URL_SRI_RUC = "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context()
    page = context.new_page()

    scraper_sri = ScraperSRI(context=context, url_base=URL_SRI_RUC)
    cliente_induauto = Cliente(identificacion="0990014094001", tipo_persona=TipoPersona.JURIDICA, razon_social="INDUAUTO S.A.")

    resultado = resolver_representante_legal(page, scraper_sri, cliente_induauto)

    print(f"\n{'='*60}")
    print(f"¿Persona encontrada?: {resultado['persona_encontrada']}")
    print(f"Nombre: {resultado['nombre']}")
    print(f"Identificación: {resultado['identificacion']}")
    print(f"Mensaje: {resultado['mensaje']}")
    print(f"\nCadena completa ({len(resultado['cadena'])} nivel(es)):")
    for nivel_info in resultado['cadena']:
        print(f"  Nivel {nivel_info['nivel']}: {nivel_info}")
        print(f"\nDatos SRI del representante legal:")
    if resultado.get("datos_sri_persona"):
        for clave, valor in resultado["datos_sri_persona"].items():
            print(f"  {clave}: {valor}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()