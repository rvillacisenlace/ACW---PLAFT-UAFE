"""
Capa de escritura del Excel. Dos implementaciones intercambiables:
- LocalExcelWriter: escribe directo al .xlsx local (para la demo, sin Graph API).
- GraphAPIWriter: [pendiente] cuando tengas tenant_id/client_id/client_secret/
  drive_id/item_id, se activa sin cambiar una línea de main.py.

main.py solo debe conocer la interfaz ExcelWriter, nunca la implementación.
"""
from abc import ABC, abstractmethod
from openpyxl import load_workbook


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
    def guardar(self) -> None:
        raise NotImplementedError


class LocalExcelWriter(ExcelWriter):
    def __init__(self, ruta_excel: str, nombre_hoja: str = "Clientes",
                 col_estado: str = "Estado-Consulta", col_detalle: str = "Detalle"):
        self.ruta_excel = ruta_excel
        self.wb = load_workbook(ruta_excel)
        self.hoja = self.wb[nombre_hoja]

        encabezados = [c.value for c in self.hoja[1]]
        self.idx_estado = encabezados.index(col_estado) + 1  # openpyxl es 1-indexed

        # Detalle es opcional: si no existe la columna en tu Excel de prueba,
        # simplemente no se escribe nada ahí (no truena).
        self.idx_detalle = (
            encabezados.index(col_detalle) + 1 if col_detalle in encabezados else None
        )

    def actualizar_estado_cliente(self, fila_excel: int, estado: str, detalle: str = "") -> None:
        self.hoja.cell(row=fila_excel, column=self.idx_estado).value = estado
        if self.idx_detalle:
            self.hoja.cell(row=fila_excel, column=self.idx_detalle).value = detalle

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

        filas_valores = []

        if not procesos_filtrados:
            filas_valores.append([
                cliente.identificacion, "Sitio 1 - Función Judicial",
                "", "", "", "", "Sin procesos vigentes",
            ])
        else:
            for proceso in procesos_filtrados:
                filas_valores.append([
                    cliente.identificacion, "Sitio 1 - Función Judicial",
                    proceso.numero_proceso,
                    proceso.materia or proceso.accion_infraccion_delito,
                    proceso.demandado, proceso.lugar,
                    proceso.resumen_ia or "(resumen no generado)",
                ])

        for denuncia in denuncias_filtradas:
            filas_valores.append([
                cliente.identificacion, "Sitio 2 - Fiscalía",
                denuncia.numero_noticia_delito, denuncia.delito,
                denuncia.nombre_sospechoso, denuncia.lugar, "",
            ])

        fila_inicial = self._obtener_ultima_fila("DetalleProcesos") + 1
        self._escribir_filas_batch("DetalleProcesos", fila_inicial, filas_valores)

    def escribir_procesos_omitidos(self, cliente, procesos_judiciales: list) -> None:
            """
            Registra los procesos que excedieron el límite de volumen (top 10),
            con datos básicos según exige el spec (Escenario 5): Número, Actor,
            Demandado, Estado. Solo aplica a Sitio 1 - Sitio 2 no tiene límite
            de volumen (confirmado que las denuncias por persona son pocas).
            """
            nombre_hoja = "ProcesosOmitidos"
            if nombre_hoja not in self.wb.sheetnames:
                hoja_omitidos = self.wb.create_sheet(nombre_hoja)
                hoja_omitidos.append([
                    "Identificacion_Cliente", "Numero_Proceso",
                    "Accion_Infraccion", "Demandado", "Estado_Observacion",
                ])
            else:
                hoja_omitidos = self.wb[nombre_hoja]

            omitidos = [p for p in procesos_judiciales if p.omitido_por_volumen or p.excluido_por_materia]

            for proceso in omitidos:
                hoja_omitidos.append([
                    cliente.identificacion,
                    proceso.numero_proceso,
                    proceso.accion_infraccion_delito,
                    proceso.demandado,  # ya contiene el "(inferido de campo de búsqueda...)"
                    proceso.resumen_ia,  # aquí vive el mensaje "Proceso omitido por límite de volumen..."
                ])

    def guardar(self) -> None:
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