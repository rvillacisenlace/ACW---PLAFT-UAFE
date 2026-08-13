"""
Portal de Sentenciados (Función Judicial - AngularJS, distinto a JSF).
Solo requiere captura de evidencia (screenshot), sin descarga de PDF.
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta
from src.documentos.evidencia import capturar_evidencia

TEXTO_SIN_REGISTROS = "No existen registros de sentencias"


class ScraperSentenciados(BaseScraper):
    nombre_sitio = "Sentenciados"

    def tiene_captcha(self, page: Page) -> bool:
        # TODO: no se ha confirmado si este portal presenta captcha -
        # verificar con uso real.
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> dict:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        # Cambiar el radio de búsqueda de "Nombre" (default) a "Cédula"
        page.click("#radio_1")
        self.delay_humano(0.5, 1.0)

        page.fill("#input_3", cliente.identificacion)
        self.delay_humano(0.5, 1.0)

        page.click("button:has-text('Buscar')")
        self.delay_humano(2.0, 3.0)

        contenido = page.content()
        tiene_registros = TEXTO_SIN_REGISTROS not in contenido

        capturar_evidencia(
            page, cliente.identificacion,
            sitio="sitio_sentenciados"
        )

        return {"tiene_antecedentes": tiene_registros}