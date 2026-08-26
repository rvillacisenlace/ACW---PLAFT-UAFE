"""
Municipio de Manta - Consulta de deudas (Rentas, Predios, EPAM).
Selector de tipo de búsqueda -> Cédula/RUC/Pasaporte, reCAPTCHA v2
(resolución automática vía 2Captcha, con respaldo manual si falla).

Confirmado que cédula y RUC devuelven el mismo valor - no se necesita
lógica de combinación como en Ambato/Esmeraldas, basta un solo intento
válido.
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, DeudaMunicipal
from src.documentos.evidencia import capturar_evidencia
from src.captcha.resolver import resolver_con_2captcha, CaptchaResolverError
from config.settings import cargar_infra_config


class ScraperMunicipioManta(BaseScraper):
    nombre_sitio = "Municipio de Manta"

    def tiene_captcha(self, page: Page) -> bool:
        return page.locator("iframe[title*='reCAPTCHA']").count() > 0

    def buscar_cliente(self, page: Page, cliente: Cliente) -> DeudaMunicipal:
        """
        Doble validación como red de seguridad (aunque se confirmó que
        cédula y RUC suelen dar el mismo valor en este portal) - misma
        lógica de combinación que Ambato/Esmeraldas.
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

        resultado_cedula = self._consultar_una_vez(page, cedula, cliente.identificacion)
        resultado_ruc = self._consultar_una_vez(page, ruc, cliente.identificacion)

        return self._combinar_resultados(resultado_cedula, resultado_ruc)

    def _consultar_una_vez(self, page: Page, identificacion: str, identificacion_evidencia: str) -> DeudaMunicipal:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        page.select_option("#tipo_documento", "2")
        self.delay_humano(0.5, 1.0)

        page.fill("#txtclave", identificacion)
        self.verificar_campo_lleno(page, "#txtclave", identificacion)
        self.delay_humano(0.5, 1.0)

        if self.tiene_captcha(page):
            self._resolver_captcha_manual(page)

        page.click("#btnbuscar_2")
        self.delay_humano(2.5, 3.5)

        return self._extraer_resultado(page, identificacion_evidencia)

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

    def _resolver_captcha_manual(self, page: Page) -> None:
        infra = cargar_infra_config()
        if infra.captcha_enabled and infra.captcha_api_key:
            try:
                resolver_con_2captcha(page, infra.captcha_api_key)
                print(f"[{self.nombre_sitio}] reCAPTCHA resuelto automáticamente.\n")
                return
            except CaptchaResolverError as e:
                print(f"[{self.nombre_sitio}] 2Captcha falló: {e} - cayendo a manual...\n")

        print(f"\n{'='*60}")
        print(f"CAPTCHA reCAPTCHA v2 - {self.nombre_sitio}")
        print(f"Resuelve el captcha en el navegador.")
        input("Cuando termines, presiona ENTER aquí para continuar...")
        print(f"{'='*60}\n")

    def _extraer_resultado(self, page: Page, identificacion: str) -> DeudaMunicipal:
        try:
            elemento_total = page.locator("h2:has-text('EL TOTAL DE DEUDAS ES DE')").locator("strong")
            valor_total = elemento_total.inner_text().strip()
        except Exception:
            capturar_evidencia(page, identificacion, sitio="sitio_municipio_manta_resultado", carpeta_sitio="municipio_manta")
            return DeudaMunicipal(registrado=False, mensaje="No se pudo extraer el total de deudas - posible registro no encontrado.")

        capturar_evidencia(page, identificacion, sitio="sitio_municipio_manta_resultado", carpeta_sitio="municipio_manta")

        tiene_deuda = valor_total not in ("$0.00", "$ 0.00", "")
        return DeudaMunicipal(registrado=True, tiene_deuda=tiene_deuda, valor_total=valor_total)