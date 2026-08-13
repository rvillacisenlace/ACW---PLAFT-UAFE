"""
Scraper del Sitio 1 (Función Judicial - eSATJE).
Para personas Naturales: validación triple (cédula + RUC derivado + nombre
completo) para mayor robustez. El RUC derivado (cédula + "001") es una
convención real de Ecuador para personas naturales con negocio propio -
NO se aplica a personas Jurídicas (riesgo de derivar una cédula de un
tercero no relacionado al restar "001" de un RUC de empresa).
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, ProcesoJudicial, ResultadoConsulta, TipoPersona
from src.procesamiento.normalizacion import normalizar_texto_busqueda
from src.documentos.evidencia import capturar_evidencia
from src.documentos.almacenamiento import guardar_pdf_local
from src.procesamiento.resumen_ia import extraer_texto_pdf, generar_resumen
from config.settings import cargar_infra_config

ID_CAMPO_CEDULA = "#form1\\:txtDemandadoCedula"
ID_CAMPO_APELLIDO = "#form1\\:txtDemandadoApellido"
ID_BOTON_BUSCAR = "#form1\\:butBuscarJuicios"
ID_TABLA_RESULTADOS = "#form1\\:dataTableJuicios2"
ID_PAGINADOR_SIGUIENTE = "#form1\\:dataTableJuicios2_paginator_bottom .ui-paginator-next"


class ScraperFuncionJudicial(BaseScraper):
    nombre_sitio = "Función Judicial"

    def tiene_captcha(self, page: Page) -> bool:
        iframe_challenge = page.locator("iframe[title*='recaptcha challenge']")
        if iframe_challenge.count() > 0 and iframe_challenge.first.is_visible():
            return True

        iframe_checkbox = page.locator("iframe[title*='reCAPTCHA']")
        if iframe_checkbox.count() > 0 and iframe_checkbox.first.is_visible():
            return True

        return False

    def _resolver_captcha_manual(self, page: Page, tiempo_espera_segundos: int = 120) -> bool:
        from config.settings import cargar_infra_config as _cargar_infra
        from src.captcha.resolver import resolver_con_2captcha, CaptchaResolverError

        infra = _cargar_infra()

        if infra.captcha_api_key:
            print("Captcha detectado - intentando resolver automáticamente con 2Captcha...")
            try:
                resolver_con_2captcha(page, infra.captcha_api_key, tiempo_espera_segundos)
                print("2Captcha devolvió un token, verificando si el portal lo aceptó...")
                page.wait_for_timeout(2000)
                if not self.tiene_captcha(page):
                    print("Captcha resuelto automáticamente vía 2Captcha.\n")
                    return True
                print("2Captcha resolvió el desafío pero el portal sigue mostrando el captcha - cayendo a resolución manual...\n")
            except CaptchaResolverError as e:
                print(f"2Captcha falló: {e}\n   Cayendo a resolución manual...\n")
            except Exception as e:
                print(f"Error inesperado en 2Captcha ({type(e).__name__}: {e})\n   Cayendo a resolución manual...\n")

        print(f"\n{'='*60}")
        print("CAPTCHA DETECTADO - Se requiere intervención manual")
        print(f"Resuelve el captcha en la ventana del navegador ahora.")
        print(f"Tienes {tiempo_espera_segundos} segundos antes de que se registre como error.")
        print(f"{'='*60}\n")

        intervalos = tiempo_espera_segundos // 3
        for _ in range(intervalos):
            page.wait_for_timeout(3000)
            if not self.tiene_captcha(page):
                print("Captcha resuelto - continuando automáticamente.\n")
                return True

        print("Tiempo de espera agotado sin resolución - se registra como error.\n")
        return False

    def buscar_cliente(self, page: Page, cliente: Cliente) -> tuple[list[ProcesoJudicial], dict]:
        procesos_encontrados = {}
        procedencia = {}

        def _registrar(procesos: list[ProcesoJudicial], tipo: str):
            for proceso in procesos:
                procesos_encontrados[proceso.numero_proceso] = proceso
                procedencia.setdefault(proceso.numero_proceso, set()).add(tipo)

        usar_derivacion = (
            cliente.tipo_persona == TipoPersona.NATURAL
            or cliente.es_juridica_con_ruc_persona_natural
        )

        if usar_derivacion:
            # Cédula real: si es Natural, es la identificación tal cual.
            # Si es "Jurídica con RUC de persona natural", se derivan los
            # primeros 10 dígitos del RUC como cédula real.
            cedula_real = (
                cliente.identificacion if cliente.tipo_persona == TipoPersona.NATURAL
                else cliente.identificacion[:10]
            )
            ruc_real = (
                f"{cliente.identificacion}001" if cliente.tipo_persona == TipoPersona.NATURAL
                else cliente.identificacion
            )
            nombre_para_buscar = cliente.nombres_completos

            procesos_cedula = self._buscar_con_paginacion_confiable(
                page, cliente, ID_CAMPO_CEDULA, cedula_real, tipo_busqueda="cedula"
            )
            _registrar(procesos_cedula, "cedula")

            procesos_ruc = self._buscar_con_paginacion_confiable(
                page, cliente, ID_CAMPO_CEDULA, ruc_real, tipo_busqueda="ruc_derivado"
            )
            _registrar(procesos_ruc, "ruc_derivado")

            nombre_normalizado = normalizar_texto_busqueda(nombre_para_buscar)
            procesos_nombre = self._buscar_con_paginacion_confiable(
                page, cliente, ID_CAMPO_APELLIDO, nombre_normalizado, tipo_busqueda="nombre"
            )
            _registrar(procesos_nombre, "nombre")

            numeros_nombre = {p.numero_proceso for p in procesos_nombre}
            numeros_cedula_o_ruc = {p.numero_proceso for p in procesos_cedula} | {p.numero_proceso for p in procesos_ruc}
            solo_en_cedula_o_ruc = numeros_cedula_o_ruc - numeros_nombre
            if solo_en_cedula_o_ruc:
                print(
                    f"ADVERTENCIA: {len(solo_en_cedula_o_ruc)} proceso(s) aparecen en cédula/RUC derivado "
                    f"pero NO en la búsqueda por nombre: {solo_en_cedula_o_ruc}."
                )

        else:
            # Jurídica real (con RazonSocial propia): razón social primero, RUC como fallback.
            nombre_normalizado = normalizar_texto_busqueda(cliente.razon_social)

            procesos_por_nombre = self._buscar_con_paginacion_confiable(
                page, cliente, ID_CAMPO_APELLIDO, nombre_normalizado, tipo_busqueda="razonsocial"
            )

            if procesos_por_nombre:
                _registrar(procesos_por_nombre, "razonsocial")
            else:
                print(f"[{cliente.identificacion}] Sin resultados por razón social, probando por RUC...")
                procesos_por_ruc = self._buscar_con_paginacion_confiable(
                    page, cliente, ID_CAMPO_CEDULA, cliente.identificacion, tipo_busqueda="ruc"
                )
                _registrar(procesos_por_ruc, "ruc")

        return list(procesos_encontrados.values()), procedencia

    def buscar_y_procesar_cliente(self, page: Page, cliente: Cliente) -> tuple[list[ProcesoJudicial], int, str]:
        """
        Busca por cédula/RUC derivado/nombre (o razón social/RUC para
        Jurídica) con paginación completa, filtra por materia, limita a
        los 3 procesos más recientes (UMBRAL_VOLUMEN), y para cada uno
        de esos 3 descarga el PDF más reciente disponible y genera un
        resumen de IA (mapeado a la columna "Observaciones" del Excel).

        Devuelve: (procesos_finales, total_relevantes_antes_del_limite,
        tematica_general) - los últimos 2 valores alimentan las columnas
        "No. de Juicios" y "Temática Juicios" de la matriz.
        """
        from src.procesamiento.limite_volumen import aplicar_limite_volumen, separar_por_materia

        todos_los_procesos, procedencia = self.buscar_cliente(page, cliente)
        procesos_relevantes, procesos_excluidos_materia = separar_por_materia(todos_los_procesos)

        total_relevantes = len(procesos_relevantes)
        tematica_general = self._clasificar_tematica_general(procesos_relevantes)

        procesos_finales = aplicar_limite_volumen(procesos_relevantes) + procesos_excluidos_materia

        nombre_cliente = (
            cliente.nombres_completos if cliente.tipo_persona == TipoPersona.NATURAL
            else cliente.razon_social
        )
        for proceso in procesos_finales:
            if proceso.omitido_por_volumen and not proceso.demandado:
                proceso.demandado = f"{nombre_cliente} (inferido de campo de búsqueda, no confirmado en detalle)"

        numeros_calificados = {
            p.numero_proceso for p in procesos_finales
            if not p.omitido_por_volumen and not p.excluido_por_materia
        }

        usar_derivacion = (
            cliente.tipo_persona == TipoPersona.NATURAL
            or cliente.es_juridica_con_ruc_persona_natural
        )

        if usar_derivacion:
            en_nombre = {n for n in numeros_calificados if "nombre" in procedencia.get(n, set())}
            resto = numeros_calificados - en_nombre
            en_cedula = {n for n in resto if "cedula" in procedencia.get(n, set())}
            en_ruc_derivado = resto - en_cedula

            if en_nombre:
                nombre_normalizado = normalizar_texto_busqueda(cliente.nombres_completos)
                page.goto(self.url_base)
                self.delay_humano()
                page.fill(ID_CAMPO_APELLIDO, nombre_normalizado)
                self.delay_humano(0.5, 1.2)
                self._buscar_con_reintento(page)
                if self.tiene_captcha(page):
                    if not self._resolver_captcha_manual(page):
                        raise ScraperError(
                            f"[{self.nombre_sitio}] Captcha detectado en re-búsqueda por nombre.",
                            resultado=ResultadoConsulta.ERROR_CAPTCHA,
                        )
                self._descargar_calificados_de_tabla_actual(page, procesos_finales, en_nombre, cliente)

            if en_cedula:
                cedula_real = (
                    cliente.identificacion if cliente.tipo_persona == TipoPersona.NATURAL
                    else cliente.identificacion[:10]
                )
                page.goto(self.url_base)
                self.delay_humano()
                page.fill(ID_CAMPO_CEDULA, cedula_real)
                self.delay_humano(0.5, 1.2)
                self._buscar_con_reintento(page)
                if self.tiene_captcha(page):
                    if not self._resolver_captcha_manual(page):
                        raise ScraperError(
                            f"[{self.nombre_sitio}] Captcha detectado en re-búsqueda por cédula.",
                            resultado=ResultadoConsulta.ERROR_CAPTCHA,
                        )
                self._descargar_calificados_de_tabla_actual(page, procesos_finales, en_cedula, cliente)

            if en_ruc_derivado:
                ruc_derivado = (
                    f"{cliente.identificacion}001" if cliente.tipo_persona == TipoPersona.NATURAL
                    else cliente.identificacion
                )
                page.goto(self.url_base)
                self.delay_humano()
                page.fill(ID_CAMPO_CEDULA, ruc_derivado)
                self.delay_humano(0.5, 1.2)
                self._buscar_con_reintento(page)
                if self.tiene_captcha(page):
                    if not self._resolver_captcha_manual(page):
                        raise ScraperError(
                            f"[{self.nombre_sitio}] Captcha detectado en re-búsqueda por RUC derivado.",
                            resultado=ResultadoConsulta.ERROR_CAPTCHA,
                        )
                self._descargar_calificados_de_tabla_actual(page, procesos_finales, en_ruc_derivado, cliente)

        else:
            calificados_en_razonsocial = {n for n in numeros_calificados if "razonsocial" in procedencia.get(n, set())}
            calificados_en_ruc = numeros_calificados - calificados_en_razonsocial

            if calificados_en_razonsocial:
                nombre_normalizado = normalizar_texto_busqueda(cliente.razon_social)
                page.goto(self.url_base)
                self.delay_humano()
                page.fill(ID_CAMPO_APELLIDO, nombre_normalizado)
                self.delay_humano(0.5, 1.2)
                self._buscar_con_reintento(page)
                if self.tiene_captcha(page):
                    if not self._resolver_captcha_manual(page):
                        raise ScraperError(
                            f"[{self.nombre_sitio}] Captcha detectado en re-búsqueda por razón social.",
                            resultado=ResultadoConsulta.ERROR_CAPTCHA,
                        )
                self._descargar_calificados_de_tabla_actual(page, procesos_finales, calificados_en_razonsocial, cliente)

            if calificados_en_ruc:
                page.goto(self.url_base)
                self.delay_humano()
                page.fill(ID_CAMPO_CEDULA, cliente.identificacion)
                self.delay_humano(0.5, 1.2)
                self._buscar_con_reintento(page)
                if self.tiene_captcha(page):
                    if not self._resolver_captcha_manual(page):
                        raise ScraperError(
                            f"[{self.nombre_sitio}] Captcha detectado en re-búsqueda por RUC.",
                            resultado=ResultadoConsulta.ERROR_CAPTCHA,
                        )
                self._descargar_calificados_de_tabla_actual(page, procesos_finales, calificados_en_ruc, cliente)

        return procesos_finales, total_relevantes, tematica_general

    def _clasificar_tematica_general(self, procesos: list[ProcesoJudicial]) -> str:
        """
        Determina una categoría general (Civil, Penal, Laboral, etc.)
        para la columna "Temática Juicios", basada en la materia
        predominante entre los procesos relevantes encontrados.
        """
        from src.procesamiento.clasificador import clasificar_categoria

        if not procesos:
            return "Sin procesos relevantes"

        categorias = [clasificar_categoria(p.accion_infraccion_delito) for p in procesos]
        categorias_validas = [c for c in categorias if c]
        if not categorias_validas:
            return "No determinada"

        # La categoría más frecuente entre los procesos relevantes
        from collections import Counter
        return Counter(categorias_validas).most_common(1)[0][0]

    def _buscar_con_reintento(self, page: Page) -> None:
        for _ in range(2):
            with page.expect_response(lambda r: "informacion.jsf" in r.url):
                page.click(ID_BOTON_BUSCAR)
            page.wait_for_timeout(500)

    def _extraer_resultados(self, page: Page, reintentos: int = 2, espera_ms: int = 500) -> list[ProcesoJudicial]:
        if page.locator(ID_TABLA_RESULTADOS).count() == 0:
            return []

        filas_locator = page.locator(f"{ID_TABLA_RESULTADOS} tbody tr")
        for intento in range(reintentos):
            if filas_locator.count() > 0:
                break
            if intento < reintentos - 1:
                page.wait_for_timeout(espera_ms)

        conteo_anterior = -1
        for _ in range(6):
            conteo_actual = filas_locator.count()
            if conteo_actual == conteo_anterior:
                break
            conteo_anterior = conteo_actual
            page.wait_for_timeout(300)

        filas = filas_locator.all()
        procesos = []

        for fila in filas:
            celdas = fila.locator("td").all_inner_texts()
            if len(celdas) < 4:
                continue

            procesos.append(ProcesoJudicial(
                numero_proceso=celdas[2].strip(),
                demandado="",
                lugar="",
                accion_infraccion_delito=celdas[3].strip(),
                fecha_ingreso=celdas[1].strip(),
            ))

        return procesos

    def _extraer_todas_las_paginas(self, page: Page, cliente: Cliente, tipo_busqueda: str) -> tuple[list[ProcesoJudicial], bool]:
        todos_los_procesos = []
        numero_pagina = 1
        completado_correctamente = True

        while True:
            procesos_pagina = self._extraer_resultados(page)
            todos_los_procesos.extend(procesos_pagina)

            capturar_evidencia(
                page, cliente.identificacion,
                sitio=f"sitio1_funcion_judicial_{tipo_busqueda}_pagina{numero_pagina}"
            )

            boton_siguiente = page.locator(ID_PAGINADOR_SIGUIENTE)
            if boton_siguiente.count() == 0:
                break

            clases = boton_siguiente.get_attribute("class") or ""
            if "ui-state-disabled" in clases:
                break

            primeras_filas_actuales = page.locator(f"{ID_TABLA_RESULTADOS} tbody tr")
            numero_proceso_antes = None
            if primeras_filas_actuales.count() > 0:
                celdas_antes = primeras_filas_actuales.first.locator("td").all_inner_texts()
                if len(celdas_antes) >= 3:
                    numero_proceso_antes = celdas_antes[2].strip()

            pagina_avanzo = False
            try:
                with page.expect_response(lambda r: "informacion.jsf" in r.url, timeout=10000):
                    boton_siguiente.click()
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception as e:
                print(f"    [pág.{numero_pagina + 1}] clic/respuesta falló: {e}")

            for _ in range(25):
                filas_actuales = page.locator(f"{ID_TABLA_RESULTADOS} tbody tr")
                if filas_actuales.count() > 0:
                    celdas_ahora = filas_actuales.first.locator("td").all_inner_texts()
                    if len(celdas_ahora) >= 3 and celdas_ahora[2].strip() != numero_proceso_antes:
                        pagina_avanzo = True
                        break
                page.wait_for_timeout(300)

            if not pagina_avanzo:
                print(f"    [advertencia] la página {numero_pagina + 1} no avanzó")
                completado_correctamente = False
                break

            numero_pagina += 1

            if numero_pagina > 10:
                print("    [advertencia] límite de seguridad de 10 páginas alcanzado")
                break

        return todos_los_procesos, completado_correctamente

    def _buscar_con_paginacion_confiable(
        self, page: Page, cliente: Cliente, campo_id: str, valor_busqueda: str,
        tipo_busqueda: str, max_intentos_totales: int = 3
    ) -> list[ProcesoJudicial]:
        procesos = []
        for intento in range(1, max_intentos_totales + 1):
            try:
                page.goto(self.url_base)
                self.delay_humano()
                page.fill(campo_id, valor_busqueda)
                self.delay_humano(0.5, 1.2)
                self._buscar_con_reintento(page)
            except Exception as e:
                print(f"    [{tipo_busqueda}] intento {intento}/{max_intentos_totales} falló al hacer clic en Buscar: {type(e).__name__}")

                if self.tiene_captcha(page):
                    print(f"    Captcha detectado como causa del fallo de clic - intentando resolver...")
                    if not self._resolver_captcha_manual(page):
                        raise ScraperError(
                            f"[{self.nombre_sitio}] Captcha detectado ({tipo_busqueda}) durante el "
                            f"clic en Buscar, sin resolución dentro del tiempo límite.",
                            resultado=ResultadoConsulta.ERROR_CAPTCHA,
                        )
                    print(f"    Captcha resuelto, reintentando búsqueda...")
                else:
                    print(f"    Causa del fallo no identificada como captcha - reintentando desde cero...")

                continue  # intenta de nuevo desde el goto, en vez de propagar el error

            if self.tiene_captcha(page):
                if not self._resolver_captcha_manual(page):
                    raise ScraperError(
                        f"[{self.nombre_sitio}] Captcha detectado tras buscar ({tipo_busqueda}), "
                        f"sin resolución dentro del tiempo límite.",
                        resultado=ResultadoConsulta.ERROR_CAPTCHA,
                    )

            procesos, completado = self._extraer_todas_las_paginas(page, cliente, tipo_busqueda)

            if completado:
                return procesos

            print(f"    [{tipo_busqueda}] intento {intento}/{max_intentos_totales} incompleto, reintentando búsqueda completa desde cero...")

        print(f"    [{tipo_busqueda}] no se logró paginación completa tras {max_intentos_totales} intentos - se usa el resultado parcial del último intento")
        return procesos

    def _descargar_calificados_de_tabla_actual(
        self, page: Page, procesos_finales: list[ProcesoJudicial],
        numeros_a_descargar: set[str], cliente: Cliente
    ) -> None:
        filas = page.locator(f"{ID_TABLA_RESULTADOS} tbody tr").all()

        for indice, fila in enumerate(filas):
            celdas = fila.locator("td").all_inner_texts()
            if len(celdas) < 4:
                continue
            numero_fila = celdas[2].strip()

            if numero_fila not in numeros_a_descargar:
                continue

            proceso = next((p for p in procesos_finales if p.numero_proceso == numero_fila), None)
            if proceso is None:
                continue

            try:
                lista_pdfs, detalle = self.descargar_pdf_proceso(page, indice_fila=indice)
                proceso.lugar = detalle["lugar"]
                proceso.materia = detalle["materia"]
                proceso.demandado = detalle["demandado"]

                rutas_guardadas = []
                for i, pdf_bytes in enumerate(lista_pdfs):
                    sufijo = f"_mov{i+1}" if len(lista_pdfs) > 1 else ""
                    ruta_guardada = guardar_pdf_local(
                        pdf_bytes, cliente.identificacion, f"{proceso.numero_proceso}{sufijo}"
                    )
                    rutas_guardadas.append(ruta_guardada)
                proceso.ruta_pdf = "; ".join(rutas_guardadas)

                try:
                    infra = cargar_infra_config()
                    if not infra.ai_summary_enabled:
                        proceso.resumen_ia = "(resumen no generado: IA desactivada temporalmente en .env)"
                    elif infra.ai_summary_api_key:
                        # Combina el texto de los PDFs descargados (hasta 2,
                        # los movimientos más recientes con documento) antes
                        # de generar un único resumen, que alimenta la
                        # columna "Observaciones" de la matriz.
                        textos = [extraer_texto_pdf(pdf) for pdf in lista_pdfs]
                        texto_combinado = "\n\n--- SIGUIENTE DOCUMENTO ---\n\n".join(textos)
                        proceso.resumen_ia = generar_resumen(texto_combinado, infra.ai_summary_api_key, infra.ai_summary_model)
                    else:
                        proceso.resumen_ia = "(resumen no generado: falta AI_SUMMARY_API_KEY en .env)"
                except Exception as e:
                    print(f"[{cliente.identificacion}] Falló resumen IA para {proceso.numero_proceso}: {type(e).__name__}: {e}")
                    proceso.resumen_ia = "(resumen no generado: error al generar)"

            except Exception as e:
                print(f"[{cliente.identificacion}] Falló descarga de {numero_fila}: {type(e).__name__}: {e}")
                if "closed" in str(e).lower():
                    print("ADVERTENCIA CRÍTICA: la página/navegador se cerró inesperadamente. Abortando el resto de descargas para este cliente.")
                    break

    def descargar_pdf_proceso(self, page: Page, indice_fila: int, max_movimientos_a_probar: int = 5, max_pdfs_deseados: int = 2) -> tuple[list[bytes], dict]:
        boton_movimientos = f"#form1\\:dataTableJuicios2\\:{indice_fila}\\:btnAbrirMovimientos"
        page.click(boton_movimientos)

        botones_ver_detalle = page.locator("#formJuicioDialogo").get_by_title("Ver Detalle del Incidente del Proceso Judicial")
        botones_ver_detalle.first.wait_for(state="visible", timeout=15000)
        self.delay_humano(0.5, 1.0)

        orden_por_fecha = self._orden_movimientos_por_fecha(page)
        intentos_en_orden = orden_por_fecha[:max_movimientos_a_probar]

        pdfs_obtenidos = []
        detalle_final = None

        for indice_movimiento in intentos_en_orden:
            if len(pdfs_obtenidos) >= max_pdfs_deseados:
                break
            try:
                contenido_pdf, detalle = self._intentar_descargar_movimiento(page, indice_movimiento)
                pdfs_obtenidos.append(contenido_pdf)
                if detalle_final is None:
                    detalle_final = detalle
            except ScraperError as e:
                print(f"    Movimiento {indice_movimiento} sin PDF, probando el siguiente... ({e})")
                continue
            except Exception as e:
                print(f"    Movimiento {indice_movimiento} falló inesperadamente, probando el siguiente... ({type(e).__name__}: {e})")
                continue

        try:
            page.click("#formJuicioDialogo\\:btnCancelar", timeout=5000)
            page.wait_for_selector("#formJuicioDialogo", state="hidden", timeout=5000)
        except Exception:
            pass
        self.delay_humano(0.3, 0.6)

        if not pdfs_obtenidos:
            raise ScraperError(
                f"[{self.nombre_sitio}] Ninguno de los primeros {len(intentos_en_orden)} movimientos "
                f"tuvo PDF descargable (fila {indice_fila}).",
                resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
            )

        return pdfs_obtenidos, detalle_final

    def _orden_movimientos_por_fecha(self, page: Page) -> list[int]:
        from datetime import datetime

        botones = page.locator("#formJuicioDialogo").get_by_title("Ver Detalle del Incidente del Proceso Judicial")
        total = botones.count()
        fechas = []

        for i in range(total):
            try:
                fila = botones.nth(i).locator("xpath=ancestor::tr[1]")
                texto_fecha = fila.locator("td").nth(1).inner_text().strip()
                fecha = datetime.strptime(texto_fecha, "%d/%m/%Y %H:%M")
            except Exception:
                fecha = datetime.min
            fechas.append((i, fecha))

        fechas.sort(key=lambda par: par[1], reverse=True)
        return [indice for indice, _ in fechas]

    def _intentar_descargar_movimiento(self, page: Page, indice_movimiento: int) -> tuple[bytes, dict]:
        botones_ver_detalle = page.locator("#formJuicioDialogo").get_by_title("Ver Detalle del Incidente del Proceso Judicial")
        botones_ver_detalle.nth(indice_movimiento).click()

        page.wait_for_selector("#formJuicioDetalle", state="visible")
        self.delay_humano(0.5, 1.0)

        try:
            if page.locator("#formJuicioDetalle\\:dataTable_data").locator(
                "text=No se registraron actividades en esta judicatura"
            ).count() > 0:
                raise ScraperError(
                    f"[{self.nombre_sitio}] Sin actividades registradas en esta judicatura "
                    f"para el movimiento {indice_movimiento}.",
                    resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
                )

            detalle = self._extraer_detalle_proceso(page)

            link_imprimir = page.locator("a.estiloLinkImprimir")
            try:
                link_imprimir.wait_for(state="visible", timeout=5000)
            except Exception:
                raise ScraperError(
                    f"[{self.nombre_sitio}] Sin acta o documento disponible para este movimiento.",
                    resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
                )

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
                    page.click("a.estiloLinkImprimir")
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
                        f"[{self.nombre_sitio}] Movimiento {indice_movimiento} sin PDF capturable.",
                        resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
                    )

                return contenido_pdf, detalle

            finally:
                page.context.remove_listener("page", _al_crear_pagina_nueva)

        finally:
            try:
                page.click("#formJuicioDetalle\\:btnCerrar", timeout=5000)
                page.wait_for_selector("#juicioDetalleDialogo", state="hidden", timeout=8000)
            except Exception:
                pass
            self.delay_humano(0.5, 0.8)

    def _extraer_detalle_proceso(self, page: Page) -> dict:
        def _valor_por_etiqueta(texto_etiqueta: str) -> str:
            fila = page.locator(
                f"td.titulo:has(label:text-is('{texto_etiqueta}'))"
            ).locator("xpath=following-sibling::td[1]")
            return fila.inner_text().strip()

        lugar = _valor_por_etiqueta("Dependencia jurisdiccional:")
        materia = _valor_por_etiqueta("Acción/Infracción:")

        demandados = page.locator(
            "td.titulo:has(label:text-is('Demandado(s)/Procesado(s):'))"
        ).locator("xpath=following-sibling::td[1]//dt.ui-datalist-item").all_inner_texts()
        demandado = "; ".join(d.strip() for d in demandados)

        return {"lugar": lugar, "materia": materia, "demandado": demandado}