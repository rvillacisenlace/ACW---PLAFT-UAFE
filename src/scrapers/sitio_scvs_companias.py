"""
Búsqueda de Compañías (SCVS). Flujo confirmado con 5 pasos:
1. Escribir RUC en autocompletado (requiere "type()" real, no "fill()",
   para disparar el evento de sugerencias).
2. Seleccionar la empresa de la lista desplegada.
3. Resolver el PRIMER captcha Altcha (habilita el botón "Consultar").
4. Clic en "Consultar" -> aparece un MENÚ de opciones (no la info directa).
5. Clic en "Consulta de cumplimiento" -> dispara un SEGUNDO Altcha (en
   un popup) -> recién ahí aparecen los datos de la empresa.
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, CompaniaSCVS

ID_CAMPO_BUSQUEDA = "#frmBusquedaCompanias\\:parametroBusqueda_input"
ID_PANEL_SUGERENCIAS = "#frmBusquedaCompanias\\:parametroBusqueda_panel li.ui-autocomplete-item"
ID_BOTON_CONSULTAR = "#frmBusquedaCompanias\\:btnConsultarCompania"


class ScraperSCVSCompanias(BaseScraper):
    nombre_sitio = "SCVS - Búsqueda de Compañías"

    def tiene_captcha(self, page: Page) -> bool:
        checkbox = page.locator("div.altcha-checkbox input[type='checkbox']")
        return checkbox.count() > 0

    def buscar_cliente(self, page: Page, cliente: Cliente) -> CompaniaSCVS:
        page.goto(self.url_base)
        self.delay_humano(1.5, 2.5)

        # Seleccionar explícitamente el radio "R.U.C." - no asumir que
        # ya viene seleccionado (confirmado que el atributo HTML no
        # siempre coincide con el estado visual real).
        page.click("label[for='frmBusquedaCompanias\\:tipoBusqueda\\:1']")
        self.delay_humano(0.5, 1.0)

        seleccionado = self._buscar_y_seleccionar_empresa(page, cliente.identificacion)
        if not seleccionado:
            return CompaniaSCVS(registrado=False, mensaje="RUC no registrado en SCVS")

        # Primer Altcha: habilita el botón "Consultar"
        self._resolver_altcha(page, "div.altcha-checkbox input[type='checkbox']")

        boton_consultar = page.locator(ID_BOTON_CONSULTAR)
        for _ in range(20):
            if boton_consultar.is_enabled():
                break
            page.wait_for_timeout(500)
        boton_consultar.click()
        self.delay_humano(2.0, 3.0)

        # Aparece el menú de opciones - clic en "Consulta de cumplimiento"
        enlace_cumplimiento = page.locator("#frmMenu\\:menuCumplimientoObligaciones")
        enlace_cumplimiento.wait_for(state="visible", timeout=10000)
        enlace_cumplimiento.click(force=True)
        self.delay_humano(1.5, 2.5)

        # Segundo Altcha, dentro del popup de captcha (frmCaptcha)
        self._resolver_altcha(page, "#frmCaptcha input[type='checkbox'].altcha-checkbox, #frmCaptcha div.altcha-checkbox input[type='checkbox']")
        self.delay_humano(1.0, 1.5)

        # Clic en "Continuar" - se habilita tras validar el Altcha del
        # popup, y es indispensable (no basta con resolver el captcha,
        # hay que confirmar explícitamente para ver el contenido).
        boton_continuar = page.locator("#frmCaptcha\\:btnPresentarContenido")
        boton_continuar.wait_for(state="visible", timeout=10000)
        for _ in range(20):
            if boton_continuar.is_enabled():
                break
            page.wait_for_timeout(500)
        boton_continuar.click(force=True)
        self.delay_humano(2.0, 3.0)

        from src.documentos.evidencia import capturar_evidencia
        capturar_evidencia(page, cliente.identificacion, sitio="sitio_scvs_companias_resultado", carpeta_sitio="scvs")

        resultado = self._extraer_datos_compania(page)

        try:
            pdf_bytes = self.descargar_certificado(page, cliente)
            from src.documentos.almacenamiento import guardar_pdf_local
            resultado.ruta_pdf = guardar_pdf_local(pdf_bytes, cliente.identificacion, "certificado_cumplimiento_scvs", carpeta_sitio="scvs")
        except Exception as e:
            print(f"[{cliente.identificacion}] Falló descarga del certificado SCVS: {e}")

        return resultado

    def _buscar_y_seleccionar_empresa(self, page: Page, ruc: str) -> bool:
        campo = page.locator(ID_CAMPO_BUSQUEDA)
        campo.wait_for(state="visible", timeout=8000)
        campo.click()
        campo.type(ruc, delay=100)
        self.delay_humano(1.5, 2.5)

        panel_sugerencias = page.locator(ID_PANEL_SUGERENCIAS)
        try:
            panel_sugerencias.first.wait_for(state="visible", timeout=8000)
        except Exception:
            return False

        panel_sugerencias.first.click()
        self.delay_humano(0.5, 1.0)
        return True

    def _resolver_altcha(self, page: Page, selector_checkbox: str) -> None:
        checkbox = page.locator(selector_checkbox)
        checkbox.wait_for(state="visible", timeout=10000)
        checkbox.click(force=True)

        for _ in range(20):
            if checkbox.is_checked():
                break
            page.wait_for_timeout(500)

    def _extraer_datos_compania(self, page: Page) -> CompaniaSCVS:
        resultado = CompaniaSCVS()
        try:
            resultado.ruc = self._valor_por_etiqueta(page, "R.U.C.:")
            resultado.expediente = self._valor_por_etiqueta(page, "Expediente:")
            resultado.representante_legal_scvs_referencia = self._valor_por_etiqueta(page, "Representante legal:")
            resultado.capital_social = self._valor_por_etiqueta(page, "Capital social:")
            resultado.situacion_legal = self._valor_por_etiqueta(page, "Situación legal:")
            resultado.cumplimiento_obligaciones = self._valor_por_etiqueta(page, "Cumplimiento de obligaciones y existencia legal:")
        except Exception as e:
            print(f"    [advertencia] falló extracción de algún campo de SCVS: {e}")
        return resultado

    def _valor_por_etiqueta(self, page: Page, texto_etiqueta: str) -> str:
        return page.locator(
            f"label:text-is('{texto_etiqueta}')"
        ).locator("xpath=ancestor::td[1]/following-sibling::td[1]/label").inner_text().strip()

    def descargar_certificado(self, page: Page, cliente: Cliente) -> bytes:
        """
        Genera y descarga el certificado de cumplimiento en PDF. Reutiliza
        el mismo patrón de captcha (Altcha en popup + botón Continuar)
        que "Consulta de cumplimiento". El PDF se muestra en un <object>
        con URL de archivo real en el servidor (no blob) - se re-descarga
        directamente por HTTP.
        """
        boton_generar = page.locator("button[title='Haga clic aquí para generar el certificado']")
        boton_generar.wait_for(state="visible", timeout=25000)
        boton_generar.click(force=True)

        # El diálogo muestra "Procesando..." antes de renderizar el
        # captcha real - se espera activamente (hasta 15s) en vez de un
        # delay fijo, que resultó insuficiente.
        checkbox_selector = "#frmCaptcha input[type='checkbox'].altcha-checkbox, #frmCaptcha div.altcha-checkbox input[type='checkbox']"
        try:
            page.wait_for_selector(checkbox_selector, state="visible", timeout=30000)
        except Exception:
            raise ScraperError(
                f"[{self.nombre_sitio}] El captcha del certificado no terminó de cargar tras 15s.",
                resultado=ResultadoConsulta.TIMEOUT,
            )

        self._resolver_altcha(page, checkbox_selector)
        self.delay_humano(1.0, 1.5)

        boton_continuar = page.locator("#frmCaptcha\\:btnPresentarContenido")
        boton_continuar.wait_for(state="visible", timeout=10000)
        for _ in range(20):
            if boton_continuar.is_enabled():
                break
            page.wait_for_timeout(500)
        boton_continuar.click(force=True)

        objetos_pdf = page.locator("object[type='application/pdf']")
        objetos_pdf.last.wait_for(state="visible", timeout=25000)

        url_relativa = objetos_pdf.last.get_attribute("data")
        url_pdf = f"https://appscvsgen.supercias.gob.ec{url_relativa}"

        respuesta = page.context.request.get(url_pdf)
        if not respuesta.ok:
            raise ScraperError(
                f"[{self.nombre_sitio}] Falló la descarga del certificado (status {respuesta.status}) desde {url_pdf}",
                resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
            )

        return respuesta.body()