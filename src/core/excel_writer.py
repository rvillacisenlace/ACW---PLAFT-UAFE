"""
Capa de escritura del Excel. Dos implementaciones intercambiables:
- LocalExcelWriter: escribe directo al .xlsx local (para la demo, sin Graph API).
- GraphAPIWriter: cuando tengas tenant_id/client_id/client_secret/drive_id/item_id,
  se activa sin cambiar una línea de main.py.

main.py solo debe conocer la interfaz ExcelWriter, nunca la implementación.
"""
from abc import ABC, abstractmethod
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment
from openpyxl.styles import Font, Alignment, PatternFill


class ExcelWriter(ABC):
    @abstractmethod
    def actualizar_estado_cliente(self, fila_excel: int, estado: str, detalle: str = "") -> None:
        raise NotImplementedError

    @abstractmethod
    def escribir_detalle_procesos(self, cliente, procesos_judiciales: list, denuncias: list) -> None:
        raise NotImplementedError

    @abstractmethod
    def escribir_procesos_omitidos(self, cliente, procesos_judiciales: list) -> None:
        raise NotImplementedError

    @abstractmethod
    def leer_clientes_pendientes(self, nombre_hoja: str = None) -> list:
        raise NotImplementedError

    @abstractmethod
    def leer_parametrizacion(self, nombre_hoja: str = "Parametrizacion") -> dict:
        raise NotImplementedError

    @abstractmethod
    def guardar(self) -> None:
        raise NotImplementedError


class LocalExcelWriter(ExcelWriter):
    """
    Apunta a la hoja real 'Revision' del Excel de trabajo. El encabezado
    real ocupa las filas 1-3 (grupo -> subgrupo -> campo, con celdas
    combinadas) - por eso el nombre de cada columna puede vivir en
    cualquiera de esas 3 filas, no solo en la fila 1. Los datos de
    clientes empiezan en la fila 4.
    """
    FILA_INICIO_DATOS = 4

    ESTILO_FUENTE = Font(name="Book Antiqua", size=11)
    ESTILO_ALINEACION = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ESTILO_RELLENO = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    
    # Columnas del bloque SRI-cliente (14-21) - hardcodeadas por indice
    # porque sus nombres de columna se repiten identicos en el bloque
    # de representante legal (22-29) y _col() por nombre resolveria mal
    # (el diccionario de mapa_columnas no distingue duplicados).
    COL_SRI_RAZON_SOCIAL = 14
    COL_SRI_ESTADO_CONTRIBUYENTE = 15
    COL_SRI_FECHA_INICIO = 16
    COL_SRI_FECHA_CESE = 17
    COL_SRI_FECHA_REINICIO = 18
    COL_SRI_CONTRIBUYENTE_FANTASMA = 19
    COL_SRI_TRANSACCIONES_INEXISTENTES = 20
    COL_SRI_ACTIVIDAD_ECONOMICA = 21

    # Bloque SRI-representante-legal (22-29) - mismo motivo de indices
    # directos que el bloque anterior. OJO: el orden de campos aqui es
    # distinto al bloque del cliente (actividad economica va antes que
    # fantasma/transacciones, no al final).
    COL_SRI_RL_RAZON_SOCIAL = 22
    COL_SRI_RL_ESTADO_CONTRIBUYENTE = 23
    COL_SRI_RL_FECHA_INICIO = 24
    COL_SRI_RL_FECHA_CESE = 25
    COL_SRI_RL_FECHA_REINICIO = 26
    COL_SRI_RL_ACTIVIDAD_ECONOMICA = 27
    COL_SRI_RL_CONTRIBUYENTE_FANTASMA = 28
    COL_SRI_RL_TRANSACCIONES_INEXISTENTES = 29

    # Bloque Contraloria (EB-EG). "Cargo" se repite 5 veces en la hoja
    # (columnas 50,59,68,77,135) - se usa indice directo, no _col().
    # ED "Categoria" (134) se deja SIN TOCAR - es de llenado manual.
    COL_CONTRALORIA_DECLARACIONES = 132
    COL_CONTRALORIA_VIGENCIA = 133
    COL_CONTRALORIA_CARGO = 135
    COL_CONTRALORIA_TIEMPO = 136
    COL_CONTRALORIA_ULTIMO_ANIO = 137

    # Bloque Sentenciados (EM-EY). Los 4 nombres de columna (No., No.
    # Proceso, Fecha de Resolucion, Infraccion) se repiten 3 veces (uno
    # por cada slot de hasta 3 sentencias) - indices directos.
    COL_SENTENCIADOS_TOTAL = 143
    COL_SENTENCIADOS_SLOTS = [
        (144, 145, 146, 147),  # No., No. Proceso, Fecha, Infraccion - slot 1
        (148, 149, 150, 151),  # slot 2
        (152, 153, 154, 155),  # slot 3
    ]

    # Bloque Funcion Judicial / CNJ (EZ-FP). "No.", "Fecha de ingreso",
    # "No. proceso", "Accion /Infraccion", "Observaciones" se repiten 3
    # veces (slots) - indices directos.
    COL_CNJ_TOTAL = 156
    COL_CNJ_TEMATICA = 157
    COL_CNJ_SLOTS = [
        (158, 159, 160, 161, 162),  # No., Fecha ingreso, No. proceso, Accion/Infraccion, Observaciones - slot 1
        (163, 164, 165, 166, 167),  # slot 2
        (168, 169, 170, 171, 172),  # slot 3
    ]

    def __init__(self, ruta_excel: str, nombre_hoja: str = "Revision"):
        self.ruta_excel = ruta_excel
        self.nombre_hoja = nombre_hoja
        self.wb = load_workbook(ruta_excel)
        self.hoja = self.wb[nombre_hoja]
        self.mapa_columnas = self._construir_mapa_columnas(self.hoja)

        # Mitigacion de un bug conocido de openpyxl: wb.save() CIERRA el
        # stream interno de cada imagen embebida al terminar de guardar.
        # Un segundo guardado en el mismo proceso falla con "I/O
        # operation on closed file" porque no hay como releer un stream
        # ya cerrado. Se capturan los bytes crudos UNA SOLA VEZ aqui,
        # mientras los streams siguen frescos tras la carga, y cada
        # guardado posterior arma un BytesIO nuevo desde esa copia en
        # memoria - nunca depende de releer un stream ya usado.
        # Confirmado con evidencia real: 5/5 guardados seguidos en el
        # mismo proceso, antes fallaba siempre en el 2do.
        import io
        self._imagenes_bytes_originales = []
        for hoja_wb in self.wb.worksheets:
            for img in getattr(hoja_wb, "_images", []):
                img.ref.seek(0)
                self._imagenes_bytes_originales.append((img, img.ref.read()))

    def _construir_mapa_columnas(self, hoja) -> dict:
        """
        Construye {nombre_columna_normalizado: indice_1based} leyendo las
        3 filas de encabezado. Si una columna tiene texto en mas de una
        fila (raro, pero por si acaso), se usa la fila mas profunda (3 >
        2 > 1) porque ahi vive el nombre de campo especifico, no el del
        grupo/subgrupo.
        """
        mapa = {}
        for col in range(1, hoja.max_column + 1):
            valor = (
                hoja.cell(row=3, column=col).value
                or hoja.cell(row=2, column=col).value
                or hoja.cell(row=1, column=col).value
            )
            if valor:
                mapa[str(valor).strip()] = col
        return mapa

    def _col(self, nombre_columna: str) -> int:
        if nombre_columna not in self.mapa_columnas:
            raise KeyError(f"Columna '{nombre_columna}' no encontrada en la hoja '{self.nombre_hoja}'")
        return self.mapa_columnas[nombre_columna]

    def _escribir_valor_con_estilo(self, fila: int, col: int, valor) -> None:
        celda = self.hoja.cell(row=fila, column=col)
        celda.value = valor
        celda.font = self.ESTILO_FUENTE
        celda.alignment = self.ESTILO_ALINEACION
        celda.fill = self.ESTILO_RELLENO

    def leer_clientes_pendientes(self, nombre_hoja: str = None) -> list:
        """
        Lee clientes pendientes de la hoja 'Revision' real. No existe
        columna 'Tipo' explicita - se infiere Natural/Juridica segun si
        esta llena 'Apellidos Y Nombres' o 'Razon Social' (mismo criterio
        que ya usan los scrapers). Todo lo que NO sea 'Completado' en
        ESTADO se considera pendiente.
        """
        from src.core.models import Cliente, TipoPersona

        col_id = self._col("Ruc / CI")
        col_nombres = self._col("Apellidos Y Nombres (P.Natural / P.Juridica)")
        col_razon = self._col("Razon Social (Empresa)")
        col_estado = self._col("ESTADO")

        clientes = []
        for fila in range(self.FILA_INICIO_DATOS, self.hoja.max_row + 1):
            identificacion = self.hoja.cell(row=fila, column=col_id).value
            if not identificacion or not str(identificacion).strip():
                continue

            estado = self.hoja.cell(row=fila, column=col_estado).value
            if estado and str(estado).strip().lower() == "completado":
                continue

            nombres = self.hoja.cell(row=fila, column=col_nombres).value
            razon = self.hoja.cell(row=fila, column=col_razon).value
            tipo = TipoPersona.NATURAL if nombres else TipoPersona.JURIDICA

            clientes.append(Cliente(
                identificacion=str(identificacion).strip(),
                tipo_persona=tipo,
                nombres_completos=(str(nombres).strip() if nombres else ""),
                razon_social=(str(razon).strip() if razon else ""),
                fila_excel=fila,
            ))

        return clientes

    def leer_parametrizacion(self, nombre_hoja: str = "Parametrizacion") -> dict:
        hoja = self.wb[nombre_hoja]
        parametros = {}
        for fila in hoja.iter_rows(min_row=2, values_only=True):
            if len(fila) >= 2 and fila[0]:
                parametros[fila[0]] = fila[1]
        return parametros
    
    def escribir_sri_ruc(self, fila_excel: int, datos: dict, datos_representante_legal: dict = None) -> None:
        """
        Escribe el resultado de consultar_ruc() del SRI para el cliente,
        y opcionalmente para su representante legal (bloque 22-29). Si
        no hay representante legal resuelto, ese bloque se llena con "NA".
        """
        # Bloque SRI del cliente
        self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_RAZON_SOCIAL, datos.get("razon_social", ""))
        self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_ESTADO_CONTRIBUYENTE, datos.get("estado_contribuyente", ""))
        self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_FECHA_INICIO, datos.get("fecha_inicio_actividades", ""))
        self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_FECHA_CESE, datos.get("fecha_cese_actividades", ""))
        self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_FECHA_REINICIO, datos.get("fecha_reinicio_actividades", ""))
        self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_CONTRIBUYENTE_FANTASMA, datos.get("contribuyente_fantasma", ""))
        self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_TRANSACCIONES_INEXISTENTES, datos.get("contribuyente_transacciones_inexistentes", ""))
        self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_ACTIVIDAD_ECONOMICA, datos.get("actividad_economica", ""))

        # Bloque Identificacion Basica
        self._escribir_valor_con_estilo(fila_excel, self._col("Representante Legal"), datos.get("representante_legal_nombre", ""))
        self._escribir_valor_con_estilo(fila_excel, self._col("ID Representante Legal"), datos.get("representante_legal_identificacion", ""))
        self._escribir_valor_con_estilo(fila_excel, self._col("Dirección Domicilio"), datos.get("direccion_matriz", ""))
        self._escribir_valor_con_estilo(fila_excel, self._col("Fecha de Constitucion"), datos.get("fecha_inicio_actividades", ""))

        # Bloque SRI del representante legal (22-29), o "NA" si no aplica
        columnas_rl = [
            self.COL_SRI_RL_RAZON_SOCIAL, self.COL_SRI_RL_ESTADO_CONTRIBUYENTE,
            self.COL_SRI_RL_FECHA_INICIO, self.COL_SRI_RL_FECHA_CESE,
            self.COL_SRI_RL_FECHA_REINICIO, self.COL_SRI_RL_ACTIVIDAD_ECONOMICA,
            self.COL_SRI_RL_CONTRIBUYENTE_FANTASMA, self.COL_SRI_RL_TRANSACCIONES_INEXISTENTES,
        ]
        if not datos_representante_legal:
            for col in columnas_rl:
                self._escribir_valor_con_estilo(fila_excel, col, "-")
        else:
            self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_RL_RAZON_SOCIAL, datos_representante_legal.get("razon_social", ""))
            self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_RL_ESTADO_CONTRIBUYENTE, datos_representante_legal.get("estado_contribuyente", ""))
            self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_RL_FECHA_INICIO, datos_representante_legal.get("fecha_inicio_actividades", ""))
            self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_RL_FECHA_CESE, datos_representante_legal.get("fecha_cese_actividades", ""))
            self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_RL_FECHA_REINICIO, datos_representante_legal.get("fecha_reinicio_actividades", ""))
            self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_RL_ACTIVIDAD_ECONOMICA, datos_representante_legal.get("actividad_economica", ""))
            self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_RL_CONTRIBUYENTE_FANTASMA, datos_representante_legal.get("contribuyente_fantasma", ""))
            self._escribir_valor_con_estilo(fila_excel, self.COL_SRI_RL_TRANSACCIONES_INEXISTENTES, datos_representante_legal.get("contribuyente_transacciones_inexistentes", ""))

    def escribir_sri_deudas(self, fila_excel: int, tiene_deuda_firme: bool, valor_deuda_firme: str = "") -> None:
        col = self._col("SRI DEUDAS")
        if tiene_deuda_firme:
            texto = f"El ciudadano / contribuyente registra un valor de deudas firmes de {valor_deuda_firme}"
        else:
            texto = "El ciudadano / contribuyente no registra deudas firmes."
        self._escribir_valor_con_estilo(fila_excel, col, texto)

    def escribir_sri_estado_tributario(self, fila_excel: int, resultado: str, obligaciones_pendientes: str = "") -> None:
        col = self._col("SRI OBLIGACIONES TRIBUTARIAS")
        if "AL DIA" in resultado.upper():
            texto = "AL DIA EN SUS OBLIGACIONES"
        else:
            texto = obligaciones_pendientes
        self._escribir_valor_con_estilo(fila_excel, col, texto)

    def escribir_municipios(self, fila_excel: int, resultados: dict) -> None:
        """
        Consolida los 5 municipios en 2 columnas (AF, AG).
        resultados: {"Quito": DeudaMunicipal, "Cuenca": DeudaMunicipal, ...}
        - Columna MUNICIPIO: nombres de los municipios CON deuda, separados por "/".
          Si el cliente no aparece registrado en NINGUNO de los 5, mensaje especial.
          Si aparece registrado pero sin deuda en ninguno, "Ninguno".
        - Columna DEUDA: suma total de las deudas de todos los municipios consultados.
        """
        municipios_con_deuda = []
        total_deuda = 0.0
        algun_registrado = False

        for nombre_municipio, deuda in resultados.items():
            if deuda.registrado:
                algun_registrado = True
            if deuda.tiene_deuda:
                municipios_con_deuda.append(nombre_municipio)
            valor_limpio = (deuda.valor_total or "0").replace("$", "").replace(",", "").strip()
            try:
                total_deuda += float(valor_limpio)
            except ValueError:
                pass  # valor no numerico (ej. mensaje de error) - no se suma, no se rompe

        if not algun_registrado:
            texto_municipios = "No existen registros en los 5 municipios"
        elif municipios_con_deuda:
            texto_municipios = " / ".join(municipios_con_deuda)
        else:
            texto_municipios = "Ninguno"

        self._escribir_valor_con_estilo(fila_excel, self._col("MUNICIPIO"), texto_municipios)
        self._escribir_valor_con_estilo(fila_excel, self._col("DEUDA"), f"${total_deuda:,.2f}")

    def escribir_sercop_proveedor(self, fila_excel: int, estado: str) -> None:
        """Columna INCOP (AH). El campo 'estado' del scraper ya viene
        formateado exactamente como se necesita: 'PROVEEDOR DEL ESTADO'
        o 'NO ES PROVEEDOR DEL ESTADO'."""
        col = self._col("INCOP")
        self._escribir_valor_con_estilo(fila_excel, col, estado)

    def escribir_sercop_certificados(self, fila_excel: int, datos: dict) -> None:
        """
        datos = resultado completo de buscar_cliente() en
        sitio_sercop_certificados.py: {"contratos_pendientes": {...},
        "incumplimientos": {...}}, cada uno con su propio 'resultado'
        (SI/NO/INDETERMINADO).
        - AI: contratos_pendientes -> "¿Tiene procesos pendientes con el Estado?"
        - AJ: incumplimientos -> "¿Es contratista incumplido?"
        """
        resultado_contratos = datos.get("contratos_pendientes", {}).get("resultado", "INDETERMINADO")
        resultado_incumplimientos = datos.get("incumplimientos", {}).get("resultado", "INDETERMINADO")

        self._escribir_valor_con_estilo(fila_excel, self._col("¿Tiene procesos pendientes con el Estado?"), resultado_contratos)
        self._escribir_valor_con_estilo(fila_excel, self._col("¿Es contratista incumplido?"), resultado_incumplimientos)

    def escribir_salud(self, fila_excel: int, situacion_laboral: str, tipo_afiliacion: str) -> None:
        """Columnas AL (Situacion Laboral) y AM (Tipo de Afiliacion)."""
        self._escribir_valor_con_estilo(fila_excel, self._col("Situación Laboral"), situacion_laboral)
        self._escribir_valor_con_estilo(fila_excel, self._col("Tipo de Afiliación"), tipo_afiliacion)

    def escribir_iess(self, fila_excel: int, iess: str, deuda_obligaciones: str = "") -> None:
        """
        Columnas AN (IESS - texto SI/NO registra mora) y AO (Deuda
        obligaciones patronales, formato $). deuda_obligaciones viene
        vacio del scraper cuando no hay mora (el regex solo matchea el
        monto si el texto menciona un valor) - se normaliza a "$0.00"
        en ese caso.
        """
        col_iess = self._col("IESS")
        col_deuda = self._col("Deuda obligaciones patronales")

        self._escribir_valor_con_estilo(fila_excel, col_iess, iess)

        valor_limpio = (deuda_obligaciones or "").strip()
        if not valor_limpio:
            texto_deuda = "$0.00"
        else:
            texto_deuda = valor_limpio if valor_limpio.startswith("$") else f"${valor_limpio}"

        self._escribir_valor_con_estilo(fila_excel, col_deuda, texto_deuda)

    def escribir_scvs_companias(self, fila_excel: int, registrado: bool, cumplimiento_obligaciones: str = "") -> None:
        """
        Columna Supercias (AR). Mapea el texto crudo del scraper
        (ej. "SI HA CUMPLIDO") a las 3 opciones exactas pedidas.
        Si la empresa no esta registrada en SCVS (RUC no encontrado),
        va "-" directamente.
        """
        col = self._col("Supercias")

        if not registrado:
            texto = "-"
        elif cumplimiento_obligaciones.strip().upper().startswith("SI"):
            texto = "SI Cumple con sus obligaciones"
        else:
            texto = "NO Cumple con sus obligaciones"

        self._escribir_valor_con_estilo(fila_excel, col, texto)

    def escribir_antecedentes_penales(self, fila_excel: int, posee_antecedentes: bool) -> None:
        col = self._col("Posee antecedentes penales")
        self._escribir_valor_con_estilo(fila_excel, col, "SI" if posee_antecedentes else "NO")

    def escribir_contraloria(self, fila_excel: int, resumen: dict) -> None:
        """resumen = resultado de ScraperContraloria.resumir_declaraciones()."""
        self._escribir_valor_con_estilo(fila_excel, self.COL_CONTRALORIA_DECLARACIONES, resumen.get("posee_declaraciones", "-"))
        self._escribir_valor_con_estilo(fila_excel, self.COL_CONTRALORIA_VIGENCIA, resumen.get("vigencia", "-"))
        self._escribir_valor_con_estilo(fila_excel, self.COL_CONTRALORIA_CARGO, resumen.get("cargo", "-"))
        self._escribir_valor_con_estilo(fila_excel, self.COL_CONTRALORIA_TIEMPO, resumen.get("tiempo", "-"))
        self._escribir_valor_con_estilo(fila_excel, self.COL_CONTRALORIA_ULTIMO_ANIO, resumen.get("ultimo_anio_en_cargo", "-"))

    def escribir_sentenciados(self, fila_excel: int, total_encontrado: int, top3: list) -> None:
        """
        top3: lista de objetos Sentenciado (hasta 3), ya ordenados por
        fecha mas reciente primero (el propio scraper los devuelve asi).
        Slots sin sentencia (cuando hay menos de 3) se llenan con "-".
        """
        self._escribir_valor_con_estilo(fila_excel, self.COL_SENTENCIADOS_TOTAL, str(total_encontrado))

        for i, (col_no, col_proceso, col_fecha, col_infraccion) in enumerate(self.COL_SENTENCIADOS_SLOTS):
            if i < len(top3):
                s = top3[i]
                self._escribir_valor_con_estilo(fila_excel, col_no, str(i + 1))
                self._escribir_valor_con_estilo(fila_excel, col_proceso, s.numero_proceso)
                self._escribir_valor_con_estilo(fila_excel, col_fecha, s.fecha_resolucion)
                self._escribir_valor_con_estilo(fila_excel, col_infraccion, s.infraccion)
            else:
                for col in (col_no, col_proceso, col_fecha, col_infraccion):
                    self._escribir_valor_con_estilo(fila_excel, col, "-")

    def escribir_funcion_judicial(self, fila_excel: int, procesos: list, total_procesos: int, tematica_general: str) -> None:
        """
        procesos: lista completa de ProcesoJudicial (incluye omitidos/
        excluidos). Solo los que NO estan omitidos_por_volumen ni
        excluidos_por_materia van en los 3 slots de detalle - mismo
        criterio que ya usa GraphAPIWriter.escribir_detalle_procesos.
        """
        self._escribir_valor_con_estilo(fila_excel, self.COL_CNJ_TOTAL, str(total_procesos))
        self._escribir_valor_con_estilo(fila_excel, self.COL_CNJ_TEMATICA, tematica_general)

        procesos_detalle = [
            p for p in procesos
            if not p.omitido_por_volumen and not p.excluido_por_materia
        ]

        for i, (col_no, col_fecha, col_proceso, col_accion, col_obs) in enumerate(self.COL_CNJ_SLOTS):
            if i < len(procesos_detalle):
                p = procesos_detalle[i]
                self._escribir_valor_con_estilo(fila_excel, col_no, str(i + 1))
                self._escribir_valor_con_estilo(fila_excel, col_fecha, p.fecha_ingreso)
                self._escribir_valor_con_estilo(fila_excel, col_proceso, p.numero_proceso)
                self._escribir_valor_con_estilo(fila_excel, col_accion, p.accion_infraccion_delito)
                self._escribir_valor_con_estilo(fila_excel, col_obs, p.resumen_ia)
            else:
                for col in (col_no, col_fecha, col_proceso, col_accion, col_obs):
                    self._escribir_valor_con_estilo(fila_excel, col, "-")

    def escribir_estado_final(self, fila_excel: int, resultados: dict) -> None:
        """
        Interpreta el diccionario de resultados por sitio (mismo formato
        que main.py produce: {nombre_sitio: resultado_o_error}) y escribe
        el ESTADO final. Un sitio fallido se ve como
        {"error": ..., "requiere_revision_manual": True}.
        - "Completado con pendientes": al menos un sitio requirio revision manual.
        - "Completado": todos los sitios terminaron sin marca de revision manual.
        """
        requiere_revision = any(
            isinstance(r, dict) and r.get("requiere_revision_manual")
            for r in resultados.values()
        )
        estado = "Completado con pendientes" if requiere_revision else "Completado"
        self.actualizar_estado_cliente(fila_excel, estado)

    def actualizar_estado_cliente(self, fila_excel: int, estado: str, detalle: str = "") -> None:
        col = self._col("ESTADO")
        self._escribir_valor_con_estilo(fila_excel, col, estado)
        # NOTA: 'detalle' no se escribe - no existe una columna de detalle
        # libre en la estructura real de 'Revision'. Si se necesita
        # guardar detalle en algun lado, definir en que columna del
        # mapeo real deberia ir (pendiente de confirmar).

    def escribir_detalle_procesos(self, cliente, procesos_judiciales: list, denuncias: list) -> None:
        # PENDIENTE - ROTO DESDE ANTES DE HOY, fuera de alcance de esta
        # sesion (no lo necesita Antecedentes Penales). Llama a
        # self._asegurar_hoja_existe / self._obtener_ultima_fila /
        # self._escribir_filas_batch, que solo existen en GraphAPIWriter,
        # nunca se definieron aqui en LocalExcelWriter. No usar todavia.
        raise NotImplementedError(
            "escribir_detalle_procesos no esta implementado en LocalExcelWriter "
            "(depende de metodos que solo existen en GraphAPIWriter) - pendiente."
        )

    def escribir_procesos_omitidos(self, cliente, procesos_judiciales: list) -> None:
        # PENDIENTE - mismo problema que escribir_detalle_procesos.
        raise NotImplementedError(
            "escribir_procesos_omitidos no esta implementado en LocalExcelWriter "
            "(depende de metodos que solo existen en GraphAPIWriter) - pendiente."
        )

    def _refrescar_streams_de_imagenes(self) -> None:
        """Arma un BytesIO nuevo para cada imagen desde los bytes crudos
        cacheados en __init__ - nunca relee un stream que un guardado
        anterior ya pudo haber cerrado."""
        import io
        for img, datos in self._imagenes_bytes_originales:
            img.ref = io.BytesIO(datos)

    def guardar(self) -> None:
        self._refrescar_streams_de_imagenes()
        self.wb.save(self.ruta_excel)


import truststore
truststore.inject_into_ssl()

import os
import msal
import requests


class GraphAPIWriter(ExcelWriter):
    """
    Escribe directamente en el Excel real alojado en el OneDrive de la
    cuenta de servicio, vía Microsoft Graph API. Usa sesión de workbook
    para agrupar los cambios y evitar bloquear el archivo a otros usuarios.
    """

    def __init__(self, cuenta_onedrive: str, drive_id: str, item_id: str,
                 tenant_id: str, client_id: str, client_secret: str,
                 nombre_hoja: str = "Clientes",
                 col_estado: str = "Estado-Consulta"):
        self.drive_id = drive_id
        self.item_id = item_id
        self.nombre_hoja = nombre_hoja
        self.col_estado = col_estado

        self._app_msal = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        self._refrescar_token()
        self.base_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook"
        self.session_id = self._crear_sesion()
        self._mapa_columnas = self._leer_encabezados()

    def _crear_sesion(self) -> str:
        resp = requests.post(
            f"{self.base_url}/createSession",
            headers=self.headers,
            json={"persistChanges": True},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _headers_con_sesion(self) -> dict:
        self._refrescar_token()  # se renueva solo si ya expiró/está por expirar
        return {**self.headers, "workbook-session-id": self.session_id}

    def _leer_encabezados(self) -> dict:
        """Lee la fila 1 de la hoja para saber en qué columna está cada campo."""
        url = f"{self.base_url}/worksheets/{self.nombre_hoja}/usedRange"
        resp = requests.get(url, headers=self._headers_con_sesion())
        resp.raise_for_status()
        valores = resp.json()["values"]
        encabezados = valores[0]
        return {nombre: idx for idx, nombre in enumerate(encabezados)}

    def _asegurar_hoja_existe(self, nombre_hoja: str, encabezados: list) -> None:
        """Crea la hoja con encabezados si todavía no existe en el archivo real."""
        resp = requests.get(f"{self.base_url}/worksheets", headers=self._headers_con_sesion())
        resp.raise_for_status()
        nombres_existentes = [h["name"] for h in resp.json()["value"]]

        if nombre_hoja not in nombres_existentes:
            requests.post(
                f"{self.base_url}/worksheets/add",
                headers=self._headers_con_sesion(),
                json={"name": nombre_hoja},
            ).raise_for_status()

            # Escribir encabezados en la fila 1
            letra_final = chr(ord("A") + len(encabezados) - 1)
            requests.patch(
                f"{self.base_url}/worksheets/{nombre_hoja}/range(address='A1:{letra_final}1')",
                headers=self._headers_con_sesion(),
                json={"values": [encabezados]},
            ).raise_for_status()

    def _obtener_ultima_fila(self, nombre_hoja: str) -> int:
        """Última fila REAL con contenido, vía usedRange (más confiable que
        el max_row de openpyxl, que puede inflarse por formato residual)."""
        resp = requests.get(
            f"{self.base_url}/worksheets/{nombre_hoja}/usedRange",
            headers=self._headers_con_sesion(),
        )
        resp.raise_for_status()
        datos = resp.json()
        return datos["rowIndex"] + datos["rowCount"]  # rowIndex es 0-based

    def _escribir_fila(self, nombre_hoja: str, num_fila: int, valores: list) -> None:
        letra_final = chr(ord("A") + len(valores) - 1)
        rango = f"A{num_fila}:{letra_final}{num_fila}"
        resp = requests.patch(
            f"{self.base_url}/worksheets/{nombre_hoja}/range(address='{rango}')",
            headers=self._headers_con_sesion(),
            json={"values": [valores]},
        )
        resp.raise_for_status()

    def actualizar_estado_cliente(self, fila_excel: int, estado: str, detalle: str = "") -> None:
        col_idx = self._mapa_columnas[self.col_estado]
        letra_columna = chr(ord("A") + col_idx)
        celda = f"{letra_columna}{fila_excel}"

        url = f"{self.base_url}/worksheets/{self.nombre_hoja}/range(address='{celda}')"
        resp = requests.patch(
            url, headers=self._headers_con_sesion(),
            json={"values": [[estado]]},
        )
        resp.raise_for_status()

    def escribir_detalle_procesos(self, cliente, procesos_judiciales: list, denuncias: list) -> None:
        encabezados = [
            "Identificacion_Cliente", "Sitio", "Numero_Proceso",
            "Tipo_Proceso", "Demandado_o_Rol", "Lugar", "Resumen_IA",
        ]
        self._asegurar_hoja_existe("DetalleProcesos", encabezados)

        procesos_filtrados = [
            p for p in procesos_judiciales
            if not p.omitido_por_volumen and not p.excluido_por_materia
        ]
        denuncias_filtradas = [d for d in denuncias if d.nombre_sospechoso]

        fila_actual = self._obtener_ultima_fila("DetalleProcesos") + 1

        if not procesos_filtrados:
            self._escribir_fila("DetalleProcesos", fila_actual, [
                cliente.identificacion, "Sitio 1 - Función Judicial",
                "", "", "", "", "Sin procesos vigentes",
            ])
            fila_actual += 1
        else:
            for proceso in procesos_filtrados:
                self._escribir_fila("DetalleProcesos", fila_actual, [
                    cliente.identificacion, "Sitio 1 - Función Judicial",
                    proceso.numero_proceso,
                    proceso.materia or proceso.accion_infraccion_delito,
                    proceso.demandado, proceso.lugar,
                    proceso.resumen_ia or "(resumen no generado)",
                ])
                fila_actual += 1

        for denuncia in denuncias_filtradas:
            self._escribir_fila("DetalleProcesos", fila_actual, [
                cliente.identificacion, "Sitio 2 - Fiscalía",
                denuncia.numero_noticia_delito, denuncia.delito,
                denuncia.nombre_sospechoso, denuncia.lugar, "",
            ])
            fila_actual += 1

    def escribir_procesos_omitidos(self, cliente, procesos_judiciales: list) -> None:
        encabezados = [
            "Identificacion_Cliente", "Numero_Proceso",
            "Accion_Infraccion", "Demandado", "Estado_Observacion",
        ]
        self._asegurar_hoja_existe("ProcesosOmitidos", encabezados)

        omitidos = [
            p for p in procesos_judiciales
            if p.omitido_por_volumen or p.excluido_por_materia
        ]
        if not omitidos:
            return

        fila_inicial = self._obtener_ultima_fila("ProcesosOmitidos") + 1
        filas_valores = [
            [cliente.identificacion, p.numero_proceso, p.accion_infraccion_delito,
             p.demandado, p.resumen_ia]
            for p in omitidos
        ]
        self._escribir_filas_batch("ProcesosOmitidos", fila_inicial, filas_valores)

    def leer_clientes_pendientes(self, nombre_hoja: str = None) -> list:
        """
        Lee los clientes pendientes directamente del Excel real en OneDrive,
        con la misma tolerancia que la versión local (todo lo que NO sea
        'Completado' se procesa).
        """
        from src.core.models import Cliente, TipoPersona

        hoja = nombre_hoja or self.nombre_hoja
        resp = requests.get(
            f"{self.base_url}/worksheets/{hoja}/usedRange",
            headers=self._headers_con_sesion(),
        )
        resp.raise_for_status()
        valores = resp.json()["values"]

        encabezados = valores[0]
        col = {str(nombre).strip(): idx for idx, nombre in enumerate(encabezados)}

        clientes = []
        for offset, fila in enumerate(valores[1:], start=2):
            estado = fila[col["Estado-Consulta"]] if col["Estado-Consulta"] < len(fila) else ""
            estado_normalizado = str(estado).strip().lower() if estado else ""
            if estado_normalizado == "completado":
                continue

            identificacion_cruda = fila[col["Identificacion"]] if col["Identificacion"] < len(fila) else None
            if identificacion_cruda is None or str(identificacion_cruda).strip() == "":
                continue

            identificacion = str(identificacion_cruda).strip()
            valor_tipo = fila[col["Tipo"]] if col["Tipo"] < len(fila) else ""
            tipo_normalizado = str(valor_tipo).strip().lower()
            tipo = TipoPersona.NATURAL if tipo_normalizado == "natural" else TipoPersona.JURIDICA

            idx_nombres = col.get("Nombres_Completos")
            idx_razon = col.get("RazonSocial")

            clientes.append(Cliente(
                identificacion=identificacion,
                tipo_persona=tipo,
                nombres_completos=(fila[idx_nombres] if idx_nombres is not None and idx_nombres < len(fila) and fila[idx_nombres] else ""),
                razon_social=(fila[idx_razon] if idx_razon is not None and idx_razon < len(fila) and fila[idx_razon] else ""),
                fila_excel=offset,
            ))

        return clientes

    def leer_parametrizacion(self, nombre_hoja: str = "Parametrizacion") -> dict:
        """Lee la Hoja de Parametrización directamente del Excel real."""
        resp = requests.get(
            f"{self.base_url}/worksheets/{nombre_hoja}/usedRange",
            headers=self._headers_con_sesion(),
        )
        resp.raise_for_status()
        valores = resp.json()["values"]

        parametros = {}
        for fila in valores[1:]:
            if len(fila) >= 2 and fila[0]:
                parametros[fila[0]] = fila[1]
        return parametros

    def _escribir_filas_batch(self, nombre_hoja: str, fila_inicial: int, filas_valores: list[list]) -> None:
        """
        Escribe MÚLTIPLES filas en una sola petición HTTP, en vez de una
        petición por fila. Crítico para clientes con muchos procesos
        omitidos (ej. 97 en un caso real) - sin esto, cada fila individual
        agrega latencia de red que se acumula a varios minutos.
        """
        if not filas_valores:
            return

        num_columnas = len(filas_valores[0])
        letra_final = chr(ord("A") + num_columnas - 1)
        fila_final = fila_inicial + len(filas_valores) - 1
        rango = f"A{fila_inicial}:{letra_final}{fila_final}"

        resp = requests.patch(
            f"{self.base_url}/worksheets/{nombre_hoja}/range(address='{rango}')",
            headers=self._headers_con_sesion(),
            json={"values": filas_valores},
        )
        resp.raise_for_status()

    def guardar(self) -> None:
        """Con Graph API los cambios ya son persistentes al escribirse -
        este método cierra la sesión de workbook."""
        try:
            requests.post(f"{self.base_url}/closeSession", headers=self._headers_con_sesion())
        except Exception:
            pass

    def _refrescar_token(self) -> None:
        """
        Pide un token a MSAL - la librería cachea internamente y solo
        hace una llamada de red real si el token actual ya expiró o está
        por expirar, así que es seguro llamarlo antes de cada operación
        sin preocuparse por sobrecargar de peticiones innecesarias.
        """
        resultado = self._app_msal.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in resultado:
            raise RuntimeError(f"No se pudo renovar el token de Graph API: {resultado.get('error_description')}")

        self.headers = {"Authorization": f"Bearer {resultado['access_token']}"}