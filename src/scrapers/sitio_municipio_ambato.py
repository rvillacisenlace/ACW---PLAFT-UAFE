"""
Municipio de Ambato (Oracle APEX) - Consulta de deudas. Doble
validación: cédula, y si no hay resultado, RUC derivado. Sin captcha.

Caso "no registrado": la página NO cambia tras el clic en Buscar (sin
mensaje de error explícito) - se detecta comparando si el campo de
total aparece o no, con un margen de espera corto ya que no hay
ninguna señal positiva de "terminó de procesar" distinta a eso.
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, DeudaMunicipal
from src.documentos.evidencia import capturar_evidencia


class ScraperMunicipioAmbato(BaseScraper):
    nombre_sitio = "Municipio de Ambato"

    def tiene_captcha(self, page: Page) -> bool:
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> DeudaMunicipal:
        """
        Doble validación SIEMPRE (no condicional): se consulta con
        cédula y con RUC derivado, sin importar el resultado del
        primero. Si ambos dan resultados con deuda distinta, se
        prioriza el que tenga deuda mayor a cero.
        """
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

    def _combinar_resultados(self, resultado_a: DeudaMunicipal, resultado_b: DeudaMunicipal) -> DeudaMunicipal:
        """
        Prioriza el resultado con deuda mayor a cero. Si ninguno tiene
        deuda, prioriza cualquiera que esté registrado. Si ninguno está
        registrado, devuelve el mensaje de "no registrado".
        """
        if resultado_a.tiene_deuda and not resultado_b.tiene_deuda:
            return resultado_a
        if resultado_b.tiene_deuda and not resultado_a.tiene_deuda:
            return resultado_b
        if resultado_a.tiene_deuda and resultado_b.tiene_deuda:
            # Ambos con deuda - se prioriza el de mayor valor (caso
            # ambiguo no confirmado con datos reales, decisión razonable
            # por defecto).
            valor_a = self._parsear_valor(resultado_a.valor_total)
            valor_b = self._parsear_valor(resultado_b.valor_total)
            return resultado_a if valor_a >= valor_b else resultado_b
        if resultado_a.registrado:
            return resultado_a
        if resultado_b.registrado:
            return resultado_b
        return resultado_a  # ninguno registrado - da igual cuál devolver

    def _parsear_valor(self, valor_texto: str) -> float:
        try:
            return float(valor_texto.replace("$", "").replace(",", "").strip())
        except (ValueError, AttributeError):
            return 0.0

    def _consultar_una_vez(self, page: Page, identificacion: str) -> DeudaMunicipal:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        page.fill("#P9_VALOR", identificacion)
        self.delay_humano(0.5, 1.0)

        page.click("#B10934304849187813087")
        self.delay_humano(2.5, 3.5)

        campo_total = page.locator("#P9_TOTALGENERAL")
        if campo_total.count() == 0:
            return DeudaMunicipal(
                registrado=False,
                mensaje="No se generaron resultados - registro mal ingresado o no posee registro.",
            )

        try:
            valor_total = campo_total.input_value().strip()
        except Exception:
            valor_total = ""

        capturar_evidencia(page, identificacion, sitio="sitio_municipio_ambato_resultado", carpeta_sitio="municipio_ambato")

        tiene_deuda = valor_total not in ("$0.00", "")
        return DeudaMunicipal(registrado=True, tiene_deuda=tiene_deuda, valor_total=valor_total)