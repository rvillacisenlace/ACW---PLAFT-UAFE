from playwright.sync_api import Page
from playwright_stealth import Stealth

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta

ID_CAMPO_RUC = "#busquedaRucId"


class ScraperSRI(BaseScraper):
    nombre_sitio = "SRI - Consulta de RUC"

    def tiene_captcha(self, page: Page) -> bool:
        """
        Este portal usa reCAPTCHA v3 (invisible) - el badge de Google
        SIEMPRE está presente en el DOM, esté la sesión bloqueada o no,
        así que NO sirve como señal de detección (confirmado: era un
        falso positivo). La señal real de bloqueo es el mensaje textual
        "Puntaje bajo" que el WAF del SRI devuelve cuando el puntaje de
        confianza de la sesión cae debajo del umbral (0.5).
        """
        return "Puntaje bajo" in page.content()

    def consultar_ruc(self, page: Page, cliente: Cliente) -> dict:
        """
        Consulta el RUC (o cédula+001 derivado) y extrae los datos
        básicos del contribuyente, actividad económica, fechas, y
        establecimiento matriz.

        NOTA IMPORTANTE: este portal usa reCAPTCHA v3 (invisible, sin
        checkbox) - a diferencia de Función Judicial, no hay nada que
        "resolver" manualmente. El sistema asigna un puntaje de confianza
        basado en el comportamiento de la sesión (fingerprint del
        navegador, velocidad de interacción). Se aplica stealth_sync
        para reducir las señales de automatización detectables, y delays
        más generosos que en otros scrapers.
        """
        Stealth().apply_stealth_sync(page)
        page.goto(self.url_base)
        self.delay_humano(6.0, 9.0)

        # El SRI SOLO acepta RUC (13 dígitos) en este campo, nunca cédula
        # sola (10 dígitos) - a diferencia de Función Judicial, aquí no
        # hay opción de buscar con cédula directa. Si la identificación
        # del cliente es una cédula, se deriva el RUC agregando "001"
        # (convención ecuatoriana para personas naturales con RUC propio).
        ruc_a_consultar = (
            f"{cliente.identificacion}001"
            if len(cliente.identificacion.strip()) == 10
            else cliente.identificacion
        )
        print(f"[{self.nombre_sitio}] Consultando con: {ruc_a_consultar}")
        page.fill(ID_CAMPO_RUC, ruc_a_consultar)
        self.delay_humano(4.0, 6.0)

        # Primer clic en "Consultar" - se habilita tras escribir
        botones_consultar = page.locator("button:has-text('Consultar')")
        botones_consultar.first.click()
        self.delay_humano(5.0, 8.0)

        if self.tiene_captcha(page):
            raise ScraperError(
                f"[{self.nombre_sitio}] Captcha detectado tras primera consulta.",
                resultado=ResultadoConsulta.ERROR_CAPTCHA,
            )

        # Segundo clic en "Consultar" (mostrar establecimientos) - aparece
        # una sección nueva con OTRO botón del mismo texto. Esperamos a
        # que haya al menos 2 botones "Consultar" visibles antes de hacer
        # clic en el segundo (índice 1), para no hacer clic prematuro.
        page.wait_for_function(
            """() => document.querySelectorAll('button').length > 0 &&
                     Array.from(document.querySelectorAll('button'))
                       .filter(b => b.innerText.includes('Consultar')).length >= 2""",
            timeout=10000,
        )
        botones_consultar_actualizados = page.locator("button:has-text('Consultar')")
        botones_consultar_actualizados.nth(1).click()
        self.delay_humano(5.0, 8.0)

        return self._extraer_datos_contribuyente(page)

    def _extraer_datos_contribuyente(self, page: Page) -> dict:
        datos = {
            "razon_social": "",
            "estado_contribuyente": "",
            "actividad_economica": "",
            "fecha_inicio_actividades": "",
            "fecha_actualizacion": "",
            "fecha_cese_actividades": "",
            "fecha_reinicio_actividades": "",
            "establecimientos": [],
        }

        try:
            datos["razon_social"] = page.locator(
                "div.sri-bold:has-text('Razón social')"
            ).locator("xpath=following::span[contains(@class,'titulo-consultas-1')][1]").inner_text().strip()
        except Exception:
            pass

        try:
            # El color de esta clase puede variar según el estado real
            # (confirmado "verde" para ACTIVO, otros estados sin validar).
            datos["estado_contribuyente"] = page.locator(
                "div.sri-bold:has-text('Estado contribuyente en el RUC')"
            ).locator("xpath=following::span[1]").inner_text().strip()
        except Exception:
            pass

        try:
            datos["actividad_economica"] = page.locator(
                "th:has-text('Actividad económica principal')"
            ).locator("xpath=following::td[@class='border-top-tabla-datos'][1]").inner_text().strip()
        except Exception:
            pass

        try:
            fila_fechas = page.locator("th:has-text('Fecha inicio actividades')").locator(
                "xpath=ancestor::table[1]//tbody/tr[1]/td"
            )
            celdas = fila_fechas.all_inner_texts()
            if len(celdas) >= 4:
                datos["fecha_inicio_actividades"] = celdas[0].strip()
                datos["fecha_actualizacion"] = celdas[1].strip()
                datos["fecha_cese_actividades"] = celdas[2].strip()
                datos["fecha_reinicio_actividades"] = celdas[3].strip()
        except Exception:
            pass

        try:
            filas_establecimientos = page.locator(
                "sri-listar-establecimientos table tbody tr"
            ).all()
            for fila in filas_establecimientos:
                celdas_valor = fila.locator("span.ui-cell-data").all_inner_texts()
                if len(celdas_valor) >= 4:
                    datos["establecimientos"].append({
                        "numero": celdas_valor[0].strip(),
                        "nombre_comercial": celdas_valor[1].strip(),
                        "ubicacion": celdas_valor[2].strip(),
                        "estado": celdas_valor[3].strip(),
                    })
        except Exception:
            pass

    def buscar_cliente(self, page: Page, cliente: Cliente) -> dict:
        return self.consultar_ruc(page, cliente)
    
        return datos