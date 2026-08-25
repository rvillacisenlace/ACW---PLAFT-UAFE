"""
Portal de Sentenciados (AngularJS). Sin columna "Observaciones" en la
matriz para este sitio - NO requiere resumen de IA, solo extracción de
datos de la tabla + PDF descargado como evidencia archivada (mismo
patrón de captura de PDF en pestaña nueva que Función Judicial).
"""
from datetime import datetime
from playwright.sync_api import Page
from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ResultadoConsulta, Sentenciado, TipoPersona
from src.documentos.almacenamiento import guardar_pdf_local
from src.documentos.evidencia import capturar_evidencia

UMBRAL_SENTENCIADOS = 3


class ScraperSentenciados(BaseScraper):
    nombre_sitio = "Sentenciados"

    def tiene_captcha(self, page: Page) -> bool:
        # TODO: no se ha confirmado si este portal presenta captcha.
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> tuple[list[Sentenciado], int]:
        """
        Busca por cédula, RUC derivado, y nombre completo (o razón
        social/RUC para Jurídica) - mismo criterio de validación triple
        que Función Judicial, para no perder sentencias indexadas bajo
        una sola de esas formas.
        """
        usar_derivacion = (
            cliente.tipo_persona == TipoPersona.NATURAL
            or getattr(cliente, "es_juridica_con_ruc_persona_natural", False)
        )

        # Se recolectan TODOS los resultados sin descartar nada todavia -
        # la deduplicacion por numero_proceso se hace despues, comparando
        # fechas explicitamente (no "el que se proceso de ultimo", que
        # dependia del orden de busqueda por casualidad).
        resultados_crudos = []

        if usar_derivacion:
            cedula_real = (
                cliente.identificacion if cliente.tipo_persona == TipoPersona.NATURAL
                else cliente.identificacion[:10]
            )
            ruc_real = (
                f"{cliente.identificacion}001" if cliente.tipo_persona == TipoPersona.NATURAL
                else cliente.identificacion
            )
            for identificacion_buscar in (cedula_real, ruc_real):
                resultados_crudos.extend(self._buscar_una_vez(page, cliente, "cedula", identificacion_buscar))
            resultados_crudos.extend(self._buscar_una_vez(page, cliente, "nombre", cliente.nombres_completos))
        else:
            resultados_crudos.extend(self._buscar_una_vez(page, cliente, "nombre", cliente.razon_social))
            resultados_crudos.extend(self._buscar_una_vez(page, cliente, "cedula", cliente.identificacion))

        def _parsear_fecha(s: Sentenciado) -> datetime:
            try:
                return datetime.strptime(s.fecha_resolucion, "%d/%m/%Y")
            except ValueError:
                return datetime.min

        # Consolidar por numero_proceso quedandonos con el mas reciente
        # de cada grupo (confirmado con evidencia real: un mismo numero
        # de proceso puede tener 2 registros con dependencia/fecha
        # distintas - se toma el de fecha mas actual como referencia).
        sentenciados_por_numero = {}
        for s in resultados_crudos:
            existente = sentenciados_por_numero.get(s.numero_proceso)
            if existente is None or _parsear_fecha(s) > _parsear_fecha(existente):
                sentenciados_por_numero[s.numero_proceso] = s

        todos_sentenciados = list(sentenciados_por_numero.values())
        total_encontrado = len(todos_sentenciados)

        def _parsear_fecha(s: Sentenciado) -> datetime:
            try:
                return datetime.strptime(s.fecha_resolucion, "%d/%m/%Y")
            except ValueError:
                return datetime.min

        todos_sentenciados.sort(key=_parsear_fecha, reverse=True)
        top3 = todos_sentenciados[:UMBRAL_SENTENCIADOS]

        if top3:
            try:
                pdf_bytes = self._descargar_pdf_sentencia(page)
                ruta_guardada = guardar_pdf_local(pdf_bytes, cliente.identificacion, "reporte_sentenciados", carpeta_sitio="sentenciados")
                for sentenciado in top3:
                    sentenciado.ruta_pdf = ruta_guardada
            except Exception as e:
                print(f"[{cliente.identificacion}] Falló descarga del reporte de sentenciados: {type(e).__name__}: {e}")

        return top3, total_encontrado

    def _buscar_una_vez(self, page: Page, cliente: Cliente, tipo_radio: str, valor_busqueda: str) -> list[Sentenciado]:
        """
        tipo_radio: "cedula" o "nombre" - determina cuál radio button
        seleccionar antes de escribir el valor de búsqueda.
        """
        page.goto(self.url_base)

        try:
            page.wait_for_selector("#radio_1", state="visible", timeout=20000)
        except Exception:
            print("    [advertencia] el radio de búsqueda no apareció a tiempo, recargando página...")
            page.reload()
            page.wait_for_selector("#radio_1", state="visible", timeout=20000)

        self.delay_humano(1.0, 1.5)

        if tipo_radio == "cedula":
            page.click("#radio_1")
            self.delay_humano(0.5, 1.0)
            page.fill("#input_3", valor_busqueda)
        else:
            # "Nombre" aparece marcado como seleccionado por defecto en
            # el atributo HTML, pero el campo #input_2 permanece en
            # readonly hasta que se dispara explícitamente el evento
            # ng-change de Angular con un clic real - confirmado con
            # error real (TimeoutError al intentar fill en campo
            # readonly). El clic es necesario aunque el radio "ya esté
            # marcado" visualmente.
            page.click("#radio_0")
            self.delay_humano(0.5, 1.0)
            page.fill("#input_2", valor_busqueda.upper())

        self.delay_humano(0.5, 1.0)

        # Esperar explícitamente que el loader desaparezca ANTES de
        # intentar el clic en Buscar - confirmado que puede seguir
        # bloqueando la pantalla incluso cuando el radio button ya se
        # reporta como "visible" (loader por encima, z-index).
        try:
            page.wait_for_selector("#loaderDiv", state="hidden", timeout=15000)
        except Exception:
            pass

        page.click("button:has-text('Buscar')", timeout=15000)
        try:
            page.wait_for_selector("#loaderDiv", state="hidden", timeout=15000)
        except Exception:
            pass
        self.delay_humano(2.0, 3.0)

        capturar_evidencia(page, cliente.identificacion, sitio=f"sitio_sentenciados_{tipo_radio}", carpeta_sitio="sentenciados")

        filas = page.locator("tbody tr[ng-repeat]").all()
        # TODO: este portal tiene paginación (no confirmada aún con un
        # caso real que la dispare) - por ahora solo se extraen los
        # resultados de la primera página. Si aparece un cliente con
        # muchos sentenciados, revisar si hace falta paginar como en
        # Función Judicial.
        resultados = []
        for fila in filas:
            celdas = fila.locator("td").all_inner_texts()
            if len(celdas) < 8:
                continue
            numero_proceso = celdas[1].strip()
            if not numero_proceso:
                continue  # fila vacia/fantasma del portal (Angular ng-repeat) - no es un caso real
            resultados.append(Sentenciado(
                numero_proceso=numero_proceso,
                provincia=celdas[2].strip(),
                dependencia_jurisdiccional=celdas[3].strip(),
                fecha_resolucion=celdas[4].strip(),
                materia=celdas[5].strip(),
                tipo_accion=celdas[6].strip(),
                infraccion=celdas[7].strip(),
            ))
        return resultados

    def _descargar_pdf_sentencia(self, page: Page) -> bytes:
        """
        Clic en el botón "Visualizar" (ng-click="imprimirReporte()") -
        genera/abre el PDF del reporte. Distinto del botón "Ver" de cada
        fila, que solo abre el detalle en pantalla sin generar documento.
        """
        boton_visualizar = page.locator("button:has-text('Visualizar')")

        resultado_captura = {"tipo": None, "obj": None}

        def _al_crear_pagina_nueva(nueva_pagina):
            def _en_respuesta(response):
                if resultado_captura["obj"] is None:
                    try:
                        if "pdf" in response.headers.get("content-type", "").lower():
                            resultado_captura["tipo"] = "response"
                            resultado_captura["obj"] = response
                    except Exception:
                        pass

            def _en_descarga(download):
                if resultado_captura["obj"] is None:
                    resultado_captura["tipo"] = "download"
                    resultado_captura["obj"] = download

            nueva_pagina.on("response", _en_respuesta)
            nueva_pagina.on("download", _en_descarga)

        page.context.on("page", _al_crear_pagina_nueva)
        pestana_pdf = None
        try:
            with page.context.expect_page() as info_pestana_nueva:
                boton_visualizar.click()
            pestana_pdf = info_pestana_nueva.value

            for _ in range(20):
                if resultado_captura["obj"] is not None:
                    break
                page.wait_for_timeout(500)

            contenido_pdf = None
            if resultado_captura["obj"] is not None:
                if resultado_captura["tipo"] == "response":
                    contenido_pdf = resultado_captura["obj"].body()
                else:
                    with open(resultado_captura["obj"].path(), "rb") as f:
                        contenido_pdf = f.read()

            if pestana_pdf and not pestana_pdf.is_closed():
                pestana_pdf.close()

            if contenido_pdf is None:
                raise ScraperError(
                    f"[{self.nombre_sitio}] Sin PDF capturable al hacer clic en Visualizar.",
                    resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
                )

            return contenido_pdf
        finally:
            page.context.remove_listener("page", _al_crear_pagina_nueva)