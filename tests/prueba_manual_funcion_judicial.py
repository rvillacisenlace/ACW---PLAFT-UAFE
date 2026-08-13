from playwright.sync_api import sync_playwright
from src.scrapers.sitio_funcion_judicial import ScraperFuncionJudicial
from src.core.models import Cliente, TipoPersona

URL_FUNCION_JUDICIAL = "https://consultas.funcionjudicial.gob.ec/informacionjudicial/public/informacion.jsf"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=200)
    context = browser.new_context()
    page = context.new_page()

    scraper = ScraperFuncionJudicial(context=context, url_base=URL_FUNCION_JUDICIAL)
    cliente = Cliente(
        identificacion="1001322518",
        tipo_persona=TipoPersona.NATURAL,
        nombres_completos="Torres Gordillo Diego Patricio",
    )

    procesos, total_relevantes, tematica = scraper.buscar_y_procesar_cliente(page, cliente)

    print(f"\n{'='*60}")
    print(f"Total de procesos: {len(procesos)}")
    print(f"Total de procesos encontrados: {total_relevantes}")
    print(f"Temática general: {tematica}")
    for proceso in procesos:
        print(f"\n  Número: {proceso.numero_proceso}")
        print(f"  Lugar: {proceso.lugar}")
        print(f"  Materia: {proceso.materia}")
        print(f"  Demandado: {proceso.demandado}")
        print(f"  Omitido por volumen: {proceso.omitido_por_volumen}")
        print(f"  Excluido por materia: {proceso.excluido_por_materia}")

    input("\nPresiona ENTER para cerrar...")
    browser.close()