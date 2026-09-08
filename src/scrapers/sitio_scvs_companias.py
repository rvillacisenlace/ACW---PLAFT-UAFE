"""
Búsqueda de Compañías (SCVS). Flujo confirmado con 5 pasos:
1. Escribir RUC en autocompletado (requiere "type()" real, no "fill()",
   para disparar el evento de sugerencias).
2. Seleccionar la empresa de la lista desplegada.
3. Resolver el PRIMER captcha Altcha (habilita el botón "Consultar").
4. Clic en "Consultar" -> aparece un MENÚ de opciones (no la info directa).
5. Clic en la opción deseada del menú -> dispara un SEGUNDO Altcha (en
   un popup) -> recién ahí aparecen los datos.

Dos opciones del menú soportadas, cada una repite el flujo completo
desde cero (no se comparte sesión/menú entre ambas - no confirmado si
el menú persiste tras ver un reporte, así que cada consulta es
independiente por seguridad):
- "Consulta de cumplimiento" -> datos generales de la compañía.
- "Beneficiario final de accionistas/socios" -> tabla jerárquica de
  beneficiarios finales (agregado 2026-09-03).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, CompaniaSCVS, BeneficiarioFinal

ID_CAMPO_BUSQUEDA = "#frmBusquedaCompanias\\:parametroBusqueda_input"
ID_PANEL_SUGERENCIAS = "#frmBusquedaCompanias\\:parametroBusqueda_panel li.ui-autocomplete-item"
ID_BOTON_CONSULTAR = "#frmBusquedaCompanias\\:btnConsultarCompania"
MAXIMO_BENEFICIARIOS_FINALES = 4


class ScraperSCVSCompanias(BaseScraper):
    nombre_sitio = "SCVS - Búsqueda de Compañías"

    def tiene_captcha(self, page: Page) -> bool:
        checkbox = page.locator("div.altcha-checkbox input[type='checkbox']")
        return checkbox.count() > 0

    def _buscar_hasta_menu(self, page: Page, cliente: Cliente) -> bool:
        """
        Pasos 1-4 compartidos por ambas consultas (cumplimiento y
        beneficiarios finales): buscar la empresa, resolver el primer
        Altcha, y hacer clic en "Consultar" para llegar al menú de
        opciones. Devuelve False si el RUC no está registrado (sin
        lanzar excepción - es un resultado válido, no un error).
        """
        self.ejecutar_con_reintentos(page.goto, self.url_base)
        self.delay_humano(1.5, 2.5)

        campo_busqueda = page.locator(ID_CAMPO_BUSQUEDA)
        page.click("label[for='frmBusquedaCompanias\\:tipoBusqueda\\:1']")
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        for _ in range(20):
            if page.locator(ID_CAMPO_BUSQUEDA).get_attribute("maxlength") != "6":
                break
            page.wait_for_timeout(300)
        self.delay_humano(0.5, 1.0)
        for _ in range(20):
            if campo_busqueda.get_attribute("maxlength") != "6":
                break
            page.wait_for_timeout(300)
        self.delay_humano(0.5, 1.0)

        seleccionado = self._buscar_y_seleccionar_empresa(page, cliente.identificacion)
        if not seleccionado:
            return False

        self._resolver_altcha(page, "div.altcha-checkbox input[type='checkbox']")

        boton_consultar = page.locator(ID_BOTON_CONSULTAR)
        for _ in range(20):
            if boton_consultar.is_enabled():
                break
            page.wait_for_timeout(500)
        boton_consultar.click()
        self.delay_humano(2.0, 3.0)
        return True

    def buscar_cliente(self, page: Page, cliente: Cliente) -> CompaniaSCVS:
        encontrada = self._buscar_hasta_menu(page, cliente)
        if not encontrada:
            return CompaniaSCVS(registrado=False, mensaje="RUC no registrado en SCVS")

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

    def consultar_beneficiarios_finales(self, page: Page, cliente: Cliente) -> list[BeneficiarioFinal]:
        """
        Flujo independiente (repite la búsqueda desde cero) para la
        opción "Beneficiario final de accionistas/socios" del menú.

        La tabla resultante es JERÁRQUICA (numeración "1.", "4.2.",
        "4.5.1.", etc. - cadenas de accionistas de accionistas). SOLO
        las filas de nivel superior (numeración sin punto intermedio:
        "1.", "2.", "3.", ...) tienen la columna "Valor" llena - las
        demás son detalle de la cadena societaria sin valor propio, y
        se descartan. Confirmado con evidencia real: el criterio "Valor
        no vacío" identifica exactamente esas filas, sin depender de
        parsear colores CSS (que podrían variar).

        Se ordenan por Valor descendente (confirmado por el usuario
        como el criterio correcto - mismo patron que Empresas
        Relacionadas de SCVS Personas) y se toman los primeros 4.
        """
        encontrada = self._buscar_hasta_menu(page, cliente)
        if not encontrada:
            return []

        enlace_beneficiarios = page.locator("#frmMenu\\:menuBeneficiariosFinales")
        enlace_beneficiarios.wait_for(state="visible", timeout=10000)
        enlace_beneficiarios.click(force=True)
        self.delay_humano(1.5, 2.5)

        self._resolver_altcha(page, "#frmCaptcha input[type='checkbox'].altcha-checkbox, #frmCaptcha div.altcha-checkbox input[type='checkbox']")
        self.delay_humano(1.0, 1.5)

        boton_continuar = page.locator("#frmCaptcha\\:btnPresentarContenido")
        boton_continuar.wait_for(state="visible", timeout=10000)
        for _ in range(20):
            if boton_continuar.is_enabled():
                break
            page.wait_for_timeout(500)
        boton_continuar.click(force=True)
        self.delay_humano(2.0, 3.0)

        from src.documentos.evidencia import capturar_evidencia
        capturar_evidencia(page, cliente.identificacion, sitio="sitio_scvs_beneficiarios_finales_resultado", carpeta_sitio="scvs")

        return self._extraer_beneficiarios_finales(page)

    def _extraer_beneficiarios_finales(self, page: Page) -> list[BeneficiarioFinal]:
        tabla = page.locator("#frmInformacionCompanias\\:tblBeneficiarioFinales_data")
        if tabla.count() == 0:
            return []

        filas = tabla.locator("tr").all()
        beneficiarios = []
        for fila in filas:
            celdas = fila.locator("td").all_inner_texts()
            celdas = [c.strip() for c in celdas]
            if len(celdas) < 7:
                continue
            valor_texto = celdas[5].strip()
            if not valor_texto:
                continue  # fila de detalle intermedio de la cadena societaria - no es un beneficiario de nivel superior
            beneficiarios.append(BeneficiarioFinal(
                numero=celdas[0], identificacion=celdas[1], nombre=celdas[2],
                nacionalidad=celdas[3], tipo_inversion=celdas[4],
                valor=valor_texto, restriccion=celdas[6],
            ))

        def _valor_numerico(b: BeneficiarioFinal) -> float:
            try:
                # Formato ecuatoriano: "." separador de miles, ","
                # separador decimal - ej. "1.786.398,0000"
                limpio = b.valor.replace(".", "").replace(",", ".")
                return float(limpio)
            except (ValueError, TypeError):
                return 0.0

        beneficiarios.sort(key=_valor_numerico, reverse=True)
        return beneficiarios[:MAXIMO_BENEFICIARIOS_FINALES]

    def _buscar_y_seleccionar_empresa(self, page: Page, ruc: str) -> bool:
        campo = page.locator(ID_CAMPO_BUSQUEDA)
        campo.wait_for(state="visible", timeout=8000)
        campo.click()
        campo.fill("")
        campo.type(ruc, delay=150)
        self.verificar_campo_lleno(page, ID_CAMPO_BUSQUEDA, ruc)

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
        boton_generar.click()
        checkbox_selector = "#frmCaptcha input[type='checkbox'].altcha-checkbox, #frmCaptcha div.altcha-checkbox input[type='checkbox']"
        try:
            page.wait_for_selector(checkbox_selector, state="visible", timeout=30000)
        except Exception:
            raise ScraperError(
                f"[{self.nombre_sitio}] El captcha del certificado no terminó de cargar tras 30s.",
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