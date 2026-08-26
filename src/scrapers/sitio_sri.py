import random
from playwright.sync_api import Page
from playwright_stealth import Stealth

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, TipoPersona

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
        Intenta primero la búsqueda directa por RUC. Si aparece el
        bloqueo de reputación de reCAPTCHA v3 ("Puntaje bajo"), reintenta
        con búsqueda por razón social/nombre completo - confirmado
        empíricamente que esa vía no dispara el mismo bloqueo con la
        misma frecuencia, aunque lleva a la misma vista de datos.
        """
        Stealth().apply_stealth_sync(page)
        page.goto(self.url_base)
        self.delay_humano(4.0, 6.0)

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
        print(f"[{self.nombre_sitio}] Consultando con RUC: {ruc_a_consultar}")
        page.fill(ID_CAMPO_RUC, ruc_a_consultar)
        self.delay_humano(4.0, 6.0)

        page.mouse.wheel(0, random.randint(50, 150))
        page.wait_for_timeout(random.randint(500, 1000))

        botones_consultar = page.locator("button:has-text('Consultar')")
        botones_consultar.first.click()
        self.delay_humano(5.0, 8.0)

        if self.tiene_captcha(page):
            print(f"[{self.nombre_sitio}] Bloqueo detectado por RUC - reintentando por razón social/nombre...")

            nombre_o_razon_social = (
                cliente.nombres_completos if cliente.tipo_persona == TipoPersona.NATURAL
                else cliente.razon_social
            )

            page.goto(self.url_base)
            self.delay_humano(6.0, 9.0)

            self._buscar_por_razon_social(page, nombre_o_razon_social)

            if self.tiene_captcha(page):
                raise ScraperError(
                    f"[{self.nombre_sitio}] Bloqueo persiste incluso con búsqueda por razón social.",
                    resultado=ResultadoConsulta.ERROR_CAPTCHA,
                )

        boton_mostrar_establecimientos = page.locator("button:has-text('Mostrar establecimientos')")
        boton_mostrar_establecimientos.wait_for(state="visible", timeout=15000)
        boton_mostrar_establecimientos.click()
        self.delay_humano(5.0, 8.0)

        from src.documentos.evidencia import capturar_evidencia
        capturar_evidencia(page, cliente.identificacion_evidencia or cliente.identificacion, sitio="sitio_sri_ruc_resultado", carpeta_sitio="sri", subcarpeta=cliente.subcarpeta_evidencia)

        return self._extraer_datos_contribuyente(page)

    def _buscar_por_razon_social(self, page: Page, nombre_o_razon_social: str) -> None:
        page.click("button[aria-label='Seleccionar búsqueda por razón social']")
        self.delay_humano(4.0, 6.0)

        page.fill("#busquedaRazonSocialId", nombre_o_razon_social)
        self.delay_humano(4.0, 6.0)

        page.click("button:has-text('Consultar')")
        self.delay_humano(4.0, 6.0)

    def _extraer_datos_contribuyente(self, page: Page) -> dict:
        datos = {
            "razon_social": "",
            "estado_contribuyente": "",
            "actividad_economica": "",
            "fecha_inicio_actividades": "",
            "fecha_actualizacion": "",
            "fecha_cese_actividades": "",
            "fecha_reinicio_actividades": "",
            "direccion_matriz": "",
            "representante_legal_nombre": "",
            "representante_legal_identificacion": "",
            "contribuyente_fantasma": "",
            "contribuyente_transacciones_inexistentes": "",
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
            # Solo se necesita la dirección del establecimiento MATRIZ
            filas_establecimientos = page.locator(
                "sri-listar-establecimientos table tbody tr"
            ).all()
            for fila in filas_establecimientos:
                celdas_valor = fila.locator("span.ui-cell-data").all_inner_texts()
                if len(celdas_valor) >= 4 and celdas_valor[0].strip() == "001":
                    datos["direccion_matriz"] = celdas_valor[2].strip()
                    break
        except Exception:
            pass

        try:
            datos["representante_legal_nombre"] = page.locator(
                "div.sri-bold:has-text('Nombre/Razón Social:')"
            ).locator("xpath=following-sibling::div[1]").inner_text().strip()
        except Exception:
            pass

        try:
            datos["representante_legal_identificacion"] = page.locator(
                "div.sri-bold:has-text('Identificación:')"
            ).locator("xpath=following-sibling::div[1]").inner_text().strip()
        except Exception:
            pass

        try:
            datos["contribuyente_fantasma"] = page.locator(
                "div.sri-bold:has-text('Contribuyente fantasma')"
            ).locator("xpath=following::span[1]").inner_text().strip()
        except Exception:
            pass

        try:
            datos["contribuyente_transacciones_inexistentes"] = page.locator(
                "div.sri-bold:has-text('Contribuyente con transacciones inexistentes')"
            ).locator("xpath=following::span[1]").inner_text().strip()
        except Exception:
            pass

        return datos

    def buscar_cliente(self, page: Page, cliente: Cliente) -> dict:
        return self.consultar_ruc(page, cliente)