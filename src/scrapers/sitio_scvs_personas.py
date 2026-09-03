"""
Scraper del Sitio 3, Flujo 3.1 (SCVS - Consulta de Personas).

Módulo distinto al de SCVS Compañías: usa ZK Framework (clases "z-*"),
NO PrimeFaces/JSF - los IDs de cada elemento son generados dinámicamente
por ZK y cambian en cada sesión (ej. "fGBPv-real" una vez, "zLHPv-real"
otra) - a diferencia de Compañías (JSF, IDs estables), aquí TODOS los
selectores deben basarse en clase CSS o texto visible, nunca en el ID
completo del elemento.

Alcance confirmado con el usuario (2026-09-01): solo la sección
"Accionista Actual en:" (participación activa), máximo 3 empresas
relacionadas. Para la Actividad Económica de cada una (que esta tabla
NO muestra), se hace una consulta cruzada a ScraperSCVSCompanias por
RUC - mismo criterio que pide la especificación original del proyecto
(Flujo 3.1: "Registrar las compañías donde tiene participación activa
-máximo 3- y capturar la Actividad Económica de dichas empresas").

SIN PROBAR TODAVÍA CONTRA EL SITIO REAL - selectores diseñados a partir
de HTML real proporcionado, pero nunca ejecutados en vivo.
"""
from playwright.sync_api import Page

from src.scrapers.base_scraper import BaseScraper, ScraperError
from src.core.models import Cliente, TipoPersona, ParticipacionSocietaria, ResultadoConsulta
from src.scrapers.sitio_sri import ScraperSRI

ID_COMBOBOX_INPUT = "input.z-combobox-inp"
ID_PANEL_SUGERENCIAS = ".z-combobox-pp .z-comboitem"
TEXTO_RADIO_IDENTIFICACION = "Identificación"
TEXTO_ENCABEZADO_ACCIONISTA_ACTUAL = "Accionista Actual en:"


class ScraperSCVSPersonas(BaseScraper):
    nombre_sitio = "SCVS - Consulta de Personas"

    def __init__(self, context, url_base: str, url_base_sri: str):
        super().__init__(context, url_base)
        # Necesario para la consulta cruzada de Actividad Economica por
        # cada empresa relacionada encontrada (via SRI, no SCVS Companias).
        self.scraper_sri = ScraperSRI(context=context, url_base=url_base_sri)

    def tiene_captcha(self, page: Page) -> bool:
        return False  # confirmado por el usuario: este modulo no tiene captcha

    def buscar_cliente(self, page: Page, cliente: Cliente) -> list[ParticipacionSocietaria]:
        page.goto(self.url_base)
        self.delay_humano(1.0, 2.0)

        # Radio "Identificación" - se selecciona por texto del label, no
        # por ID (dinamico). ZK hace clickeable el <label>, no solo el
        # <input>, para alternar el radio.
        page.click(f"label:has-text('{TEXTO_RADIO_IDENTIFICACION}')")
        self.delay_humano(0.3, 0.6)

        campo = page.locator(ID_COMBOBOX_INPUT).first
        campo.click()
        campo.type(cliente.identificacion, delay=100)
        self.delay_humano(1.0, 1.5)

        # NO se hace clic en la sugerencia del panel - confirmado con
        # evidencia real: ZK auto-completa el campo con el formato
        # "ID | NOMBRE" apenas hay una sola coincidencia exacta, SIN
        # necesitar clic. Hacer clic de todas formas en el panel (que
        # en ese punto ya podria estar en un estado inconsistente)
        # destruye el combobox completo y la pagina vuelve al
        # formulario vacio. Solo se valida que el campo SI contenga
        # el texto esperado (confirma que el auto-completado ocurrio).
        valor_campo = campo.input_value()
        if cliente.identificacion not in valor_campo:
            raise ScraperError(
                f"[{self.nombre_sitio}] El campo no se auto-completó como se esperaba para "
                f"'{cliente.identificacion}' (valor actual: '{valor_campo}').",
                resultado=ResultadoConsulta.ERROR_DESCONOCIDO,
            )

        # Boton "Buscar" - el texto esta en un <td> hermano, no en el
        # <button> mismo, por eso se hace clic en el contenedor
        # "z-button" completo que envuelve tanto el boton como su texto.
        page.locator("span.z-button:has-text('Buscar')").first.click()

        # Esperar explicitamente a que el encabezado "Accionista Actual
        # en:" este visible, MAS un margen generoso adicional - la
        # pagina tiene 8 secciones ZK pesadas y el timing parece
        # inconsistente entre corridas (a veces alcanza con poco, a
        # veces no). Se prioriza confiabilidad sobre velocidad aqui.
        page.locator(f"td.z-caption-l:has-text('{TEXTO_ENCABEZADO_ACCIONISTA_ACTUAL}')").first.wait_for(state="visible", timeout=20000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass  # si no llega a quedar inactivo del todo, seguimos igual tras el timeout
        self.delay_humano(2.5, 3.5)

        from src.documentos.evidencia import capturar_evidencia
        capturar_evidencia(
            page, cliente.identificacion_evidencia or cliente.identificacion,
            sitio="sitio3_scvs_personas_resultado", carpeta_sitio="scvs_personas",
            subcarpeta=cliente.subcarpeta_evidencia,
        )

        participaciones = self._extraer_accionista_actual(page)

        # Consulta cruzada por RUC via SRI para la Actividad Economica de
        # cada empresa relacionada (maximo 3, ya limitado en la
        # extraccion). Se usa SRI (no SCVS Companias) porque ese
        # scraper ya extrae "actividad_economica" de forma confiable -
        # SCVS Companias nunca extrajo ese campo, agregarlo ahi
        # significaria codigo nuevo sin probar.
        for participacion in participaciones:
            pagina_sri = page.context.new_page()
            try:
                cliente_empresa_relacionada = Cliente(
                    identificacion=participacion.ruc_empresa, tipo_persona=TipoPersona.JURIDICA,
                    razon_social=participacion.nombre_empresa,
                )
                datos_sri = self.scraper_sri.consultar_ruc(pagina_sri, cliente_empresa_relacionada)
                participacion.actividad_economica = datos_sri.get("actividad_economica", "") or "No disponible"
            except Exception as e:
                print(f"    [SCVS Personas] No se pudo obtener Actividad Económica de {participacion.nombre_empresa} ({participacion.ruc_empresa}) vía SRI: {type(e).__name__}: {e}")
                participacion.actividad_economica = "No disponible"
            finally:
                # Pestaña separada para no interferir con 'page' (que
                # sigue mostrando los resultados de SCVS) - confirmado
                # con evidencia real: reutilizar la misma pagina hacia
                # SRI dejaba la pantalla de SCVS en un estado raro.
                pagina_sri.close()

        return participaciones

    def _extraer_accionista_actual(self, page: Page) -> list[ParticipacionSocietaria]:
        """
        Localiza la sección "Accionista Actual en:" por su texto de
        encabezado. IMPORTANTE: el encabezado y la tabla de datos NO
        estan anidados (padre-hijo) - son divs HERMANOS en el DOM
        (confirmado con evidencia real): el div exterior exacto
        "z-groupbox-3d" contiene solo el encabezado, y la tabla de
        datos vive en un div HERMANO siguiente (id terminado en
        "-cave"). Se sube con clase EXACTA "z-groupbox-3d" (no
        contains(), que enganchaba erroneamente con "z-groupbox-3d-hm"/
        "-hl"/"-hr", subclases mas cercanas con nombre parecido), y
        luego se toma el siguiente hermano para buscar las filas.
        """
        encabezado = page.locator(f"td.z-caption-l:has-text('{TEXTO_ENCABEZADO_ACCIONISTA_ACTUAL}')").first
        if encabezado.count() == 0:
            return []

        contenedor_datos = encabezado.locator(
            "xpath=ancestor::div[@class='z-groupbox-3d'][1]/div[contains(@class,'z-groupbox-3d-cnt')]"
        )
        filas = contenedor_datos.locator("tr.z-listitem").all()

        participaciones = []
        for fila in filas[:3]:  # maximo 3, segun especificacion original
            celdas = fila.locator("td").all_inner_texts()
            if len(celdas) < 3:
                continue
            nombre_empresa = celdas[1].strip()
            ruc_empresa = celdas[2].strip()
            participaciones.append(ParticipacionSocietaria(ruc_empresa=ruc_empresa, nombre_empresa=nombre_empresa))

        return participaciones