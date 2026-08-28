from playwright.sync_api import sync_playwright

from src.scrapers.sitio_fiscalia import ScraperFiscalia
from src.core.models import Cliente, TipoPersona

URL_FISCALIA_NOTICIAS = "https://www.gestiondefiscalias.gob.ec/siaf/informacion/web/noticiasdelito"
URL_FISCALIA_TOTEM = "https://www.gestiondefiscalias.gob.ec/siaf/informacion/web/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    scraper = ScraperFiscalia(context=context, url_base=URL_FISCALIA_NOTICIAS)
    cliente = Cliente(identificacion="1793232200001", tipo_persona=TipoPersona.JURIDICA, razon_social="AVALOR HOLDING S.A.S.")

    denuncias = scraper.buscar_cliente(page, cliente)
    print(f"\nTotal de denuncias: {len(denuncias)}\n")
    for d in denuncias:
        print(f"  Número noticia del delito: {d.numero_noticia_delito}")
        print(f"  Lugar: {d.lugar}")
        print(f"  Delito: {d.delito}")
        print(f"  Nombre sospechoso: {d.nombre_sospechoso}")
        print()

    input("Presiona ENTER para cerrar...")
    browser.close()