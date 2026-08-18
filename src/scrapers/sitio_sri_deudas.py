"""
Consulta de Deudas Firmes, Impugnadas y en Facilidades de Pago (SRI).
Reutiliza el mismo campo de búsqueda (#busquedaRucId) y la misma
estrategia de bloqueo/respaldo por razón social que Consulta de RUC.

Solo se extrae el valor de "Deudas FIRMES" - impugnadas y facilidades
de pago quedan fuera de alcance por decisión de negocio.
"""
from playwright.sync_api import Page

from src.scrapers.sitio_sri import ScraperSRI
from src.core.models import Cliente, DeudaSRI
from src.core.models import Cliente, DeudaSRI, ResultadoConsulta
from src.scrapers.base_scraper import ScraperError


class ScraperSRIDeudas(ScraperSRI):
    nombre_sitio = "SRI - Consulta de Deudas Firmes"

    def consultar_deudas(self, page: Page, cliente: Cliente) -> DeudaSRI:
        """
        Reutiliza el flujo de búsqueda de la clase padre (RUC directo
        con respaldo por razón social ante bloqueo), pero sin el paso
        de "Mostrar establecimientos" (no aplica en este portal).
        """
        import random
        from playwright_stealth import Stealth
        from src.core.models import ResultadoConsulta, TipoPersona
        from src.scrapers.base_scraper import ScraperError

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

        from src.documentos.evidencia import capturar_evidencia
        capturar_evidencia(page, cliente.identificacion, sitio="sitio_sri_deudas_resultado", carpeta_sitio="sri")

        return self._extraer_deuda_firme(page)

    def _extraer_deuda_firme(self, page: Page) -> DeudaSRI:
        # Caso 1: mensaje único de "sin ningún tipo de deuda"
        mensaje_sin_deudas = page.locator(
            "text=no registra deudas firmes, impugnadas o en facilidades de pago"
        )
        if mensaje_sin_deudas.count() > 0:
            return DeudaSRI(
                tiene_deuda_firme=False,
                valor_deuda_firme="$0.00",
                mensaje="El ciudadano/contribuyente no registra deudas firmes, impugnadas o en facilidades de pago.",
            )

        # Caso 2: estructura con secciones separadas - solo tomamos "Deudas firmes"
        try:
            seccion_firmes = page.locator("sri-mostrar-deudas").filter(
                has=page.locator("h3", has_text="Deudas firmes")
            )
            valor_total = seccion_firmes.locator(
                "span:has-text('Valor total')"
            ).locator("xpath=following::span[1]").inner_text().strip()

            tiene_deuda = valor_total not in ("$0.00", "USD $0.00", "")
            return DeudaSRI(tiene_deuda_firme=tiene_deuda, valor_deuda_firme=valor_total, mensaje="")
        except Exception:
            return DeudaSRI(tiene_deuda_firme=False, valor_deuda_firme="", mensaje="No se pudo extraer el valor de deudas firmes.")

    def _clic_consultar_robusto(self, page: Page, max_intentos: int = 5) -> None:
        """
        Hace clic en "Consultar" de forma robusta ante el spinner
        (sri-splash) que puede aparecer/desaparecer varias veces durante
        una carga compleja - confirmado empíricamente que "esperar
        oculto -> clic inmediato" pierde la ventana si el spinner vuelve
        a aparecer justo antes del clic. Se usa un timeout corto por
        intento para fallar rápido y reintentar, en vez de esperar el
        timeout completo de Playwright en cada vuelta.
        """
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
                    print(f"    [{self.nombre_sitio}] Clic bloqueado por spinner - clic sobre el overlay y reintentando ({intento}/{max_intentos})...")
                    try:
                        # Clic directo sobre el overlay gris de bloqueo
                        # (ui-blockui-document) - confirmado manualmente
                        # que un clic ahí "despierta" el render atascado,
                        # a diferencia de un clic en cualquier otro lugar.
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
        """
        Espera activamente a que aparezca CUALQUIERA de los 2 resultados
        posibles (mensaje de "sin deudas" o la sección "Deudas firmes").
        Si no aparece a tiempo, reintenta el clic de forma robusta.
        """
        for intento in range(max_reintentos + 1):
            try:
                page.wait_for_function(
                    """() => {
                        const texto = document.body.innerText;
                        return texto.includes('no registra deudas firmes') ||
                               texto.includes('Deudas firmes');
                    }""",
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