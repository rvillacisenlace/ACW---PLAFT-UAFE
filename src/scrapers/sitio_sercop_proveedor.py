"""
SERCOP - Búsqueda de Proveedor del Estado. Búsqueda directa por RUC
(derivado desde cédula si hace falta). Sin captcha.
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta
from src.documentos.evidencia import capturar_evidencia

MENSAJE_SIN_RESULTADOS = "No se ha encontrado ningún resultado."


class ScraperSERCOPProveedor(BaseScraper):
    nombre_sitio = "SERCOP - Búsqueda de Proveedor"

    def tiene_captcha(self, page: Page) -> bool:
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> dict:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        self._aceptar_cookies_si_aparece(page)

        ruc_a_consultar = (
            f"{cliente.identificacion}001"
            if len(cliente.identificacion.strip()) == 10
            else cliente.identificacion
        )

        page.fill("#ruc", ruc_a_consultar)
        self.delay_humano(0.5, 1.0)

        page.click("a:has-text('Buscar')")
        self.delay_humano(2.0, 3.0)

        return self._extraer_resultado(page, cliente)

    def _aceptar_cookies_si_aparece(self, page: Page) -> None:
        try:
            boton = page.locator("button.cc-dismiss")
            boton.wait_for(state="visible", timeout=5000)
            boton.click()
            self.delay_humano(0.5, 1.0)
        except Exception:
            pass

    def _extraer_resultado(self, page: Page, cliente: Cliente) -> dict:
        capturar_evidencia(page, cliente.identificacion, sitio="sitio_sercop_proveedor_resultado", carpeta_sitio="sercop")

        # Se revisa el texto completo de la página (no solo un <td>
        # específico) en busca de la frase clave, más flexible ante
        # posibles diferencias de estructura o espaciado.
        contenido_pagina = page.content()
        if "No se ha encontrado ningún resultado" in contenido_pagina:
            return {"es_proveedor": False, "estado": "NO ES PROVEEDOR DEL ESTADO"}

        return {"es_proveedor": True, "estado": "PROVEEDOR DEL ESTADO"}