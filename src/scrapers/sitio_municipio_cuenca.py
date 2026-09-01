"""
Municipio de Cuenca - Consulta de deudas. Búsqueda directa por
cédula/RUC (sin captcha). Doble validación: primero cédula, si no hay
registro, reintenta con RUC derivado (+001).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, DeudaMunicipal, TipoPersona
from src.documentos.evidencia import capturar_evidencia

MENSAJE_NO_REGISTRADO = "Número de identificación incorrecto o no se encuentra registrado como contribuyente"


class ScraperMunicipioCuenca(BaseScraper):
    nombre_sitio = "Municipio de Cuenca"

    def tiene_captcha(self, page: Page) -> bool:
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> DeudaMunicipal:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        self._aceptar_cookies_si_aparece(page)

        # Primer intento: cédula directa
        resultado = self._consultar_una_vez(page, cliente.identificacion, cliente.identificacion)
        if resultado.registrado:
            return resultado

        # Segundo intento: RUC derivado (solo tiene sentido si la
        # identificación original es una cédula de 10 dígitos)
        if len(cliente.identificacion.strip()) == 10:
            ruc_derivado = f"{cliente.identificacion}001"
            self._recargar_pagina_robusto(page)
            self._aceptar_cookies_si_aparece(page)
            resultado = self._consultar_una_vez(page, ruc_derivado, cliente.identificacion)

        return resultado

    def _recargar_pagina_robusto(self, page: Page) -> None:
        """
        Recarga forzada de la SPA (ruta hash #/impuestos) - confirmado
        que un simple goto() a la misma URL puede dejar la app en un
        estado intermedio donde el campo nunca vuelve a aparecer.
        page.reload() fuerza una recarga real del navegador, más
        confiable que goto() a una URL idéntica.
        """
        page.goto(self.url_base)
        try:
            page.reload(wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
        self.delay_humano(2.0, 3.0)

    def _aceptar_cookies_si_aparece(self, page: Page) -> None:
        try:
            boton = page.locator("#rcc-confirm-button")
            boton.wait_for(state="visible", timeout=5000)
            boton.click()
            self.delay_humano(0.5, 1.0)
        except Exception:
            pass

    def _consultar_una_vez(self, page: Page, identificacion: str, identificacion_evidencia: str) -> DeudaMunicipal:
        """
        identificacion: valor usado para BUSCAR (puede ser cedula o RUC
        derivado). identificacion_evidencia: SIEMPRE la identificacion
        original del cliente (cliente.identificacion) - para que toda la
        evidencia de un mismo cliente quede en UNA sola carpeta, sin
        importar con cual variante (cedula/RUC) se hizo la busqueda real.
        Confirmado bug real: antes se usaba 'identificacion' (variable),
        partiendo la evidencia en 2 carpetas para el mismo cliente.
        """
        page.wait_for_selector("#inputCampo", state="visible", timeout=25000)
        page.fill("#inputCampo", identificacion)
        self.verificar_campo_lleno(page, "#inputCampo", identificacion)
        self.delay_humano(0.5, 1.0)

        boton_consultar = page.locator("button[aria-label='Consultar']")
        for _ in range(10):
            if boton_consultar.is_enabled():
                break
            page.wait_for_timeout(300)
        boton_consultar.click()
        self.delay_humano(2.0, 3.0)

        # Caso: no registrado (diálogo modal) - se captura evidencia, se
        # lee el mensaje, y RECIÉN DESPUÉS se cierra con "Aceptar"
        # (confirmado que el modal no se cierra solo).
        dialogo_no_registrado = page.locator(f"text={MENSAJE_NO_REGISTRADO}")
        if dialogo_no_registrado.count() > 0:
            capturar_evidencia(page, identificacion_evidencia, sitio="sitio_municipio_cuenca_resultado", carpeta_sitio="municipio_cuenca")

            try:
                page.locator("button[aria-label='Aceptar']").click()
                self.delay_humano(0.5, 1.0)
            except Exception:
                pass

            return DeudaMunicipal(registrado=False, mensaje=MENSAJE_NO_REGISTRADO, tiene_deuda=False, valor_total="$0.00")

        # Caso: registrado, con o sin deuda
        try:
            valor_total = page.locator("#divTotales .gad-texto-grande").inner_text().strip()
        except Exception:
            valor_total = ""

            capturar_evidencia(page, identificacion_evidencia, sitio="sitio_municipio_cuenca_resultado", carpeta_sitio="municipio_cuenca")
        tiene_deuda = valor_total not in ("$ 0.00", "$0.00", "")
        return DeudaMunicipal(registrado=True, tiene_deuda=tiene_deuda, valor_total=valor_total)