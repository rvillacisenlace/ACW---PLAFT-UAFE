"""
Consulta de Estado Tributario (SRI). Reutiliza el mismo campo de
búsqueda (#busquedaRucId) y el manejo robusto de spinner ya confirmado
en Consulta de Deudas Firmes.
"""
import random
from playwright.sync_api import Page
from playwright_stealth import Stealth

from src.scrapers.sitio_sri import ScraperSRI
from src.scrapers.base_scraper import ScraperError
from src.core.models import Cliente, EstadoTributarioSRI, ResultadoConsulta, TipoPersona


class ScraperSRIEstadoTributario(ScraperSRI):
    nombre_sitio = "SRI - Estado Tributario"

    def consultar_estado_tributario(self, page: Page, cliente: Cliente) -> EstadoTributarioSRI:
        Stealth().apply_stealth_sync(page)
        page.goto(self.url_base)
        self.delay_humano(6.0, 9.0)

        for _ in range(3):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            page.mouse.move(x, y, steps=random.randint(10, 25))
            page.wait_for_timeout(random.randint(300, 800))

        ruc_a_consultar = (
            f"{cliente.identificacion}001"
            if len(cliente.identificacion.strip()) == 10
            else cliente.identificacion
        )
        page.fill("#busquedaRucId", ruc_a_consultar)
        self.delay_humano(4.0, 6.0)

        page.mouse.wheel(0, random.randint(50, 150))
        page.wait_for_timeout(random.randint(500, 1000))

        self._clic_consultar_robusto(page)
        self._esperar_resultado_con_reintento(page)

        if self.tiene_captcha(page):
            nombre_o_razon_social = (
                cliente.nombres_completos if cliente.tipo_persona == TipoPersona.NATURAL
                else cliente.razon_social
            )
            page.goto(self.url_base)
            self.delay_humano(6.0, 9.0)
            self._buscar_por_razon_social(page, nombre_o_razon_social)
            self._esperar_resultado_con_reintento(page)

            if self.tiene_captcha(page):
                raise ScraperError(
                    f"[{self.nombre_sitio}] Bloqueo persiste incluso con búsqueda por razón social.",
                    resultado=ResultadoConsulta.ERROR_CAPTCHA,
                )

        self.delay_humano(1.5, 2.5)
        return self._extraer_estado_tributario(page)

    def _clic_consultar_robusto(self, page: Page, max_intentos: int = 5) -> None:
        """Mismo mecanismo confirmado en Consulta de Deudas Firmes."""
        for intento in range(1, max_intentos + 1):
            try:
                page.wait_for_selector(".sri-splash", state="hidden", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(400)
            try:
                page.locator("button:has-text('Consultar')").first.click(timeout=4000)
                return
            except Exception:
                if intento < max_intentos:
                    try:
                        overlay = page.locator(".ui-blockui-document")
                        if overlay.count() > 0:
                            overlay.first.click(force=True, timeout=2000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)
                    continue
                else:
                    raise ScraperError(
                        f"[{self.nombre_sitio}] No se pudo hacer clic en Consultar tras {max_intentos} intentos - spinner persistente.",
                        resultado=ResultadoConsulta.TIMEOUT,
                    )

    def _esperar_resultado_con_reintento(self, page: Page, max_reintentos: int = 2) -> None:
        for intento in range(max_reintentos + 1):
            try:
                page.wait_for_function(
                    """() => document.body.innerText.includes('Estado tributario')""",
                    timeout=10000,
                )
                return
            except Exception:
                if intento < max_reintentos:
                    print(f"    [{self.nombre_sitio}] Página sin terminar de cargar - reintentando clic ({intento + 1}/{max_reintentos})...")
                    self._clic_consultar_robusto(page)
                    self.delay_humano(2.0, 3.0)
                else:
                    print(f"    [{self.nombre_sitio}] Advertencia: la página no confirmó resultado tras {max_reintentos} reintentos.")

    def _extraer_estado_tributario(self, page: Page) -> EstadoTributarioSRI:
        resultado = EstadoTributarioSRI()

        try:
            resultado.resultado = page.locator(
                "span.sri-bold:has-text('Resultado')"
            ).locator("xpath=following::span[1]").inner_text().strip()
        except Exception:
            pass

        try:
            filas = page.locator("p-datatable tbody tr").all()
            partes = []
            for fila in filas:
                celdas = fila.locator("td")
                if celdas.count() < 2:
                    continue
                obligacion = celdas.nth(0).locator("span.ui-cell-data").inner_text().strip()
                periodo = celdas.nth(1).locator("span.ui-cell-data").inner_text().strip()
                if obligacion:
                    partes.append(f"{obligacion} {periodo}".strip())
            resultado.obligaciones_pendientes = " / ".join(partes)
        except Exception:
            pass

        return resultado