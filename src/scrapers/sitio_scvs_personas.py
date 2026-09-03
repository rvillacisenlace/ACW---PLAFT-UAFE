"""
Scraper del Sitio 3, Flujo 3.1 (SCVS - Consulta de Personas).

Módulo ZK Framework - IDs dinámicos por sesión, todos los selectores se
basan en clase CSS o texto visible, nunca en el ID completo.

Alcance REAL confirmado con el usuario (2026-09-03) contra el Excel de
referencia (caso Corredor Camargo Silverio, 1706794003001):
- Se extraen 2 secciones: "Administración Actual en:" (Presidente/RL) y
  "Accionista Actual en:". Los totales de cada una van en columnas
  separadas (Z, AA), SIN deduplicar entre si.
- Las empresas se FUSIONAN por RUC: si una empresa aparece en ambas
  secciones, su Cargo combina ambos roles ("Accionista / PRESIDENTE").
  Si aparece solo en una, el Cargo refleja solo esa.
- La lista fusionada se ordena por Capital Invertido DESCENDENTE
  (confirmado por el usuario como la regla real), y se toman las
  primeras 4 (hay 4 slots en el Excel real, no 3 como se asumio
  inicialmente).
- Empresas que solo aparecen en "Administración Actual" (sin ser
  tambien accionistas) no tienen Capital Invertido - se tratan como 0
  para efectos de orden (quedan al final), y aparecen en el Cargo con
  el texto de administracion.
- "Patrimonio (Último año) BG-3" queda PENDIENTE - requiere un modulo
  de SCVS que todavia no se ha explorado (sin HTML de referencia aun).
  Todas las participaciones se devuelven con ese campo en "-".
- La Actividad Económica (Observaciones) y Fecha de Constitución se
  obtienen via consulta cruzada a SRI, en pestaña separada.
"""
import time

from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, TipoPersona, ParticipacionSocietaria, ResultadoConsulta
from src.scrapers.sitio_sri import ScraperSRI

ID_COMBOBOX_INPUT = "input.z-combobox-inp"
ID_PANEL_SUGERENCIAS = ".z-combobox-pp .z-comboitem"
TEXTO_RADIO_IDENTIFICACION = "Identificación"
TEXTO_ENCABEZADO_ACCIONISTA_ACTUAL = "Accionista Actual en:"
TEXTO_ENCABEZADO_ADMINISTRACION_ACTUAL = "Administración Actual en:"
TEXTO_SIN_COINCIDENCIA = "No existe ninguna coincidencia con el parámetro ingresado"
MAXIMO_SLOTS = 4


class ScraperSCVSPersonas(BaseScraper):
    nombre_sitio = "SCVS - Consulta de Personas"

    def __init__(self, context, url_base: str, url_base_sri: str):
        super().__init__(context, url_base)
        self.scraper_sri = ScraperSRI(context=context, url_base=url_base_sri)

    def tiene_captcha(self, page: Page) -> bool:
        return False  # confirmado por el usuario: este modulo no tiene captcha

    def buscar_cliente(self, page: Page, cliente: Cliente) -> dict:
        """
        Devuelve un dict con:
        - "total_presidente_rl": int (columna Z)
        - "total_accionista": int (columna AA)
        - "participaciones": list[ParticipacionSocietaria], hasta 4 (slots AB-BK)
        """
        page.goto(self.url_base)
        self.delay_humano(1.0, 2.0)

        page.click(f"label:has-text('{TEXTO_RADIO_IDENTIFICACION}')")
        self.delay_humano(0.3, 0.6)

        campo = page.locator(ID_COMBOBOX_INPUT).first
        campo.click()
        campo.type(cliente.identificacion, delay=100)
        self.delay_humano(1.0, 1.5)

        valor_campo = campo.input_value()
        if cliente.identificacion not in valor_campo:
            raise ScraperError(
                f"[{self.nombre_sitio}] El campo no se auto-completó como se esperaba para "
                f"'{cliente.identificacion}' (valor actual: '{valor_campo}').",
                resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
            )

        page.locator("span.z-button:has-text('Buscar')").first.click()

        # El sitio puede responder con la pantalla de resultados, o con
        # un mensaje rojo de "sin coincidencia" (identificacion sin
        # registros - caso normal, no un error). Polling por ambos.
        locator_sin_coincidencia = page.locator(f"div.z-div:has-text('{TEXTO_SIN_COINCIDENCIA}')")
        locator_con_resultados = page.locator(f"td.z-caption-l:has-text('{TEXTO_ENCABEZADO_ACCIONISTA_ACTUAL}')")

        tiempo_limite = time.time() + 20
        sin_coincidencia = False
        encontro_resultados = False
        while time.time() < tiempo_limite:
            if locator_sin_coincidencia.count() > 0:
                sin_coincidencia = True
                break
            if locator_con_resultados.count() > 0:
                encontro_resultados = True
                break
            page.wait_for_timeout(500)

        if sin_coincidencia:
            return {"total_presidente_rl": 0, "total_accionista": 0, "participaciones": []}

        if not encontro_resultados:
            raise ScraperError(
                f"[{self.nombre_sitio}] Ni resultados ni mensaje de 'sin coincidencia' aparecieron tras 20s "
                f"para '{cliente.identificacion}' - posible cambio en el sitio.",
                resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
            )

        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        self.delay_humano(2.5, 3.5)

        from src.documentos.evidencia import capturar_evidencia
        capturar_evidencia(
            page, cliente.identificacion_evidencia or cliente.identificacion,
            sitio="sitio3_scvs_personas_resultado", carpeta_sitio="scvs_personas",
            subcarpeta=cliente.subcarpeta_evidencia,
        )

        filas_administracion = self._extraer_tabla(page, TEXTO_ENCABEZADO_ADMINISTRACION_ACTUAL)
        filas_accionista = self._extraer_tabla(page, TEXTO_ENCABEZADO_ACCIONISTA_ACTUAL)

        total_presidente_rl = len(filas_administracion)
        total_accionista = len(filas_accionista)

        participaciones = self._fusionar_por_ruc(filas_administracion, filas_accionista)
        participaciones = participaciones[:MAXIMO_SLOTS]

        # Consulta cruzada por RUC via SRI para Actividad Economica
        # (Observaciones) y Fecha de Constitucion, en pestaña separada
        # para no interferir con 'page' (que sigue en SCVS).
        for participacion in participaciones:
            pagina_sri = page.context.new_page()
            try:
                cliente_empresa_relacionada = Cliente(
                    identificacion=participacion.ruc_empresa, tipo_persona=TipoPersona.JURIDICA,
                    razon_social=participacion.nombre_empresa,
                )
                datos_sri = self.scraper_sri.consultar_ruc(pagina_sri, cliente_empresa_relacionada)
                participacion.actividad_economica = datos_sri.get("actividad_economica", "") or "No disponible"
                participacion.fecha_constitucion = datos_sri.get("fecha_inicio_actividades", "") or "-"
            except Exception as e:
                print(f"    [SCVS Personas] No se pudo obtener datos SRI de {participacion.nombre_empresa} ({participacion.ruc_empresa}): {type(e).__name__}: {e}")
                participacion.actividad_economica = "No disponible"
            finally:
                pagina_sri.close()

        return {
            "total_presidente_rl": total_presidente_rl,
            "total_accionista": total_accionista,
            "participaciones": participaciones,
        }

    def _extraer_tabla(self, page: Page, texto_encabezado: str) -> list[dict]:
        """
        Extrae todas las filas de una seccion identificada por su texto
        de encabezado ("Administración Actual en:" o "Accionista Actual
        en:"). Devuelve dicts crudos (sin fusionar todavia) con las
        columnas relevantes de cada tabla - las 2 secciones NO tienen
        las mismas columnas, por eso se detecta cual es por el texto del
        encabezado recibido.

        Estructura DOM confirmada con evidencia real: el div exterior
        exacto "z-groupbox-3d" es ancestro del encabezado, y el
        contenedor de datos es su HIJO DIRECTO con clase
        "z-groupbox-3d-cnt" (NO un hermano, y NO se debe usar
        contains() para el ancestro - engancha con subclases como
        "z-groupbox-3d-hm").
        """
        encabezado = page.locator(f"td.z-caption-l:has-text('{texto_encabezado}')").first
        if encabezado.count() == 0:
            return []

        contenedor_datos = encabezado.locator(
            "xpath=ancestor::div[@class='z-groupbox-3d'][1]/div[contains(@class,'z-groupbox-3d-cnt')]"
        )
        filas_dom = contenedor_datos.locator("tr.z-listitem").all()

        filas = []
        for fila in filas_dom:
            celdas = fila.locator("td").all_inner_texts()
            celdas = [c.strip() for c in celdas]
            if texto_encabezado == TEXTO_ENCABEZADO_ADMINISTRACION_ACTUAL:
                # Columnas: Expediente, Nombre, Ruc, Nacionalidad, Cargo, ...
                if len(celdas) < 5:
                    continue
                filas.append({"nombre": celdas[1], "ruc": celdas[2], "cargo": celdas[4]})
            else:
                # Columnas: Expediente, Nombre, Ruc, Capital Invertido, Capital Total Cía., Valor Nominal, Situación Legal, Posesión Efectiva
                if len(celdas) < 7:
                    continue
                filas.append({
                    "nombre": celdas[1], "ruc": celdas[2],
                    "capital_invertido": celdas[3], "situacion_legal": celdas[6],
                })

        return filas

    def _fusionar_por_ruc(self, filas_administracion: list[dict], filas_accionista: list[dict]) -> list[ParticipacionSocietaria]:
        """
        Fusiona ambas listas por RUC de empresa. Si una empresa aparece
        en ambas, el Cargo combina los 2 roles ("Accionista / CARGO_TEXTUAL").
        Ordena por Capital Invertido descendente (confirmado por el
        usuario como la regla real de orden) - empresas sin capital
        (solo en Administración) se tratan como 0, quedan al final.
        """
        por_ruc: dict[str, ParticipacionSocietaria] = {}

        for fila in filas_accionista:
            ruc = fila["ruc"]
            por_ruc[ruc] = ParticipacionSocietaria(
                ruc_empresa=ruc, nombre_empresa=fila["nombre"],
                cargo="Accionista",
                capital_invertido=fila["capital_invertido"],
                situacion_legal=fila["situacion_legal"],
            )

        for fila in filas_administracion:
            ruc = fila["ruc"]
            if ruc in por_ruc:
                por_ruc[ruc].cargo = f"Accionista / {fila['cargo']}"
            else:
                por_ruc[ruc] = ParticipacionSocietaria(
                    ruc_empresa=ruc, nombre_empresa=fila["nombre"],
                    cargo=fila["cargo"],
                )

        def _capital_numerico(p: ParticipacionSocietaria) -> float:
            try:
                return float(p.capital_invertido)
            except (ValueError, TypeError):
                return 0.0

        return sorted(por_ruc.values(), key=_capital_numerico, reverse=True)