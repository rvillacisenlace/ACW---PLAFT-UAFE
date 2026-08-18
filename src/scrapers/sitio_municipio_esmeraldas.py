"""
Municipio de Esmeraldas - Consulta de deudas. Sin captcha, doble
validación siempre activa (cédula y RUC, en ambas direcciones), misma
lógica de combinación que Ambato (prioriza deuda mayor a cero).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, DeudaMunicipal
from src.documentos.evidencia import capturar_evidencia


class ScraperMunicipioEsmeraldas(BaseScraper):
    nombre_sitio = "Municipio de Esmeraldas"

    def tiene_captcha(self, page: Page) -> bool:
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> DeudaMunicipal:
        identificacion_original = cliente.identificacion.strip()

        if len(identificacion_original) == 10:
            cedula = identificacion_original
            ruc = f"{identificacion_original}001"
        elif len(identificacion_original) == 13:
            ruc = identificacion_original
            cedula = identificacion_original[:10]
        else:
            return DeudaMunicipal(registrado=False, mensaje="Identificación con formato inesperado.")

        resultado_cedula = self._consultar_una_vez(page, cedula)
        resultado_ruc = self._consultar_una_vez(page, ruc)

        return self._combinar_resultados(resultado_cedula, resultado_ruc)

    def _consultar_una_vez(self, page: Page, identificacion: str) -> DeudaMunicipal:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        page.fill("#txtid", identificacion)
        self.delay_humano(0.5, 1.0)

        page.click("button:has-text('Consultar')")
        self.delay_humano(2.0, 3.0)

        # Sin registro: la página no cambia, el campo de total no aparece
        campo_total = page.locator("input[style*='color: green']")
        if campo_total.count() == 0:
            return DeudaMunicipal(registrado=False, mensaje="Sin registro - la página no mostró resultados.")

        try:
            valor_total = campo_total.input_value().strip()
        except Exception:
            valor_total = ""

        capturar_evidencia(page, identificacion, sitio="sitio_municipio_esmeraldas_resultado", carpeta_sitio="municipio_esmeraldas")

        tiene_deuda = valor_total not in ("$ 0.00", "$0.00", "")
        return DeudaMunicipal(registrado=True, tiene_deuda=tiene_deuda, valor_total=valor_total)

    def _combinar_resultados(self, resultado_a: DeudaMunicipal, resultado_b: DeudaMunicipal) -> DeudaMunicipal:
        if resultado_a.tiene_deuda and not resultado_b.tiene_deuda:
            return resultado_a
        if resultado_b.tiene_deuda and not resultado_a.tiene_deuda:
            return resultado_b
        if resultado_a.tiene_deuda and resultado_b.tiene_deuda:
            valor_a = self._parsear_valor(resultado_a.valor_total)
            valor_b = self._parsear_valor(resultado_b.valor_total)
            return resultado_a if valor_a >= valor_b else resultado_b
        if resultado_a.registrado:
            return resultado_a
        if resultado_b.registrado:
            return resultado_b
        return resultado_a

    def _parsear_valor(self, valor_texto: str) -> float:
        try:
            return float(valor_texto.replace("$", "").replace(",", "").strip())
        except (ValueError, AttributeError):
            return 0.0